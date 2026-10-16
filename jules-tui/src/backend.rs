//! Backend client — spawns the Python NDJSON protocol server
//! (`python -m jules.cli.protocol`) as a subprocess and exchanges
//! line-delimited JSON with it.
//!
//! No async runtime: stdout is read on a dedicated OS thread and forwarded
//! to the main render/event loop via `mpsc::channel`, matching the existing
//! blocking-poll style in `main.rs` (crossterm event::poll).

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::mpsc::{self, Receiver};
use std::thread;

/// One parsed event from the backend, mapped from the NDJSON wire protocol
/// defined in `jules/cli/protocol.py`.
#[derive(Debug, Clone)]
pub enum BackendEvent {
    Status {
        provider: String,
        model: String,
    },
    Thinking(String),
    ContentChunk(String),
    Done,
    Error(String),
    SessionsJson(String),
    LoadedSession(String),
    DeletedSession(String),
    /// The backend process's stdout closed unexpectedly (crash, EOF).
    Disconnected,
}

pub struct BackendClient {
    child: Child,
    stdin: ChildStdin,
    pub events: Receiver<BackendEvent>,
}

impl BackendClient {
    /// Spawn `python -m jules.cli.protocol` using the given interpreter
    /// path (e.g. the project's venv `python`) and working directory
    /// (the Python backend resolves `Path.cwd()`-relative context there).
    pub fn spawn(python_path: &str, working_dir: &str) -> std::io::Result<Self> {
        let mut child = Command::new(python_path)
            .args(["-m", "jules.cli.protocol"])
            .current_dir(working_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()?;

        let stdin = child.stdin.take().expect("piped stdin");
        let stdout = child.stdout.take().expect("piped stdout");

        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                let Ok(line) = line else { break };
                if line.trim().is_empty() {
                    continue;
                }
                let event = parse_event(&line);
                if tx.send(event).is_err() {
                    break; // receiver dropped — main loop exited
                }
            }
            let _ = tx.send(BackendEvent::Disconnected);
        });

        Ok(Self {
            child,
            stdin,
            events: rx,
        })
    }

    /// Send one user message to the backend as a single NDJSON line.
    pub fn send_message(&mut self, content: &str) -> std::io::Result<()> {
        // Minimal JSON string escaping — content is plain chat text, not
        // arbitrary untrusted structure, but quotes/backslashes/newlines
        // must still be escaped to keep the line valid NDJSON.
        let escaped = escape_json_string(content);
        writeln!(
            self.stdin,
            "{{\"type\":\"user_message\",\"content\":\"{escaped}\"}}"
        )?;
        self.stdin.flush()
    }

    /// Send a slash command (e.g. `/status`, `/model deepseek-v4-flash-free`)
    /// to the backend, dispatched by `jules/cli/protocol.py::_dispatch_command`
    /// to the same handlers the now-obsolete Textual TUI used (user
    /// decision, 2026-07-19: "migra todo el backend... el cli y funciones
    /// que ya estaban" — command logic is real backend logic, reused as-is,
    /// only the transport changes).
    pub fn send_command(&mut self, name: &str, args: &[String]) -> std::io::Result<()> {
        let escaped_name = escape_json_string(name);
        let escaped_args: Vec<String> = args
            .iter()
            .map(|a| format!("\"{}\"", escape_json_string(a)))
            .collect();
        writeln!(
            self.stdin,
            "{{\"type\":\"command\",\"name\":\"{escaped_name}\",\"args\":[{}]}}",
            escaped_args.join(",")
        )?;
        self.stdin.flush()
    }

    #[allow(dead_code)] // available for explicit shutdown once app.rs wires it on quit
    pub fn kill(&mut self) {
        let _ = self.child.kill();
    }
}

fn escape_json_string(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out
}

/// Hand-rolled minimal JSON field extraction — avoids pulling in a full
/// JSON crate (serde_json) for a handful of known, flat message shapes.
/// Falls back to `BackendEvent::Error` on anything unexpected, so a
/// malformed or future-shaped line never panics the TUI.
fn parse_event(line: &str) -> BackendEvent {
    let msg_type = extract_string_field(line, "type");
    match msg_type.as_deref() {
        Some("status") => BackendEvent::Status {
            provider: extract_string_field(line, "provider").unwrap_or_default(),
            model: extract_string_field(line, "model").unwrap_or_default(),
        },
        Some("thinking") => {
            BackendEvent::Thinking(extract_string_field(line, "content").unwrap_or_default())
        }
        Some("content_chunk") => {
            BackendEvent::ContentChunk(extract_string_field(line, "content").unwrap_or_default())
        }
        Some("done") => BackendEvent::Done,
        Some("sessions_json") => BackendEvent::SessionsJson(line.to_string()),
        Some("loaded_session") => BackendEvent::LoadedSession(line.to_string()),
        Some("deleted_session") => BackendEvent::DeletedSession(
            extract_string_field(line, "session_id").unwrap_or_default(),
        ),
        Some("tool_status") => BackendEvent::Thinking(String::new()),
        Some("error") => {
            BackendEvent::Error(extract_string_field(line, "message").unwrap_or_default())
        }
        _ => BackendEvent::Error(format!("unrecognized backend line: {line}")),
    }
}

/// Extract a top-level `"key": "value"` string field from a flat JSON
/// object, handling `\"`, `\\`, and `\n` escapes. Not a general JSON
/// parser — only supports the flat, string-valued shapes this protocol
/// actually emits (see `jules/cli/protocol.py`).
fn extract_string_field(json: &str, key: &str) -> Option<String> {
    let needle = format!("\"{key}\"");
    let key_pos = json.find(&needle)?;
    let after_key = &json[key_pos + needle.len()..];
    let colon_pos = after_key.find(':')?;
    let after_colon = after_key[colon_pos + 1..].trim_start();
    if !after_colon.starts_with('"') {
        return None;
    }
    let mut chars = after_colon[1..].chars();
    let mut out = String::new();
    while let Some(c) = chars.next() {
        match c {
            '"' => return Some(out),
            '\\' => match chars.next() {
                Some('n') => out.push('\n'),
                Some('r') => out.push('\r'),
                Some('t') => out.push('\t'),
                Some('"') => out.push('"'),
                Some('\\') => out.push('\\'),
                Some('u') => {
                    let mut hex = String::with_capacity(4);
                    for _ in 0..4 {
                        if let Some(hc) = chars.next() {
                            hex.push(hc);
                        }
                    }
                    if let Ok(code) = u32::from_str_radix(&hex, 16) {
                        if let Some(ch) = char::from_u32(code) {
                            out.push(ch);
                        }
                    }
                }
                Some(other) => out.push(other),
                None => break,
            },
            c => out.push(c),
        }
    }
    None // unterminated string — malformed line
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_event_content_chunk_with_unicode() {
        let line = r#"{"type": "content_chunk", "content": "Che, \u00bfqu\u00e9 tal?\n"}"#;
        let event = parse_event(line);
        match event {
            BackendEvent::ContentChunk(text) => {
                assert_eq!(text, "Che, ¿qué tal?\n");
            }
            _ => panic!("Expected ContentChunk"),
        }
    }

    #[test]
    fn test_parse_event_status_and_done() {
        let line_status =
            r#"{"type": "status", "provider": "opencode", "model": "deepseek-v4-flash-free"}"#;
        match parse_event(line_status) {
            BackendEvent::Status { provider, model } => {
                assert_eq!(provider, "opencode");
                assert_eq!(model, "deepseek-v4-flash-free");
            }
            _ => panic!("Expected Status"),
        }

        let line_done = r#"{"type": "done"}"#;
        assert!(matches!(parse_event(line_done), BackendEvent::Done));
    }
}
