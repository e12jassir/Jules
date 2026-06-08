mod app;
mod ipc;
mod ui;
mod widgets;

use std::{
    env,
    error::Error,
    fs::{self, OpenOptions},
    path::{Path, PathBuf},
    process::Stdio,
};

use app::{AppEvent, AppState, TuiMode};
use crossterm::{
    event::{self, Event, KeyCode, KeyEvent, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ipc::{IpcInbound, IpcOutbound};
use ratatui::{backend::CrosstermBackend, Terminal};
use tokio::{
    io::{AsyncBufReadExt, AsyncWriteExt, BufReader},
    process::Command,
    sync::mpsc::{unbounded_channel, UnboundedSender},
};

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    let mut state = AppState::default();

    let (event_tx, mut event_rx) = unbounded_channel::<AppEvent>();
    let (writer_tx, mut writer_rx) = unbounded_channel::<String>();

    let mut child = spawn_backend()?;
    let stdout = child
        .stdout
        .take()
        .ok_or("failed to capture child stdout")?;
    let mut stdin = child
        .stdin
        .take()
        .ok_or("failed to capture child stdin")?;

    tokio::spawn(async move {
        while let Some(line) = writer_rx.recv().await {
            if stdin.write_all(line.as_bytes()).await.is_err() {
                break;
            }
            if stdin.write_all(b"\n").await.is_err() {
                break;
            }
            if stdin.flush().await.is_err() {
                break;
            }
        }
    });

    let stdout_tx = event_tx.clone();
    tokio::spawn(async move {
        let mut lines = BufReader::new(stdout).lines();
        loop {
            match lines.next_line().await {
                Ok(Some(line)) => match serde_json::from_str::<IpcInbound>(&line) {
                    Ok(msg) => {
                        if stdout_tx.send(AppEvent::Ipc(msg)).is_err() {
                            break;
                        }
                    }
                    Err(err) => {
                        let _ = stdout_tx.send(AppEvent::Ipc(IpcInbound::Error {
                            message: format!("invalid IPC from backend: {err}"),
                            recoverable: true,
                        }));
                    }
                },
                Ok(None) => {
                    let _ = stdout_tx.send(AppEvent::ChildExited(None));
                    break;
                }
                Err(err) => {
                    let _ = stdout_tx.send(AppEvent::Ipc(IpcInbound::Error {
                        message: format!("failed to read backend stdout: {err}"),
                        recoverable: false,
                    }));
                    let _ = stdout_tx.send(AppEvent::ChildExited(None));
                    break;
                }
            }
        }
    });

    let wait_tx = event_tx.clone();
    tokio::spawn(async move {
        let code = child.wait().await.ok().and_then(|status| status.code());
        let _ = wait_tx.send(AppEvent::ChildExited(code));
    });

    let term_tx = event_tx.clone();
    std::thread::spawn(move || {
        while let Ok(ev) = event::read() {
            match ev {
                Event::Key(_) | Event::Resize(_, _) => {
                    if term_tx.send(AppEvent::Terminal(ev)).is_err() {
                        break;
                    }
                }
                _ => {}
            }
        }
    });

    let mut terminal = setup_terminal()?;
    send_outbound(&writer_tx, &IpcOutbound::Init { protocol_version: 1 })?;
    terminal.draw(|frame| ui::draw(frame, &state))?;

    let mut should_quit = false;
    while let Some(event) = event_rx.recv().await {
        if process_event(event, &mut state, &writer_tx, &mut should_quit)? {
            break;
        }
        terminal.draw(|frame| ui::draw(frame, &state))?;
    }

    let _ = send_outbound(&writer_tx, &IpcOutbound::Quit);
    restore_terminal(&mut terminal)?;
    Ok(())
}

fn process_event(
    event: AppEvent,
    state: &mut AppState,
    writer_tx: &UnboundedSender<String>,
    should_quit: &mut bool,
) -> Result<bool, Box<dyn Error>> {
    match event {
        AppEvent::Terminal(ev) => handle_terminal_event(ev, state, writer_tx, should_quit)?,
        AppEvent::Ipc(msg) => handle_ipc_event(msg, state, writer_tx)?,
        AppEvent::Send(line) => {
            writer_tx.send(line).map_err(|_| "writer channel closed")?;
        }
        AppEvent::ChildExited(code) => {
            if !*should_quit {
                state.mode = TuiMode::Error(format!(
                    "Backend exited{}",
                    code.map(|c| format!(" with code {c}")).unwrap_or_default()
                ));
            }
        }
        AppEvent::Quit => {
            *should_quit = true;
            return Ok(true);
        }
    }
    Ok(false)
}

fn handle_terminal_event(
    event: Event,
    state: &mut AppState,
    writer_tx: &UnboundedSender<String>,
    should_quit: &mut bool,
) -> Result<(), Box<dyn Error>> {
    match event {
        Event::Resize(_, _) => return Ok(()),
        Event::Key(key) => {
            if key.modifiers.contains(KeyModifiers::CONTROL) {
                match key.code {
                    KeyCode::Char('c') => {
                        *should_quit = true;
                        return Ok(());
                    }
                    KeyCode::Char('p') => {
                        state.input = "/".to_string();
                        state.mode = TuiMode::Chat;
                        return Ok(());
                    }
                    _ => {}
                }
            }

            match &state.mode {
                TuiMode::Connecting => return Ok(()),
                TuiMode::Error(_) => {
                    if matches!(key.code, KeyCode::Esc | KeyCode::Enter) {
                        *should_quit = true;
                    }
                    return Ok(());
                }
                TuiMode::ModelPicker => {
                    handle_model_picker_key(key, state, writer_tx)?;
                    return Ok(());
                }
                TuiMode::Chat => {}
            }

            match key.code {
                KeyCode::Enter => submit_input(state, writer_tx)?,
                KeyCode::Char(c) => state.input.push(c),
                KeyCode::Backspace => {
                    state.input.pop();
                }
                KeyCode::Esc => {
                    state.input.clear();
                }
                KeyCode::Up => navigate_history(state, true),
                KeyCode::Down => navigate_history(state, false),
                KeyCode::Tab => cycle_model(state, writer_tx)?,
                _ => {}
            }
        }
        _ => {}
    }
    Ok(())
}

fn handle_model_picker_key(
    key: KeyEvent,
    state: &mut AppState,
    writer_tx: &UnboundedSender<String>,
) -> Result<(), Box<dyn Error>> {
    match key.code {
        KeyCode::Tab => cycle_model(state, writer_tx)?,
        KeyCode::Esc | KeyCode::Enter => state.mode = TuiMode::Chat,
        _ => state.mode = TuiMode::Chat,
    }
    Ok(())
}

fn handle_ipc_event(
    msg: IpcInbound,
    state: &mut AppState,
    writer_tx: &UnboundedSender<String>,
) -> Result<(), Box<dyn Error>> {
    match msg {
        IpcInbound::Ready { boot_ms, .. } => {
            state.boot_ms = boot_ms;
            state.mode = TuiMode::Chat;
            send_outbound(writer_tx, &IpcOutbound::StatusGet)?;
            send_outbound(writer_tx, &IpcOutbound::ModelList)?;
        }
        IpcInbound::Token { content } => {
            state.is_streaming = true;
            state.streaming_buf.push_str(&content);
        }
        IpcInbound::Thought { content } => {
            state.messages.push((false, format!("[thought] {content}")));
        }
        IpcInbound::Done { .. } => {
            if !state.streaming_buf.is_empty() {
                state.messages.push((false, state.streaming_buf.clone()));
            }
            state.streaming_buf.clear();
            state.is_streaming = false;
        }
        IpcInbound::Cancelled => {
            state.streaming_buf.clear();
            state.is_streaming = false;
            state.messages.push((false, "[cancelled]".into()));
        }
        IpcInbound::CommandResult { name, ok, data, error } => {
            let content = if ok {
                format!("/{name}: {data}")
            } else {
                format!("/{name} error: {}", error.unwrap_or_else(|| "unknown error".into()))
            };
            state.messages.push((false, content));
        }
        IpcInbound::ModelChanged { provider, model } => {
            state.active_model = format!("{provider}:{model}");
            state.mode = TuiMode::Chat;
        }
        IpcInbound::ModelList { models } => {
            state.available_models = models;
            if state.active_model == "unknown" {
                if let Some(first) = state.available_models.first() {
                    if first.len() >= 2 {
                        state.active_model = format!("{}:{}", first[0], first[1]);
                    }
                }
            }
        }
        IpcInbound::Status {
            online,
            episodes,
            scoring_healthy,
        } => {
            state.online = online;
            state.episodes = episodes;
            state.scoring_healthy = scoring_healthy;
        }
        IpcInbound::Error { message, recoverable } => {
            if recoverable {
                state.messages.push((false, format!("[error] {message}")));
                state.is_streaming = false;
            } else {
                state.mode = TuiMode::Error(message);
            }
        }
    }
    Ok(())
}

fn submit_input(
    state: &mut AppState,
    writer_tx: &UnboundedSender<String>,
) -> Result<(), Box<dyn Error>> {
    let input = state.input.trim().to_string();
    if input.is_empty() {
        return Ok(());
    }

    if state.input_history.last() != Some(&input) {
        state.input_history.push(input.clone());
    }
    state.history_idx = None;

    if let Some(rest) = input.strip_prefix('/') {
        let mut parts = rest.split_whitespace();
        let name = parts.next().unwrap_or("status").to_string();
        let args = parts.map(|s| s.to_string()).collect::<Vec<_>>();
        send_outbound(writer_tx, &IpcOutbound::Command { name, args })?;
    } else {
        state.messages.push((true, input.clone()));
        state.streaming_buf.clear();
        state.is_streaming = false;
        send_outbound(writer_tx, &IpcOutbound::Message { content: input })?;
    }

    state.input.clear();
    Ok(())
}

fn navigate_history(state: &mut AppState, up: bool) {
    if state.input_history.is_empty() {
        return;
    }

    let next = match (state.history_idx, up) {
        (None, true) => Some(state.input_history.len().saturating_sub(1)),
        (Some(idx), true) => Some(idx.saturating_sub(1)),
        (Some(idx), false) if idx + 1 < state.input_history.len() => Some(idx + 1),
        (_, false) => None,
    };

    state.history_idx = next;
    state.input = next
        .and_then(|idx| state.input_history.get(idx).cloned())
        .unwrap_or_default();
}

fn cycle_model(
    state: &mut AppState,
    writer_tx: &UnboundedSender<String>,
) -> Result<(), Box<dyn Error>> {
    use crate::widgets::model_picker::ModelPicker;

    if let Some(idx) = ModelPicker::next_model_index(&state.active_model, &state.available_models) {
        if let Some(model) = state.available_models.get(idx) {
            if model.len() >= 2 {
                send_outbound(
                    writer_tx,
                    &IpcOutbound::ModelSet {
                        provider: model[0].clone(),
                        model: model[1].clone(),
                    },
                )?;
                state.mode = TuiMode::ModelPicker;
            }
        }
    }
    Ok(())
}

fn send_outbound(
    writer_tx: &UnboundedSender<String>,
    msg: &IpcOutbound,
) -> Result<(), Box<dyn Error>> {
    let line = serde_json::to_string(msg)?;
    writer_tx.send(line).map_err(|_| "writer channel closed")?;
    Ok(())
}

fn spawn_backend() -> Result<tokio::process::Child, Box<dyn Error>> {
    let python = resolve_python();
    let log_path = backend_log_path();
    if let Some(parent) = log_path.parent() {
        fs::create_dir_all(parent)?;
    }
    let stderr = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)?;

    let mut cmd = Command::new(python);
    cmd.args(["-m", "jules.server"])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::from(stderr));

    if let Ok(root) = env::current_dir() {
        cmd.current_dir(root);
    }

    Ok(cmd.spawn()?)
}

fn resolve_python() -> String {
    if let Ok(value) = env::var("JULES_PYTHON") {
        return value;
    }

    let venv = Path::new(".venv/bin/python");
    if venv.exists() {
        return venv.to_string_lossy().to_string();
    }

    "python3".to_string()
}

fn backend_log_path() -> PathBuf {
    env::temp_dir().join("jules-tui-backend.log")
}

fn setup_terminal() -> Result<Terminal<CrosstermBackend<std::io::Stdout>>, Box<dyn Error>> {
    enable_raw_mode()?;
    let mut stdout = std::io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    Ok(Terminal::new(backend)?)
}

fn restore_terminal(
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
) -> Result<(), Box<dyn Error>> {
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ready_event_switches_to_chat_and_requests_status_and_models() {
        let (tx, mut rx) = unbounded_channel();
        let mut state = AppState::default();

        handle_ipc_event(
            IpcInbound::Ready {
                protocol_version: 1,
                boot_ms: 12.5,
            },
            &mut state,
            &tx,
        )
        .unwrap();

        assert!(matches!(state.mode, TuiMode::Chat));
        assert_eq!(state.boot_ms, 12.5);

        let first = rx.try_recv().unwrap();
        let second = rx.try_recv().unwrap();
        assert!(first.contains("status_get") || second.contains("status_get"));
        assert!(first.contains("model_list") || second.contains("model_list"));
    }

    #[test]
    fn token_and_done_events_commit_streamed_message() {
        let (tx, _rx) = unbounded_channel();
        let mut state = AppState::default();

        handle_ipc_event(IpcInbound::Token { content: "hel".into() }, &mut state, &tx).unwrap();
        handle_ipc_event(IpcInbound::Token { content: "lo".into() }, &mut state, &tx).unwrap();
        assert!(state.is_streaming);
        assert_eq!(state.streaming_buf, "hello");

        handle_ipc_event(IpcInbound::Done { tokens: 2 }, &mut state, &tx).unwrap();
        assert!(!state.is_streaming);
        assert!(state.streaming_buf.is_empty());
        assert_eq!(state.messages.last(), Some(&(false, "hello".into())));
    }

    #[test]
    fn submit_slash_command_serializes_command_request() {
        let (tx, mut rx) = unbounded_channel();
        let mut state = AppState::default();
        state.input = "/status now".into();

        submit_input(&mut state, &tx).unwrap();

        let line = rx.try_recv().unwrap();
        assert!(line.contains("\"type\":\"command\""));
        assert!(line.contains("\"name\":\"status\""));
        assert!(line.contains("\"args\":[\"now\"]"));
        assert!(state.input.is_empty());
    }

    #[test]
    fn submit_plain_message_records_history_and_serializes_message() {
        let (tx, mut rx) = unbounded_channel();
        let mut state = AppState::default();
        state.input = "hola".into();

        submit_input(&mut state, &tx).unwrap();

        let line = rx.try_recv().unwrap();
        assert!(line.contains("\"type\":\"message\""));
        assert!(line.contains("\"content\":\"hola\""));
        assert_eq!(state.messages.last(), Some(&(true, "hola".into())));
        assert_eq!(state.input_history.last(), Some(&"hola".into()));
    }
}
