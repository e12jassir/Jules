mod app;
mod backend;
mod banner;
mod commands;
mod palette;
mod ui;
mod widgets;

use std::io;
use std::time::Duration;

use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind, KeyModifiers},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};

use app::AppState;

fn main() -> io::Result<()> {
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let result = run(&mut terminal);

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
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
            if let Event::Key(key) = event::read()? {
                if key.kind != KeyEventKind::Press {
                    continue;
                }
                handle_key(&mut state, key.code, key.modifiers);
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

fn handle_key_home(state: &mut AppState, code: KeyCode) {
    if state.theme_overlay_visible {
        handle_key_theme_overlay(state, code);
        return;
    }

    let matches = state.command_overlay_matches();
    if !matches.is_empty() {
        match code {
            KeyCode::Up => {
                state.command_overlay_move(-1);
                return;
            }
            KeyCode::Down => {
                state.command_overlay_move(1);
                return;
            }
            KeyCode::Tab | KeyCode::Enter => {
                state.command_overlay_accept();
                return;
            }
            KeyCode::Esc => {
                state.command_overlay_selected = None;
                return;
            }
            _ => {}
        }
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
        _ => {}
    }
}

fn handle_key_chat(state: &mut AppState, code: KeyCode) {
    if state.theme_overlay_visible {
        handle_key_theme_overlay(state, code);
        return;
    }

    let matches = state.command_overlay_matches();
    if !matches.is_empty() {
        match code {
            KeyCode::Up => {
                state.command_overlay_move(-1);
                return;
            }
            KeyCode::Down => {
                state.command_overlay_move(1);
                return;
            }
            KeyCode::Tab | KeyCode::Enter => {
                state.command_overlay_accept();
                return;
            }
            KeyCode::Esc => {
                state.command_overlay_selected = None;
                return;
            }
            _ => {}
        }
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
        _ => {}
    }
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
