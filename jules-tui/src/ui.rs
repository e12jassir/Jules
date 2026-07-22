//! Root draw function. Mirrors the two-screen structure of
//! jules_tui_mockup.html: #home (centered logo+input+tip) and #chat
//! (grid: chat-main | sidebar).
//!
//! RULE (per ROADMAP.md B3.1): never call .style(bg(...)) on the outer
//! frame/root — only on the specific blocks that have a background in the
//! mockup (--field inputs, --panel/titlebar strips). This keeps terminal
//! transparency intact once real compositor testing happens.

use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Paragraph, Widget},
    Frame,
};

use crate::app::{AppState, Screen};
use crate::widgets::chat_log::ChatLog;
use crate::widgets::input_bar::{bordered_block, draw_command_overlay, draw_left_accent_bar, draw_panel_half_extension, InputBar};
use crate::widgets::sidebar::Sidebar;
use crate::widgets::status_bar::BottomBar;

pub fn draw(frame: &mut Frame, state: &AppState) {
    let area = frame.area();
    let rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(1),
            Constraint::Length(1), // BottomBar status line (1 line up)
            Constraint::Length(1), // bottom padding row
        ])
        .split(area);

    match state.screen {
        Screen::Home => draw_home(frame, rows[0], state),
        Screen::Chat => draw_chat(frame, rows[0], state),
    }

    frame.render_widget(
        BottomBar {
            cwd: &state.cwd,
            version: &state.version,
            sidebar_visible: state.sidebar_visible && state.screen == Screen::Chat,
            is_streaming: state.is_streaming(),
            anim_tick: state.anim_tick,
            theme: state.theme,
        },
        rows[1],
    );

    if state.theme_overlay_visible {
        draw_theme_picker(frame, area, state);
    }
}

/// `/themes` picker: a centered popup listing every available theme,
/// navigated with Up/Down and confirmed with Enter/Tab (Esc closes without
/// applying). Replaces the old ctrl+y-only cycling as the discoverable way
/// to switch themes (user request, 2026-07-21).
fn draw_theme_picker(frame: &mut Frame, area: Rect, state: &AppState) {
    use crate::palette::ALL_THEMES;
    use ratatui::widgets::{List, ListItem, ListState};

    let width: u16 = 32;
    let height: u16 = ALL_THEMES.len() as u16 + 2;
    let x = area.x + area.width.saturating_sub(width) / 2;
    let y = area.y + area.height.saturating_sub(height) / 2;
    let popup_area = Rect {
        x,
        y,
        width: width.min(area.width),
        height: height.min(area.height),
    };

    let theme = state.theme;
    let mut style = Style::default().fg(theme.text());
    style = style.bg(theme.panel_bg().unwrap_or(theme.void()));
    let block = Block::default()
        .style(style)
        .title(" themes ")
        .padding(ratatui::widgets::Padding::horizontal(1));
    let inner = block.inner(popup_area);
    frame.render_widget(block, popup_area);

    let items: Vec<ListItem> = ALL_THEMES
        .iter()
        .map(|t| {
            let marker = if *t == state.theme { "● " } else { "  " };
            ListItem::new(Line::from(vec![
                Span::styled(marker, Style::default().fg(theme.amber())),
                Span::styled(t.label(), Style::default().fg(theme.text())),
            ]))
        })
        .collect();

    let list = List::new(items).highlight_style(
        Style::default()
            .fg(theme.text())
            .add_modifier(Modifier::BOLD)
            .bg(theme.field_bg().unwrap_or(theme.void())),
    );
    let mut list_state = ListState::default();
    list_state.select(Some(state.theme_overlay_selected));
    ratatui::widgets::StatefulWidget::render(list, inner, frame.buffer_mut(), &mut list_state);
}

fn draw_home(frame: &mut Frame, area: Rect, state: &AppState) {
    // Mirrors #home .home-center: vertically centered logo + input box + tip.
    // Clamp to the actual available width so narrow terminals (e.g. 79
    // columns) never produce a box_area wider than the buffer itself —
    // that used to panic ratatui with "index outside of buffer" once the
    // fixed 84-column box exceeded the real terminal width (user-reported
    // crash, 2026-07-21).
    let box_width: u16 = 84u16.min(area.width);
    let inner_width = box_width.saturating_sub(4); // horizontal padding (2+2)
    let input_bar_height = InputBar::probe_height(&state.input, inner_width);
    let box_height: u16 = input_bar_height + 1; // + bottom padding row (no top padding)
    let logo_height: u16 = crate::banner::JULES_BANNER.len() as u16;
    let gap_logo_to_box: u16 = 2; // one clear blank line between logo and input box
    let tip_height: u16 = 2;
    let total_h = logo_height + gap_logo_to_box + box_height + 1 + tip_height;

    let top_pad = area.height.saturating_sub(total_h) / 2;
    let x = area.x + area.width.saturating_sub(box_width) / 2;

    let logo_area = Rect {
        x: area.x,
        y: area.y + top_pad,
        width: area.width,
        height: logo_height,
    };
    for (i, line) in crate::banner::JULES_BANNER.iter().enumerate() {
        let line_area = Rect {
            x: area.x,
            y: logo_area.y + i as u16,
            width: area.width,
            height: 1,
        };
        Paragraph::new(Line::from(Span::styled(
            *line,
            Style::default().fg(ratatui::style::Color::White).add_modifier(Modifier::BOLD),
        )))
        .alignment(Alignment::Center)
        .render(line_area, frame.buffer_mut());
    }

    let box_area = Rect {
        x,
        y: logo_area.y + logo_height + gap_logo_to_box,
        width: box_width,
        height: box_height,
    };
    // No border — the input panel is delimited purely by its background
    // fill (Solid theme) or nothing at all (Transparent theme).
    let block = bordered_block(state.theme);
    let inner = block.inner(box_area);
    frame.render_widget(block, box_area);
    draw_left_accent_bar(box_area, frame.buffer_mut(), state.theme);
    draw_panel_half_extension(box_area, frame.buffer_mut(), state.theme);
    // `bordered_block`'s own Padding::new(2, 2, 1, 1) already gives a
    // symmetric 2-column margin between the "┃" accent bar (drawn at
    // column 0 of the outer area) and the prompt/text content on both
    // sides — no extra shift needed here (user request, 2026-07-21:
    // "  ›_______  " with exactly 2 spaces on each end).

    let input_bar = InputBar {
        input: &state.input,
        cursor_pos: state.cursor_pos,
        placeholder: "Ask anything… \"why does my inotify watch keep hitting the limit?\"",
        mode: "chat",
        model: &state.active_model,
        provider: &state.active_provider,
        hint: "",
        prompt_char: "›",
    };
    frame.set_cursor_position(input_bar.get_cursor_position(inner));
    input_bar.render_themed(inner, frame.buffer_mut(), state.theme);

    let matches = state.command_overlay_matches();
    if !matches.is_empty() {
        let overlay_height = (matches.len() as u16 + 2).min(12);
        let overlay_area = Rect {
            x: box_area.x,
            y: box_area.y.saturating_sub(overlay_height),
            width: box_area.width,
            height: overlay_height,
        };
        draw_command_overlay(
            overlay_area,
            frame.buffer_mut(),
            &matches,
            state.command_overlay_selected,
            state.theme,
        );
    }

    let tip_area = Rect {
        x: area.x,
        y: box_area.y + box_height + 1,
        width: area.width,
        height: tip_height,
    };
    let tip_line = Line::from(vec![
        Span::styled("Tip", Style::default().fg(state.theme.warn()).add_modifier(Modifier::BOLD)),
        Span::styled(
            " run jules doctor the first time to check your environment",
            Style::default().fg(state.theme.faint()),
        ),
    ]);
    Paragraph::new(tip_line)
        .alignment(Alignment::Center)
        .render(tip_area, frame.buffer_mut());
}

fn draw_chat(frame: &mut Frame, area: Rect, state: &AppState) {
    let cols = if state.sidebar_visible {
        Layout::default()
            .direction(Direction::Horizontal)
            .constraints([
                Constraint::Min(1),
                Constraint::Length(2), // transparent 2-column gap between main and sidebar
                Constraint::Length(40),
            ])
            .split(area)
    } else {
        Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Min(1)])
            .split(area)
    };

    // 2-column left margin from the terminal screen edge (user request,
    // 2026-07-21: match OpenCode chat panel margin), aligning both ChatLog
    // and InputBar left accent bars ("┃") at column 2.
    let main_area = Rect {
        x: cols[0].x + 2,
        y: cols[0].y + 1, // 1-line top margin from terminal ceiling
        width: cols[0].width.saturating_sub(2),
        height: cols[0].height.saturating_sub(1),
    };

    let inner_width = main_area.width.saturating_sub(4);
    let input_bar_height = InputBar::probe_height(&state.input, inner_width);
    let input_panel_height = input_bar_height + 1; // + bottom padding row (no top padding)
    let main_rows = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Min(1),
            Constraint::Length(input_panel_height), // input bar panel
            Constraint::Length(1), // 1 blank line below input panel (shifts panel 1 line up)
        ])
        .split(main_area);

    let thread_block = Block::default();
    let thread_inner = thread_block.inner(main_rows[0]);
    frame.render_widget(thread_block, main_rows[0]);
    frame.render_widget(
        ChatLog::new(&state.messages, state.thinking_expanded, state.theme, state.scroll_offset),
        thread_inner,
    );

    // No border on the input bar — solid fill (Solid theme) or nothing
    // (Transparent theme), never a drawn box.
    let input_block = bordered_block(state.theme);
    let input_inner = input_block.inner(main_rows[1]);
    frame.render_widget(input_block, main_rows[1]);
    draw_left_accent_bar(main_rows[1], frame.buffer_mut(), state.theme);
    draw_panel_half_extension(main_rows[1], frame.buffer_mut(), state.theme);


    let input_bar = InputBar {
        input: &state.input,
        cursor_pos: state.cursor_pos,
        placeholder: "Ask anything…",
        mode: "chat",
        model: &state.active_model,
        provider: &state.active_provider,
        hint: "",
        prompt_char: "›",
    };
    frame.set_cursor_position(input_bar.get_cursor_position(input_inner));
    input_bar.render_themed(input_inner, frame.buffer_mut(), state.theme);

    let matches = state.command_overlay_matches();
    if !matches.is_empty() {
        let overlay_height = (matches.len() as u16 + 2).min(12);
        let overlay_area = Rect {
            x: main_rows[1].x,
            y: main_rows[1].y.saturating_sub(overlay_height),
            width: main_rows[1].width,
            height: overlay_height,
        };
        draw_command_overlay(
            overlay_area,
            frame.buffer_mut(),
            &matches,
            state.command_overlay_selected,
            state.theme,
        );
    }



    if state.sidebar_visible {
        let mut sidebar_style = Style::default();
        if let Some(bg) = state.theme.panel_bg() {
            sidebar_style = sidebar_style.bg(bg);
        }
        let sidebar_area = Rect {
            x: cols[2].x,
            y: cols[2].y,
            width: cols[2].width,
            height: cols[2].height + 1,
        };
        let sidebar_block = Block::default()
            .style(sidebar_style)
            .padding(ratatui::widgets::Padding::horizontal(2));
        let sidebar_inner = sidebar_block.inner(sidebar_area);
        frame.render_widget(sidebar_block, sidebar_area);
        frame.render_widget(
            Sidebar {
                state,
                theme: state.theme,
                version: &state.version,
            },
            sidebar_inner,
        );
    }
}
