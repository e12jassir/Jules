//! AppState — visual prototype only. No IPC, no backend connection yet.
//! Data below is hardcoded to mirror jules_tui_mockup.html exactly, so we can
//! validate visual fidelity in Ratatui before wiring the real Python backend.

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Screen {
    Home,
    Chat,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Role {
    User,
    Jules,
}

#[derive(Debug, Clone)]
pub struct ChatMessage {
    pub role: Role,
    pub who: &'static str,
    pub thinking: Option<String>,
    pub body: String,
    pub tagline: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // Auto variant wired once Batch 1 IPC reports real routing_mode
pub enum RoutingMode {
    Manual,
    Auto,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DoctorStatus {
    Pass,
    Fail,
    Warn,
}

#[derive(Debug, Clone)]
pub struct DoctorCheck {
    pub status: DoctorStatus,
    pub name: String,
    pub message: String,
}

pub struct AppState {
    pub screen: Screen,
    pub should_quit: bool,

    // Home / chat input
    pub input: String,
    pub cursor_pos: usize,

    // Model / routing (mock — Batch 1 will wire real values via StatusEvent)
    pub active_model: String,
    pub active_provider: String,
    pub routing_mode: RoutingMode,
    pub routing_reason: Option<String>,

    // Chat thread
    pub messages: Vec<ChatMessage>,
    /// Number of message rows scrolled up from the bottom. 0 means
    /// "pinned to the latest message" (default). Wired to Home/End/
    /// PageUp/PageDown/Ctrl+Up/Ctrl+Down in main.rs (user report,
    /// 2026-07-19: "no puedo subir ni bajar" — scroll was never wired to
    /// input, only the field existed).
    pub scroll_offset: u16,
    pub thinking_expanded: bool,

    // Sidebar — CONTEXTO panel
    pub ctx_tokens: u32,
    pub ctx_used_pct: u8,
    pub ctx_quota_provider: String,
    pub ctx_quota_pct: u8,

    // Sidebar — MEMORIA panel
    pub mem_episodes: u32,
    pub mem_top_match_pct: u8,
    pub mem_top_match_note: String,

    // Status bar (transparent background, text only).
    pub cwd: String,
    pub git_branch: Option<String>,
    pub version: String,

    // Doctor checks shown in the sidebar (populated when /doctor completes).
    pub doctor_checks: Vec<DoctorCheck>,
    /// True while we're awaiting the response to a /doctor command, so Done
    /// knows to parse the resulting message as doctor output.
    pub pending_doctor: bool,
    /// True from startup until the auto-run /doctor finishes, so the
    /// sidebar can show "checking..." instead of "run /doctor".
    pub doctor_running: bool,
    /// Accumulates backend output for a silent /doctor run so the chunks
    /// never appear in the chat log.
    doctor_buffer: String,

    pub sidebar_visible: bool,
    pub theme: crate::palette::Theme,

    // Backend connection (subprocess + NDJSON, see backend.rs). `None`
    // when the backend failed to spawn — the TUI still runs, but
    // submit_input() will surface a visible error instead of pretending
    // to answer (no more hardcoded mock responses).
    pub backend: Option<crate::backend::BackendClient>,
    pub backend_error: Option<String>,
    /// Index of the in-progress Jules message being streamed into, so
    /// `poll_backend_events` can append tokens without re-creating a new
    /// ChatMessage per chunk.
    pending_jules_message: Option<usize>,

    /// Currently highlighted index into the command overlay's match list
    /// (see `commands.rs`). `None` when the overlay isn't showing — i.e.
    /// the input doesn't start with `/`, or it has a space (past the
    /// command name into arguments).
    pub command_overlay_selected: Option<usize>,

    /// `true` while the `/themes` picker overlay is open — a small popup
    /// listing all themes so the user can pick one directly, instead of
    /// only cycling with ctrl+y (user request, 2026-07-21).
    pub theme_overlay_visible: bool,
    /// Highlighted index into `palette::ALL_THEMES` while the picker is
    /// open.
    pub theme_overlay_selected: usize,
    /// Animation tick counter for UI animations (e.g. streaming loading bar).
    pub anim_tick: usize,
    /// `true` while the backend is generating a response (from submit_input until Done/Error).
    pub is_generating: bool,
}

impl AppState {
    pub fn is_streaming(&self) -> bool {
        self.is_generating || self.pending_jules_message.is_some()
    }
    /// Where to find the Python venv interpreter that hosts the real Jules
    /// backend. Resolved relative to the **running executable's location**
    /// (not the process cwd — those differ whenever the binary is launched
    /// from outside `jules-tui/`, e.g. `cd .. && jules-tui/target/debug/jules-tui`,
    /// which previously produced "No such file or directory" because `..`
    /// was interpreted relative to the caller's shell cwd, not the binary's
    /// own directory). Matches the on-disk layout `Jules/.venv` +
    /// `Jules/jules-tui/target/debug/jules-tui`, so we go up from the
    /// executable's directory until we escape `target/{debug,release}`.
    /// Overridable via `JULES_PYTHON` for anyone running from a different
    /// layout, per the same spirit as other env-driven overrides in this
    /// codebase (e.g. `SHELL`, `HOME`).
    fn resolve_python_path() -> String {
        if let Ok(p) = std::env::var("JULES_PYTHON") {
            return p;
        }
        Self::project_root()
            .join(".venv/bin/python")
            .to_string_lossy()
            .into_owned()
    }

    fn resolve_backend_cwd() -> String {
        if let Ok(p) = std::env::var("JULES_BACKEND_CWD") {
            return p;
        }
        Self::project_root().to_string_lossy().into_owned()
    }

    /// Walk up from the running executable's directory past `target/debug`
    /// or `target/release` to reach `jules-tui/`, then one more level to
    /// reach the `Jules/` project root that holds `.venv/`. Falls back to
    /// `..` (the previous cwd-relative behavior) if the executable's path
    /// cannot be determined — e.g. some minimal/sandboxed environments.
    fn project_root() -> std::path::PathBuf {
        std::env::current_exe()
            .ok()
            .and_then(|exe| {
                let dir = exe.parent()?; // .../jules-tui/target/debug
                let target = dir.parent()?; // .../jules-tui/target
                let jules_tui = target.parent()?; // .../jules-tui
                let project_root = jules_tui.parent()?; // .../Jules
                Some(project_root.to_path_buf())
            })
            .unwrap_or_else(|| std::path::PathBuf::from(".."))
    }

    pub fn new() -> Self {
        // Placeholder mock conversation removed (user decision, 2026-07-18):
        // the chat starts empty — only the user's own submitted messages
        // should appear, no canned Jules reply.
        let messages: Vec<ChatMessage> = Vec::new();

        let python_path = Self::resolve_python_path();
        let backend_cwd = Self::resolve_backend_cwd();
        let (backend, backend_error) =
            match crate::backend::BackendClient::spawn(&python_path, &backend_cwd) {
                Ok(client) => (Some(client), None),
                Err(e) => (
                    None,
                    Some(format!(
                        "no se pudo iniciar el backend ({python_path}): {e}"
                    )),
                ),
            };

        let mut state = Self {
            screen: Screen::Home,
            should_quit: false,

            input: String::new(),
            cursor_pos: 0,

            active_model: "Gemini 3.5 Flash (Primary)".to_string(),
            active_provider: "Antigravity".to_string(),
            routing_mode: RoutingMode::Manual,
            routing_reason: None,

            messages,
            scroll_offset: 0,
            thinking_expanded: true,

            ctx_tokens: 0,
            ctx_used_pct: 0,
            ctx_quota_provider: "antigravity".to_string(),
            ctx_quota_pct: 0,

            mem_episodes: 0,
            mem_top_match_pct: 0,
            mem_top_match_note: "none".to_string(),

            cwd: real_cwd(),
            git_branch: real_git_branch(),
            version: "0.4.0".to_string(),

            doctor_checks: Vec::new(),
            pending_doctor: false,
            doctor_running: false,
            doctor_buffer: String::new(),

            sidebar_visible: true,
            theme: crate::palette::Theme::System,
            backend,
            backend_error,
            pending_jules_message: None,
            command_overlay_selected: None,
            theme_overlay_visible: false,
            theme_overlay_selected: 0,
            anim_tick: 0,
            is_generating: false,
        };
        state.run_doctor_silent();
        state
    }

    /// Send the doctor command to the backend without adding any chat
    /// message — used at startup and whenever the sidebar needs a refresh.
    pub fn run_doctor_silent(&mut self) {
        if let Some(backend) = self.backend.as_mut() {
            if backend.send_command("doctor", &[]).is_ok() {
                self.pending_doctor = true;
                self.doctor_running = true;
            }
        }
    }

    pub fn submit_input(&mut self) {
        let trimmed = self.input.trim();
        if trimmed.is_empty() {
            return;
        }
        let text = trimmed.to_string();
        self.input.clear();
        self.cursor_pos = 0;
        self.screen = Screen::Chat;

        if let Some((name, args)) = crate::commands::slash_command_line(&text) {
            self.dispatch_slash_command(&text, name, args);
            return;
        }

        self.messages.push(ChatMessage {
            role: Role::User,
            who: "you",
            thinking: None,
            body: text.clone(),
            tagline: None,
        });
        self.update_sidebar_metrics();

        match self.backend.as_mut() {
            Some(backend) => {
                self.is_generating = true;
                if let Err(e) = backend.send_message(&text) {
                    self.is_generating = false;
                    self.messages.push(ChatMessage {
                        role: Role::Jules,
                        who: "jules",
                        thinking: None,
                        body: format!("Error enviando mensaje al backend: {e}"),
                        tagline: None,
                    });
                    self.update_sidebar_metrics();
                }
            }
            None => {
                self.is_generating = false;
                let reason = self
                    .backend_error
                    .clone()
                    .unwrap_or_else(|| "backend no disponible".to_string());
                self.messages.push(ChatMessage {
                    role: Role::Jules,
                    who: "jules",
                    thinking: None,
                    body: reason,
                    tagline: None,
                });
                self.update_sidebar_metrics();
            }
        }
    }

    pub fn update_sidebar_metrics(&mut self) {
        let total_chars: usize = self.messages.iter().map(|m| m.body.len()).sum();
        let approx_tokens = (total_chars / 4) as u32;
        self.ctx_tokens = approx_tokens;
        self.ctx_used_pct = ((approx_tokens as f32 / 200_000.0) * 100.0).min(100.0) as u8;

        let user_msg_count = self.messages.iter().filter(|m| matches!(m.role, Role::User)).count() as u32;
        self.mem_episodes = user_msg_count;
        if user_msg_count > 0 {
            self.mem_top_match_pct = 95;
            self.mem_top_match_note = "active session context".to_string();
        } else {
            self.mem_top_match_pct = 0;
            self.mem_top_match_note = "none".to_string();
        }
    }

    /// Route a submitted `/command` line: `clear`/`exit` are resolved
    /// entirely client-side (per jules/cli/protocol.py's docstring — they
    /// are UI/process concerns, not backend logic); everything else is
    /// sent to the backend as a `command` NDJSON message and dispatched
    /// to the real handlers in `jules/cli/commands.py` (user decision,
    /// 2026-07-19: reuse the existing CLI's command logic wholesale,
    /// don't reimplement it).
    fn dispatch_slash_command(&mut self, raw_text: &str, name: &str, args: Vec<String>) {
        self.messages.push(ChatMessage {
            role: Role::User,
            who: "you",
            thinking: None,
            body: raw_text.to_string(),
            tagline: None,
        });

        match name {
            "clear" => {
                self.messages.clear();
                self.pending_jules_message = None;
            }
            "exit" => {
                self.should_quit = true;
            }
            "themes" => {
                self.open_theme_picker();
            }
            "doctor" => {
                self.pending_doctor = true;
                match self.backend.as_mut() {
                    Some(backend) => {
                        if let Err(e) = backend.send_command(name, &args) {
                            self.pending_doctor = false;
                            self.messages.push(ChatMessage {
                                role: Role::Jules,
                                who: "jules",
                                thinking: None,
                                body: format!("Error enviando comando al backend: {e}"),
                                tagline: None,
                            });
                        }
                    }
                    None => {
                        self.pending_doctor = false;
                        let reason = self
                            .backend_error
                            .clone()
                            .unwrap_or_else(|| "backend no disponible".to_string());
                        self.messages.push(ChatMessage {
                            role: Role::Jules,
                            who: "jules",
                            thinking: None,
                            body: reason,
                            tagline: None,
                        });
                    }
                }
            }
            _ => match self.backend.as_mut() {
                Some(backend) => {
                    if let Err(e) = backend.send_command(name, &args) {
                        self.messages.push(ChatMessage {
                            role: Role::Jules,
                            who: "jules",
                            thinking: None,
                            body: format!("Error enviando comando al backend: {e}"),
                            tagline: None,
                        });
                    }
                }
                None => {
                    let reason = self
                        .backend_error
                        .clone()
                        .unwrap_or_else(|| "backend no disponible".to_string());
                    self.messages.push(ChatMessage {
                        role: Role::Jules,
                        who: "jules",
                        thinking: None,
                        body: reason,
                        tagline: None,
                    });
                }
            },
        }
    }

    /// Drain any pending events from the backend's stdout thread and apply
    /// them to the chat log. Call this once per event-loop tick (see
    /// `main.rs`) — non-blocking, returns immediately if there is nothing
    /// new.
    pub fn poll_backend_events(&mut self) {
        let Some(backend) = self.backend.as_ref() else {
            return;
        };
        let mut drained = Vec::new();
        while let Ok(event) = backend.events.try_recv() {
            drained.push(event);
        }
        let has_events = !drained.is_empty();
        for event in drained {
            self.apply_backend_event(event);
        }
        if has_events {
            self.update_sidebar_metrics();
        }
    }

    fn ensure_pending_jules_message(&mut self) -> usize {
        if let Some(idx) = self.pending_jules_message {
            return idx;
        }
        self.messages.push(ChatMessage {
            role: Role::Jules,
            who: "jules",
            thinking: None,
            body: String::new(),
            tagline: None,
        });
        let idx = self.messages.len() - 1;
        self.pending_jules_message = Some(idx);
        idx
    }

    fn apply_backend_event(&mut self, event: crate::backend::BackendEvent) {
        use crate::backend::BackendEvent;
        match event {
            BackendEvent::Status { provider, model } => {
                self.active_provider = provider;
                self.active_model = model;
            }
            BackendEvent::Thinking(chunk) => {
                self.is_generating = true;
                let idx = self.ensure_pending_jules_message();
                let entry = self.messages[idx].thinking.get_or_insert_with(String::new);
                entry.push_str(&chunk);
            }
            BackendEvent::ContentChunk(chunk) => {
                self.is_generating = true;
                if self.doctor_running {
                    // Silent auto-run: accumulate in the doctor buffer,
                    // never create a visible chat message.
                    self.doctor_buffer.push_str(&chunk);
                } else {
                    let idx = self.ensure_pending_jules_message();
                    self.messages[idx].body.push_str(&chunk);
                }
            }
            BackendEvent::Done => {
                self.is_generating = false;
                if self.pending_doctor {
                    self.pending_doctor = false;
                    self.doctor_running = false;
                    // Parse results from the right source: the silent buffer
                    // for auto-runs, or the last chat message for /doctor.
                    let source = if !self.doctor_buffer.is_empty() {
                        let buf = std::mem::take(&mut self.doctor_buffer);
                        parse_doctor_output(&buf)
                    } else if let Some(msg) = self.messages.iter().rev().find(|m| matches!(m.role, Role::Jules)) {
                        parse_doctor_output(&msg.body.clone())
                    } else {
                        Vec::new()
                    };
                    self.doctor_checks = source;
                }
                self.pending_jules_message = None;
            }
            BackendEvent::Error(message) => {
                self.is_generating = false;
                self.messages.push(ChatMessage {
                    role: Role::Jules,
                    who: "jules",
                    thinking: None,
                    body: format!("Error del backend: {message}"),
                    tagline: None,
                });
                self.pending_jules_message = None;
            }
            BackendEvent::Disconnected => {
                self.is_generating = false;
                self.backend = None;
                self.backend_error = Some("el backend se desconectó".to_string());
                self.messages.push(ChatMessage {
                    role: Role::Jules,
                    who: "jules",
                    thinking: None,
                    body: "El backend se desconectó inesperadamente.".to_string(),
                    tagline: None,
                });
                self.pending_jules_message = None;
            }
        }
    }

    pub fn insert_char(&mut self, c: char) {
        self.input.insert(self.cursor_pos, c);
        self.cursor_pos += c.len_utf8();
        self.command_overlay_selected = None;
    }

    pub fn backspace(&mut self) {
        if self.cursor_pos == 0 {
            return;
        }
        let mut idx = self.cursor_pos - 1;
        while !self.input.is_char_boundary(idx) {
            idx -= 1;
        }
        self.input.remove(idx);
        self.cursor_pos = idx;
        self.command_overlay_selected = None;
    }

    /// Commands matching the current input, or empty if the overlay
    /// shouldn't be showing (input isn't a bare `/command` in progress).
    pub fn command_overlay_matches(&self) -> Vec<&'static crate::commands::SlashCommand> {
        match crate::commands::slash_query(&self.input) {
            Some(query) => crate::commands::matching_commands(query),
            None => Vec::new(),
        }
    }

    pub fn command_overlay_move(&mut self, delta: i32) {
        let matches = self.command_overlay_matches();
        if matches.is_empty() {
            self.command_overlay_selected = None;
            return;
        }
        let len = matches.len() as i32;
        let current = self.command_overlay_selected.map(|i| i as i32).unwrap_or(-1);
        let next = ((current + delta) % len + len) % len;
        self.command_overlay_selected = Some(next as usize);
    }

    /// Complete the input with the currently highlighted (or first, if
    /// none highlighted) overlay match, appending a trailing space so the
    /// user can immediately type arguments. No-op if the overlay has no
    /// matches.
    pub fn command_overlay_accept(&mut self) {
        let matches = self.command_overlay_matches();
        if matches.is_empty() {
            return;
        }
        let idx = self.command_overlay_selected.unwrap_or(0).min(matches.len() - 1);
        let name = matches[idx].name;
        self.input = format!("/{name} ");
        self.cursor_pos = self.input.len();
        self.command_overlay_selected = None;
    }

    pub fn move_cursor_left(&mut self) {
        if self.cursor_pos == 0 {
            return;
        }
        let mut idx = self.cursor_pos - 1;
        while !self.input.is_char_boundary(idx) {
            idx -= 1;
        }
        self.cursor_pos = idx;
    }

    pub fn move_cursor_right(&mut self) {
        if self.cursor_pos >= self.input.len() {
            return;
        }
        let mut idx = self.cursor_pos + 1;
        while idx < self.input.len() && !self.input.is_char_boundary(idx) {
            idx += 1;
        }
        self.cursor_pos = idx;
    }

    pub fn toggle_thinking(&mut self) {
        self.thinking_expanded = !self.thinking_expanded;
    }

    pub fn toggle_sidebar(&mut self) {
        self.sidebar_visible = !self.sidebar_visible;
    }

    pub fn toggle_theme(&mut self) {
        self.theme = self.theme.next();
    }

    /// Open the `/themes` picker overlay, pre-selecting the currently
    /// active theme so the user sees where they are in the list.
    pub fn open_theme_picker(&mut self) {
        self.theme_overlay_selected = crate::palette::ALL_THEMES
            .iter()
            .position(|t| *t == self.theme)
            .unwrap_or(0);
        self.theme_overlay_visible = true;
    }

    pub fn close_theme_picker(&mut self) {
        self.theme_overlay_visible = false;
    }

    pub fn theme_picker_move(&mut self, delta: i32) {
        if !self.theme_overlay_visible {
            return;
        }
        let len = crate::palette::ALL_THEMES.len() as i32;
        let current = self.theme_overlay_selected as i32;
        let next = ((current + delta) % len + len) % len;
        self.theme_overlay_selected = next as usize;
    }

    /// Apply the highlighted theme and close the picker.
    pub fn theme_picker_accept(&mut self) {
        if let Some(theme) = crate::palette::ALL_THEMES.get(self.theme_overlay_selected) {
            self.theme = *theme;
        }
        self.theme_overlay_visible = false;
    }

    pub fn go_home(&mut self) {
        self.screen = Screen::Home;
    }

    /// Scroll the chat log up by `lines` rows (toward older messages).
    /// Caps are enforced by ChatLog's own render logic (there's no way to
    /// know max scroll without knowing rendered heights, which only the
    /// widget computes) — this just increments; ChatLog clamps when
    /// rendering.
    pub fn scroll_chat_up(&mut self, lines: u16) {
        self.scroll_offset = self.scroll_offset.saturating_add(lines);
    }

    pub fn scroll_chat_down(&mut self, lines: u16) {
        self.scroll_offset = self.scroll_offset.saturating_sub(lines);
    }

    pub fn scroll_chat_to_top(&mut self) {
        // A large value; ChatLog clamps to the actual max on render.
        self.scroll_offset = u16::MAX;
    }

    pub fn scroll_chat_to_bottom(&mut self) {
        self.scroll_offset = 0;
    }
}

/// Parse `/doctor` backend output into structured check results.
/// Recognises lines starting with ✓, ✗, or ⚠ followed by a space.
/// Lines that don't match that pattern are silently ignored so the
/// function is robust to whitespace, ANSI resets, or extra prose the
/// backend may emit around the check list.
fn parse_doctor_output(text: &str) -> Vec<DoctorCheck> {
    let mut checks = Vec::new();
    for line in text.lines() {
        let line = line.trim();
        let (status, rest) = if let Some(r) = line.strip_prefix('✓') {
            (DoctorStatus::Pass, r)
        } else if let Some(r) = line.strip_prefix('✗') {
            (DoctorStatus::Fail, r)
        } else if let Some(r) = line.strip_prefix('⚠') {
            (DoctorStatus::Warn, r)
        } else {
            continue;
        };
        let rest = rest.trim_start_matches([' ', ':']);
        let (name, message) = if let Some(colon) = rest.find(':') {
            (rest[..colon].trim().to_string(), rest[colon + 1..].trim().to_string())
        } else {
            (rest.trim().to_string(), String::new())
        };
        if !name.is_empty() {
            checks.push(DoctorCheck { status, name, message });
        }
    }
    checks
}

/// Current working directory, shortened to `~/...` when inside $HOME —
/// mirrors what a shell prompt shows. Falls back to the raw path, or "?"
/// if the cwd cannot be read (e.g. deleted directory).
fn real_cwd() -> String {
    let cwd = match std::env::current_dir() {
        Ok(p) => p,
        Err(_) => return "?".to_string(),
    };
    if let Some(home) = std::env::var_os("HOME") {
        let home_path = std::path::PathBuf::from(home);
        if let Ok(rel) = cwd.strip_prefix(&home_path) {
            return if rel.as_os_str().is_empty() {
                "~".to_string()
            } else {
                format!("~/ {}", rel.display())
            };
        }
    }
    cwd.display().to_string()
}

/// Current git branch via `git rev-parse --abbrev-ref HEAD`, run once at
/// startup. Returns None outside a git repo or if git is not installed.
fn real_git_branch() -> Option<String> {
    let output = std::process::Command::new("git")
        .args(["rev-parse", "--abbrev-ref", "HEAD"])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    let branch = String::from_utf8(output.stdout).ok()?.trim().to_string();
    if branch.is_empty() || branch == "HEAD" {
        None
    } else {
        Some(branch)
    }
}
