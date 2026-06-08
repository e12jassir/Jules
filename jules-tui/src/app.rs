//! Application state and event types for the central mpsc loop.

use crate::ipc::IpcInbound;
use crossterm::event::Event;

/// All events that can arrive at the central loop.
#[derive(Debug)]
pub enum AppEvent {
    /// A terminal event from the crossterm reader task.
    Terminal(Event),
    /// A parsed IPC message from the Python server stdout reader task.
    Ipc(IpcInbound),
    /// A serialized IPC message to send to the Python server stdin writer task.
    Send(String),
    /// Child process exited — carry the exit code (None = killed).
    ChildExited(Option<i32>),
    /// Request to quit the TUI cleanly.
    Quit,
}

/// Rendering mode of the TUI.
#[derive(Debug, Clone, PartialEq)]
pub enum TuiMode {
    /// Waiting for backend ready signal.
    Connecting,
    /// Normal interactive mode.
    Chat,
    /// Model picker overlay is open.
    ModelPicker,
    /// Backend died — show error, disable input.
    Error(String),
}

/// The full application state mutated exclusively by the central event loop.
#[derive(Debug)]
pub struct AppState {
    pub mode: TuiMode,
    /// Chat messages: (is_user, content).
    pub messages: Vec<(bool, String)>,
    /// Tokens accumulating for the current streaming response.
    pub streaming_buf: String,
    pub is_streaming: bool,
    /// Current input bar contents.
    pub input: String,
    /// Active model name (provider:model).
    pub active_model: String,
    /// Available models from server.
    pub available_models: Vec<Vec<String>>,
    /// Status from last status_get.
    pub online: bool,
    pub episodes: u32,
    pub scoring_healthy: bool,
    /// Boot ms from ready event.
    pub boot_ms: f64,
    /// Input history (newest last).
    pub input_history: Vec<String>,
    pub history_idx: Option<usize>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            mode: TuiMode::Connecting,
            messages: Vec::new(),
            streaming_buf: String::new(),
            is_streaming: false,
            input: String::new(),
            active_model: String::from("unknown"),
            available_models: Vec::new(),
            online: false,
            episodes: 0,
            scoring_healthy: true,
            boot_ms: 0.0,
            input_history: Vec::new(),
            history_idx: None,
        }
    }
}
