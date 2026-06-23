//! IPC protocol types mirroring `jules/server/protocol.py`.
//! Internally-tagged serde enums — tag field is "type", values are snake_case.

use serde::{Deserialize, Deserializer, Serialize};
use std::sync::{Arc, Mutex};
use tokio::process::Child;

// ---------------------------------------------------------------------------
// Outbound: TUI → Python server (stdin of child)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "type", rename_all = "snake_case")]
pub enum IpcOutbound {
    Init { protocol_version: u8 },
    Message { content: String },
    Command { name: String, args: Vec<String> },
    ModelSet { provider: String, model: String },
    ModelList,
    StatusGet,
    ContextGet,
    Cancel,
    Quit,
}

// ---------------------------------------------------------------------------
// Inbound: Python server → TUI (stdout of child)
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub enum IpcInbound {
    Ready {
        protocol_version: u8,
        boot_ms: f64,
    },
    Token {
        content: String,
    },
    Thought {
        content: String,
    },
    Done {
        tokens: u32,
    },
    Cancelled,
    CommandResult {
        name: String,
        ok: bool,
        data: serde_json::Value,
        error: Option<String>,
    },
    ModelChanged {
        provider: String,
        model: String,
    },
    ModelList {
        models: Vec<Vec<String>>,
    },
    Status {
        online: bool,
        episodes: u32,
        scoring_healthy: bool,
    },
    Tools {
        filesystem: bool,
        terminal: bool,
        git: bool,
        search: bool,
        web: bool,
    },
    ProjectInfo {
        path: String,
        branch: String,
        file_count: u32,
    },
    MemoryStats {
        episodes: u32,
        facts: u32,
        memories: u32,
    },
    Error {
        message: String,
        recoverable: bool,
    },
    Unknown {
        message_type: Option<String>,
        raw: serde_json::Value,
    },
}

#[derive(Debug, Clone, Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum KnownInbound {
    Ready {
        protocol_version: u8,
        boot_ms: f64,
    },
    Token {
        content: String,
    },
    Thought {
        content: String,
    },
    Done {
        tokens: u32,
    },
    Cancelled,
    CommandResult {
        name: String,
        ok: bool,
        #[serde(default)]
        data: serde_json::Value,
        #[serde(default)]
        error: Option<String>,
    },
    ModelChanged {
        provider: String,
        model: String,
    },
    ModelList {
        models: Vec<Vec<String>>,
    },
    Status {
        online: bool,
        episodes: u32,
        scoring_healthy: bool,
    },
    Tools {
        filesystem: bool,
        terminal: bool,
        git: bool,
        search: bool,
        web: bool,
    },
    ProjectInfo {
        path: String,
        branch: String,
        file_count: u32,
    },
    MemoryStats {
        episodes: u32,
        facts: u32,
        memories: u32,
    },
    Error {
        message: String,
        recoverable: bool,
    },
}

impl From<KnownInbound> for IpcInbound {
    fn from(value: KnownInbound) -> Self {
        match value {
            KnownInbound::Ready {
                protocol_version,
                boot_ms,
            } => Self::Ready {
                protocol_version,
                boot_ms,
            },
            KnownInbound::Token { content } => Self::Token { content },
            KnownInbound::Thought { content } => Self::Thought { content },
            KnownInbound::Done { tokens } => Self::Done { tokens },
            KnownInbound::Cancelled => Self::Cancelled,
            KnownInbound::CommandResult {
                name,
                ok,
                data,
                error,
            } => Self::CommandResult {
                name,
                ok,
                data,
                error,
            },
            KnownInbound::ModelChanged { provider, model } => {
                Self::ModelChanged { provider, model }
            }
            KnownInbound::ModelList { models } => Self::ModelList { models },
            KnownInbound::Status {
                online,
                episodes,
                scoring_healthy,
            } => Self::Status {
                online,
                episodes,
                scoring_healthy,
            },
            KnownInbound::Tools {
                filesystem,
                terminal,
                git,
                search,
                web,
            } => Self::Tools {
                filesystem,
                terminal,
                git,
                search,
                web,
            },
            KnownInbound::ProjectInfo {
                path,
                branch,
                file_count,
            } => Self::ProjectInfo {
                path,
                branch,
                file_count,
            },
            KnownInbound::MemoryStats {
                episodes,
                facts,
                memories,
            } => Self::MemoryStats {
                episodes,
                facts,
                memories,
            },
            KnownInbound::Error {
                message,
                recoverable,
            } => Self::Error {
                message,
                recoverable,
            },
        }
    }
}

impl<'de> Deserialize<'de> for IpcInbound {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let raw = serde_json::Value::deserialize(deserializer)?;
        match serde_json::from_value::<KnownInbound>(raw.clone()) {
            Ok(msg) => Ok(msg.into()),
            Err(_) => Ok(Self::Unknown {
                message_type: raw
                    .get("type")
                    .and_then(serde_json::Value::as_str)
                    .map(str::to_string),
                raw,
            }),
        }
    }
}

// ---------------------------------------------------------------------------
// ChildGuard — kills child process on Drop to prevent zombies
// ---------------------------------------------------------------------------

pub struct ChildGuard {
    inner: Arc<Mutex<Option<Child>>>,
}

impl ChildGuard {
    pub fn new(child: Child) -> Self {
        Self {
            inner: Arc::new(Mutex::new(Some(child))),
        }
    }

    /// Returns a clone of the shared handle so other tasks can take ownership of the child.
    pub fn handle(&self) -> Arc<Mutex<Option<Child>>> {
        self.inner.clone()
    }
}

impl Drop for ChildGuard {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.inner.lock() {
            if let Some(ref mut child) = *guard {
                let _ = child.start_kill();
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Tests — serde parity against protocol.py fixture JSON (Task 5.1)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // --- Outbound serialization ---

    #[test]
    fn init_serializes_correctly() {
        let msg = IpcOutbound::Init {
            protocol_version: 1,
        };
        let json = serde_json::to_string(&msg).unwrap();
        let v: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(v["type"], "init");
        assert_eq!(v["protocol_version"], 1);
    }

    #[test]
    fn message_serializes_correctly() {
        let msg = IpcOutbound::Message {
            content: "hola".into(),
        };
        let json = serde_json::to_string(&msg).unwrap();
        let v: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(v["type"], "message");
        assert_eq!(v["content"], "hola");
    }

    #[test]
    fn command_serializes_correctly() {
        let msg = IpcOutbound::Command {
            name: "status".into(),
            args: vec![],
        };
        let json = serde_json::to_string(&msg).unwrap();
        let v: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(v["type"], "command");
        assert_eq!(v["name"], "status");
        assert_eq!(v["args"], serde_json::json!([]));
    }

    #[test]
    fn model_set_serializes_correctly() {
        let msg = IpcOutbound::ModelSet {
            provider: "google".into(),
            model: "gemini-3.5-flash".into(),
        };
        let json = serde_json::to_string(&msg).unwrap();
        let v: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(v["type"], "model_set");
        assert_eq!(v["provider"], "google");
    }

    #[test]
    fn quit_serializes_correctly() {
        let json = serde_json::to_string(&IpcOutbound::Quit).unwrap();
        let v: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(v["type"], "quit");
    }

    #[test]
    fn context_get_serializes_correctly() {
        let json = serde_json::to_string(&IpcOutbound::ContextGet).unwrap();
        let v: serde_json::Value = serde_json::from_str(&json).unwrap();
        assert_eq!(v["type"], "context_get");
    }

    // --- Inbound deserialization (fixtures mirror protocol.py output) ---

    #[test]
    fn ready_deserializes_correctly() {
        let json = r#"{"type":"ready","protocol_version":1,"boot_ms":42.5}"#;
        let msg: IpcInbound = serde_json::from_str(json).unwrap();
        match msg {
            IpcInbound::Ready {
                protocol_version,
                boot_ms,
            } => {
                assert_eq!(protocol_version, 1);
                assert!((boot_ms - 42.5).abs() < 0.001);
            }
            _ => panic!("expected Ready"),
        }
    }

    #[test]
    fn token_deserializes_correctly() {
        let json = r#"{"type":"token","content":"hel"}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::Token { content } => assert_eq!(content, "hel"),
            _ => panic!("expected Token"),
        }
    }

    #[test]
    fn done_deserializes_correctly() {
        let json = r#"{"type":"done","tokens":342}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::Done { tokens } => assert_eq!(tokens, 342),
            _ => panic!("expected Done"),
        }
    }

    #[test]
    fn cancelled_deserializes_correctly() {
        let json = r#"{"type":"cancelled"}"#;
        assert!(matches!(
            serde_json::from_str::<IpcInbound>(json).unwrap(),
            IpcInbound::Cancelled
        ));
    }

    #[test]
    fn command_result_with_null_error_deserializes() {
        let json = r#"{"type":"command_result","name":"status","ok":true,"data":{"info":"ok"},"error":null}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::CommandResult {
                name, ok, error, ..
            } => {
                assert_eq!(name, "status");
                assert!(ok);
                assert!(error.is_none());
            }
            _ => panic!("expected CommandResult"),
        }
    }

    #[test]
    fn command_result_with_error_deserializes() {
        let json = r#"{"type":"command_result","name":"unknown","ok":false,"data":null,"error":"Unknown command: unknown"}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::CommandResult { ok, error, .. } => {
                assert!(!ok);
                assert_eq!(error.unwrap(), "Unknown command: unknown");
            }
            _ => panic!("expected CommandResult"),
        }
    }

    #[test]
    fn model_list_deserializes_correctly() {
        let json = r#"{"type":"model_list","models":[["google","gemini-3.5-flash"],["ollama","llama3.2:1b"]]}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::ModelList { models } => {
                assert_eq!(models.len(), 2);
                assert_eq!(models[0], vec!["google", "gemini-3.5-flash"]);
            }
            _ => panic!("expected ModelList"),
        }
    }

    #[test]
    fn status_deserializes_correctly() {
        let json = r#"{"type":"status","online":true,"episodes":25,"scoring_healthy":true}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::Status {
                online,
                episodes,
                scoring_healthy,
            } => {
                assert!(online);
                assert_eq!(episodes, 25);
                assert!(scoring_healthy);
            }
            _ => panic!("expected Status"),
        }
    }

    #[test]
    fn error_recoverable_deserializes() {
        let json = r#"{"type":"error","message":"provider unavailable","recoverable":true}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::Error {
                message,
                recoverable,
            } => {
                assert_eq!(message, "provider unavailable");
                assert!(recoverable);
            }
            _ => panic!("expected Error"),
        }
    }

    #[test]
    fn error_fatal_deserializes() {
        let json = r#"{"type":"error","message":"fatal","recoverable":false}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::Error { recoverable, .. } => assert!(!recoverable),
            _ => panic!("expected Error"),
        }
    }

    #[test]
    fn tools_deserialize_correctly() {
        let json = r#"{"type":"tools","filesystem":true,"terminal":false,"git":true,"search":true,"web":false}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::Tools {
                filesystem,
                terminal,
                git,
                search,
                web,
            } => {
                assert!(filesystem);
                assert!(!terminal);
                assert!(git);
                assert!(search);
                assert!(!web);
            }
            _ => panic!("expected Tools"),
        }
    }

    #[test]
    fn project_info_deserializes_correctly() {
        let json = r#"{"type":"project_info","path":"/repo","branch":"main","file_count":42}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::ProjectInfo {
                path,
                branch,
                file_count,
            } => {
                assert_eq!(path, "/repo");
                assert_eq!(branch, "main");
                assert_eq!(file_count, 42);
            }
            _ => panic!("expected ProjectInfo"),
        }
    }

    #[test]
    fn memory_stats_deserialize_correctly() {
        let json = r#"{"type":"memory_stats","episodes":3,"facts":1,"memories":2}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::MemoryStats {
                episodes,
                facts,
                memories,
            } => {
                assert_eq!(episodes, 3);
                assert_eq!(facts, 1);
                assert_eq!(memories, 2);
            }
            _ => panic!("expected MemoryStats"),
        }
    }

    #[test]
    fn unknown_inbound_deserializes_to_fallback_variant() {
        let json = r#"{"type":"future_event","payload":123}"#;
        match serde_json::from_str::<IpcInbound>(json).unwrap() {
            IpcInbound::Unknown { message_type, raw } => {
                assert_eq!(message_type.as_deref(), Some("future_event"));
                assert_eq!(raw["payload"], 123);
            }
            _ => panic!("expected Unknown"),
        }
    }
}
