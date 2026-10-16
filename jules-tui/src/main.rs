mod app;
mod backend;
mod banner;
mod commands;
mod models;
mod palette;
mod providers;
mod selector;
mod sessions;
mod ui;
mod widgets;

use std::io;
use std::time::Duration;

use crossterm::{
    event::{
        self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode, KeyEventKind, KeyModifiers,
        MouseEvent, MouseEventKind,
    },
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};

use app::AppState;

fn main() -> io::Result<()> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let result = run(&mut terminal);

    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;

    result
}

fn run(terminal: &mut Terminal<CrosstermBackend<io::Stdout>>) -> io::Result<()> {
    let mut state = AppState::new();

    loop {
        let size = terminal.size()?;
        if size.width == 0 || size.height == 0 {
            if event::poll(Duration::from_millis(200))? {
                if let Event::Key(key) = event::read()? {
                    if key.kind == KeyEventKind::Press
                        && key.code == KeyCode::Char('c')
                        && key.modifiers.contains(KeyModifiers::CONTROL)
                    {
                        break;
                    }
                }
            }
            continue;
        }

        state.poll_backend_events();
        state.anim_tick = state.anim_tick.wrapping_add(1);
        terminal.draw(|frame| ui::draw(frame, &state))?;

        if state.should_quit {
            break;
        }

        let poll_timeout = if state.is_streaming() {
            Duration::from_millis(60)
        } else {
            Duration::from_millis(200)
        };

        if event::poll(poll_timeout)? {
            match event::read()? {
                Event::Key(key) => {
                    if key.kind == KeyEventKind::Press {
                        handle_key(&mut state, key.code, key.modifiers);
                    }
                }
                Event::Mouse(mouse) => {
                    handle_mouse(&mut state, mouse);
                }
                _ => {}
            }
        }
    }

    Ok(())
}

fn handle_key(state: &mut AppState, code: KeyCode, modifiers: KeyModifiers) {
    if modifiers.contains(KeyModifiers::CONTROL) {
        match code {
            KeyCode::Char('c') => {
                state.should_quit = true;
                return;
            }
            KeyCode::Char('t') => {
                state.toggle_thinking();
                return;
            }
            KeyCode::Char('b') => {
                state.toggle_sidebar();
                return;
            }
            KeyCode::Char('y') => {
                state.toggle_theme();
                return;
            }
            _ => {}
        }
    }

    match state.screen {
        app::Screen::Home => handle_key_home(state, code),
        app::Screen::Chat => handle_key_chat(state, code),
    }
}

fn handle_command_overlay_key(state: &mut AppState, code: KeyCode) -> bool {
    if state.command_overlay_matches().is_empty() {
        return false;
    }

    match code {
        KeyCode::Up => state.command_overlay_move(-1),
        KeyCode::Down => state.command_overlay_move(1),
        KeyCode::Tab => match crate::commands::slash_palette_action(
            &state.input,
            crate::commands::SlashPaletteKey::Tab,
        ) {
            crate::commands::SlashPaletteAction::Complete => state.command_overlay_accept(),
            crate::commands::SlashPaletteAction::Dispatch => unreachable!("Tab always completes"),
        },
        KeyCode::Enter => match crate::commands::slash_palette_action(
            &state.input,
            crate::commands::SlashPaletteKey::Enter,
        ) {
            crate::commands::SlashPaletteAction::Dispatch => state.submit_input(),
            crate::commands::SlashPaletteAction::Complete => state.command_overlay_accept(),
        },
        KeyCode::Esc => state.dismiss_command_overlay(),
        _ => return false,
    }
    true
}

fn handle_key_home(state: &mut AppState, code: KeyCode) {
    if handle_active_selector(state, code) {
        return;
    }

    if handle_command_overlay_key(state, code) {
        return;
    }

    match code {
        KeyCode::Char(c) => state.insert_char(c),
        KeyCode::Backspace => state.backspace(),
        KeyCode::Left => state.move_cursor_left(),
        KeyCode::Right => state.move_cursor_right(),
        KeyCode::Home => state.cursor_pos = 0,
        KeyCode::End => state.cursor_pos = state.input.len(),
        KeyCode::Enter => {
            if !state.input.trim().is_empty() {
                state.submit_input();
            }
        }
        KeyCode::Esc => {
            if state.is_streaming() {
                state.cancel_streaming();
            } else {
                state.input.clear();
                state.cursor_pos = 0;
            }
        }
        _ => {}
    }
}

fn handle_key_chat(state: &mut AppState, code: KeyCode) {
    if handle_active_selector(state, code) {
        return;
    }

    if handle_command_overlay_key(state, code) {
        return;
    }

    match code {
        KeyCode::Char(c) => state.insert_char(c),
        KeyCode::Backspace => state.backspace(),
        KeyCode::Left => state.move_cursor_left(),
        KeyCode::Right => state.move_cursor_right(),
        KeyCode::Home => state.scroll_offset = u16::MAX,
        KeyCode::End => state.scroll_offset = 0,
        KeyCode::PageUp => state.scroll_offset = state.scroll_offset.saturating_add(5),
        KeyCode::PageDown => state.scroll_offset = state.scroll_offset.saturating_sub(5),
        KeyCode::Up => state.scroll_offset = state.scroll_offset.saturating_add(1),
        KeyCode::Down => state.scroll_offset = state.scroll_offset.saturating_sub(1),
        KeyCode::Enter => {
            if !state.input.trim().is_empty() {
                state.submit_input();
            }
        }
        KeyCode::Esc => {
            if state.is_streaming() {
                state.cancel_streaming();
            } else {
                state.input.clear();
                state.cursor_pos = 0;
            }
        }
        _ => {}
    }
}

fn handle_active_selector(state: &mut AppState, code: KeyCode) -> bool {
    match state.active_selector {
        Some(selector::ActiveSelector::Themes) => handle_key_theme_overlay(state, code),
        Some(selector::ActiveSelector::Models) => handle_key_models_overlay(state, code),
        Some(selector::ActiveSelector::Providers) => handle_key_provider_overlay(state, code),
        Some(selector::ActiveSelector::Sessions) => handle_key_sessions_overlay(state, code),
        None => return false,
    }
    true
}

fn handle_key_theme_overlay(state: &mut AppState, code: KeyCode) {
    match code {
        KeyCode::Up => state.theme_picker_move(-1),
        KeyCode::Down => state.theme_picker_move(1),
        KeyCode::Enter | KeyCode::Tab => state.theme_picker_accept(),
        KeyCode::Esc => state.close_theme_picker(),
        _ => {}
    }
}

fn handle_key_provider_overlay(state: &mut AppState, code: KeyCode) {
    if state.provider_overlay_input_mode {
        match code {
            KeyCode::Char(c) => state.provider_overlay_key_input.push(c),
            KeyCode::Backspace => {
                state.provider_overlay_key_input.pop();
            }
            KeyCode::Enter => state.provider_picker_accept(),
            KeyCode::Esc => {
                state.provider_overlay_input_mode = false;
                state.provider_overlay_key_input.clear();
            }
            _ => {}
        }
    } else {
        match code {
            KeyCode::Up => state.provider_picker_move(-1),
            KeyCode::Down => state.provider_picker_move(1),
            KeyCode::Enter => state.provider_picker_accept(),
            KeyCode::Esc => state.close_provider_picker(),
            _ => {}
        }
    }
}

/// `/models` picker keymap: Up/Down navigate the filtered row list,
/// Enter/Tab confirms, Esc closes without applying (same shape as
/// `handle_key_theme_overlay`), plus free-text typing/backspace to filter
/// by model or provider name — mirrors OpenCode's own model select popup
/// search box (user request, 2026-07-21).
fn handle_key_models_overlay(state: &mut AppState, code: KeyCode) {
    match code {
        KeyCode::Up => state.models_picker_move(-1),
        KeyCode::Down => state.models_picker_move(1),
        KeyCode::Enter | KeyCode::Tab => state.models_picker_accept(),
        KeyCode::Esc => state.close_models_picker(),
        KeyCode::Char(c) => state.models_picker_type(c),
        KeyCode::Backspace => state.models_picker_backspace(),
        _ => {}
    }
}

fn handle_mouse(state: &mut AppState, event: MouseEvent) {
    if let Some(selector) = state.active_selector {
        match (selector, event.kind) {
            (selector::ActiveSelector::Models, MouseEventKind::ScrollUp) => {
                state.models_picker_move(-1)
            }
            (selector::ActiveSelector::Models, MouseEventKind::ScrollDown) => {
                state.models_picker_move(1)
            }
            (selector::ActiveSelector::Themes, MouseEventKind::ScrollUp) => {
                state.theme_picker_move(-1)
            }
            (selector::ActiveSelector::Themes, MouseEventKind::ScrollDown) => {
                state.theme_picker_move(1)
            }
            (selector::ActiveSelector::Sessions, MouseEventKind::ScrollUp) => {
                state.sessions_picker_move(-1)
            }
            (selector::ActiveSelector::Sessions, MouseEventKind::ScrollDown) => {
                state.sessions_picker_move(1)
            }
            _ => {}
        }
        return;
    }

    match event.kind {
        MouseEventKind::ScrollUp => {
            state.scroll_offset = state.scroll_offset.saturating_add(3);
        }
        MouseEventKind::ScrollDown => {
            state.scroll_offset = state.scroll_offset.saturating_sub(3);
        }
        _ => {}
    }
}

fn handle_key_sessions_overlay(state: &mut AppState, code: KeyCode) {
    // Closing the popup is always safe: it only hides the UI and never
    // cancels the NDJSON request that may already be in flight.
    if code == KeyCode::Esc {
        state.sessions_picker_escape();
        return;
    }

    if state.sessions_selector.is_pending() {
        return;
    }

    if state.sessions_selector.confirming_delete.is_some() {
        if code == KeyCode::Enter {
            state.sessions_picker_confirm_delete();
        }
        return;
    }

    match code {
        KeyCode::Up => state.sessions_picker_move(-1),
        KeyCode::Down => state.sessions_picker_move(1),
        KeyCode::Enter => state.sessions_picker_accept(),
        KeyCode::Char('d') | KeyCode::Delete => state.sessions_picker_request_delete(),
        KeyCode::Char(c) => state.sessions_picker_type(c),
        KeyCode::Backspace => state.sessions_picker_backspace(),
        _ => {}
    }
}
