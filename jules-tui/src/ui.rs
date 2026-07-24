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
use crate::palette;
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
        dim_backdrop(frame.buffer_mut(), area, state.theme);
        draw_theme_picker(frame, area, state);
    }
    if state.models_overlay_visible {
        dim_backdrop(frame.buffer_mut(), area, state.theme);
        draw_models_picker(frame, area, state);
    }
    if state.provider_overlay_visible {
        dim_backdrop(frame.buffer_mut(), area, state.theme);
        draw_provider_picker(frame, area, state);
    }
}

/// Darkens every cell already painted on screen by blending its
/// foreground/background colors toward `theme.void()` — kept as a
/// utility for future full-screen popups; unused by the `/models`
/// picker, which now anchors above the input bar like the `/` command
/// overlay instead of dimming the whole screen (user request,
/// 2026-07-21: match the `/` overlay exactly, no backdrop).
#[allow(dead_code)]
fn dim_backdrop(buf: &mut ratatui::buffer::Buffer, area: Rect, theme: palette::Theme) {
    use ratatui::style::Color;

    let void = theme.void();
    let Color::Rgb(vr, vg, vb) = void else { return };

    let blend = |c: Color| -> Color {
        match c {
            Color::Rgb(r, g, b) => {
                let mix = |c: u8, v: u8| -> u8 { ((c as u16 * 45 + v as u16 * 55) / 100) as u8 };
                Color::Rgb(mix(r, vr), mix(g, vg), mix(b, vb))
            }
            other => other,
        }
    };

    for y in area.y..area.y + area.height {
        for x in area.x..area.x + area.width {
            if let Some(cell) = buf.cell_mut((x, y)) {
                let style = cell.style();
                let mut new_style = Style::default();
                if let Some(fg) = style.fg {
                    new_style = new_style.fg(blend(fg));
                }
                if let Some(bg) = style.bg {
                    new_style = new_style.bg(blend(bg));
                }
                cell.set_style(new_style);
            }
        }
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

/// `/models` picker: polished model selector styled matching the `/` command overlay
/// (`draw_command_overlay`): side `┃` accent bars, theme field background, aligned margins,
/// Spanish typography, and keyboard controls footer.
fn draw_models_picker(frame: &mut Frame, area: Rect, state: &AppState) {
    use crate::models::{filtered_rows, get_provider_icon};
    use ratatui::widgets::{List, ListItem, ListState, Paragraph};

    let theme = state.theme;
    let rows = filtered_rows(&state.models_overlay_query);

    let popup_width = 60.min(area.width.saturating_sub(2));
    let popup_height = 25.min(area.height.saturating_sub(2));

    let popup_area = Rect {
        x: area.x + (area.width.saturating_sub(popup_width)) / 2,
        y: area.y + (area.height.saturating_sub(popup_height)) / 2,
        width: popup_width,
        height: popup_height,
    };

    let bg = theme.panel_bg().unwrap_or(theme.void());
    let highlight_bg = theme.field_bg().unwrap_or(theme.void());
    let buf = frame.buffer_mut();

    // 1. Fill popup_area with solid theme background color (borderless)
    let fill_style = Style::default().bg(bg).fg(theme.text());
    for row_y in popup_area.y..popup_area.y + popup_area.height {
        for col_x in popup_area.x..popup_area.x + popup_area.width {
            if let Some(cell) = buf.cell_mut((col_x, row_y)) {
                cell.set_symbol(" ");
                cell.set_style(fill_style);
            }
        }
    }

    if popup_area.width < 10 || popup_area.height < 6 {
        return;
    }

    // 3. Inner layout padding (1 col left/right, 1 row top/bottom)
    let content_area = Rect {
        x: popup_area.x + 1,
        y: popup_area.y + 1,
        width: popup_area.width.saturating_sub(2),
        height: popup_area.height.saturating_sub(2),
    };

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1), // Header title
            Constraint::Length(1), // Spacer
            Constraint::Length(1), // Search bar
            Constraint::Length(1), // Spacer
            Constraint::Min(4),    // Model list
            Constraint::Length(1), // Footer navigation
        ])
        .split(content_area);

    let header_area = chunks[0];
    let search_area = Rect {
        x: chunks[2].x + 1,
        y: chunks[2].y,
        width: chunks[2].width.saturating_sub(2),
        height: chunks[2].height,
    };
    let list_area = Rect {
        x: chunks[4].x + 1,
        y: chunks[4].y,
        width: chunks[4].width.saturating_sub(2),
        height: chunks[4].height,
    };
    let footer_area = chunks[5];

    // 4. Header: "Select model" on left, "esc" on right
    let gap_title = (header_area.width as usize).saturating_sub(15);
    Paragraph::new(Line::from(vec![
        Span::styled("Select model", Style::default().fg(theme.text()).add_modifier(Modifier::BOLD)),
        Span::raw(" ".repeat(gap_title)),
        Span::styled("esc", Style::default().fg(theme.faint())),
    ]))
    .render(header_area, buf);

    // 5. Search bar with subtle highlighted background and 1-space margin
    let search_placeholder = if state.models_overlay_query.is_empty() {
        Span::styled(" Search", Style::default().fg(theme.faint()))
    } else {
        Span::styled(format!(" {}▏", state.models_overlay_query), Style::default().fg(theme.text()))
    };

    let search_fill = Style::default().bg(highlight_bg);
    for col_x in search_area.x..search_area.x + search_area.width {
        if let Some(cell) = buf.cell_mut((col_x, search_area.y)) {
            cell.set_style(search_fill);
        }
    }

    Paragraph::new(Line::from(vec![search_placeholder])).render(search_area, buf);

    // 6. Build List Items
    let mut items: Vec<ListItem> = Vec::new();
    let mut selectable_item_visual_indices: Vec<usize> = Vec::new();

    if state.models_overlay_query.is_empty() && !state.active_model.is_empty() {
        // Recent Section
        items.push(ListItem::new(Line::from(vec![
            Span::styled(" Recent", Style::default().fg(theme.faint()).add_modifier(Modifier::BOLD)),
        ])));
        let active_icon = get_provider_icon(&state.active_provider);
        let active_left = format!(" ● {} {}", active_icon, state.active_model);
        let active_provider = format!(" {}", state.active_provider);
        let free_tag = "Free";
        let gap = (list_area.width as usize)
            .saturating_sub(active_left.chars().count())
            .saturating_sub(active_provider.chars().count())
            .saturating_sub(free_tag.len())
            .saturating_sub(1)
            .max(1);

        let active_line = Line::from(vec![
            Span::styled(active_left, Style::default().fg(theme.text()).add_modifier(Modifier::BOLD)),
            Span::styled(active_provider, Style::default().fg(theme.faint())),
            Span::raw(" ".repeat(gap)),
            Span::styled(free_tag, Style::default().fg(theme.faint())),
            Span::raw(" "),
        ]);
        items.push(ListItem::new(active_line));
        items.push(ListItem::new(Line::from(vec![
            Span::styled(" ───────────────────────────────────────────", Style::default().fg(theme.faint())),
        ])));
    }

    let mut current_provider = "";
    for row in rows.iter() {
        if row.provider != current_provider {
            if !items.is_empty() {
                items.push(ListItem::new(Line::from(""))); // Blank line space between provider groups
            }
            current_provider = row.provider;
            items.push(ListItem::new(Line::from(vec![
                Span::styled(
                    format!(" {} {}", row.icon, row.provider),
                    Style::default().fg(theme.faint()).add_modifier(Modifier::BOLD),
                ),
            ])));
        }

        let is_active = row.model.name == state.active_model && row.provider == state.active_provider;
        let marker = if is_active { "● " } else { "  " };
        let free_text = if row.model.free { "Free" } else { "" };
        let model_left = format!(" {marker}{}", row.model.name);
        let gap = (list_area.width as usize)
            .saturating_sub(model_left.chars().count())
            .saturating_sub(free_text.len())
            .saturating_sub(1)
            .max(1);

        let line = Line::from(vec![
            Span::styled(model_left, Style::default().fg(theme.text())),
            Span::raw(" ".repeat(gap)),
            Span::styled(free_text, Style::default().fg(theme.faint())),
            Span::raw(" "),
        ]);

        selectable_item_visual_indices.push(items.len());
        items.push(ListItem::new(line));
    }

    if rows.is_empty() {
        items.push(ListItem::new(Line::from(vec![
            Span::styled(" No models found", Style::default().fg(theme.faint())),
        ])));
    }

    // 7. Render List with full-row bar highlight matching the / command overlay
    let list = List::new(items)
        .style(Style::default().bg(bg))
        .highlight_style(
            Style::default()
                .fg(theme.text())
                .add_modifier(Modifier::BOLD)
                .bg(highlight_bg),
        );

    let mut list_state = ListState::default();
    if !selectable_item_visual_indices.is_empty() {
        let sel = state.models_overlay_selected.min(selectable_item_visual_indices.len() - 1);
        list_state.select(Some(selectable_item_visual_indices[sel]));
    }

    ratatui::widgets::StatefulWidget::render(list, list_area, buf, &mut list_state);

    // 8. Footer navigation matching exact OpenCode mockup
    let footer_text = Line::from(vec![
        Span::styled("Connect provider ", Style::default().fg(theme.faint())),
        Span::styled("ctrl+a", Style::default().fg(theme.text())),
        Span::raw("   "),
        Span::styled("Favorite ", Style::default().fg(theme.faint())),
        Span::styled("ctrl+f", Style::default().fg(theme.text())),
    ]);
    Paragraph::new(footer_text)
        .alignment(Alignment::Center)
        .render(footer_area, buf);
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
            Constraint::Min(1),    // Chat thread log
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

fn draw_provider_picker(frame: &mut Frame, area: Rect, state: &AppState) {
    use crate::providers::{is_key_configured, AuthKind, PROVIDERS};
    use ratatui::widgets::{List, ListItem, ListState, Paragraph};

    let theme = state.theme;
    let popup_width = 72.min(area.width.saturating_sub(2));
    let popup_height = 26.min(area.height.saturating_sub(2));

    let popup_area = Rect {
        x: area.x + (area.width.saturating_sub(popup_width)) / 2,
        y: area.y + (area.height.saturating_sub(popup_height)) / 2,
        width: popup_width,
        height: popup_height,
    };

    let bg = theme.panel_bg().unwrap_or(theme.void());
    let highlight_bg = theme.field_bg().unwrap_or(theme.void());
    let buf = frame.buffer_mut();

    let fill_style = Style::default().bg(bg).fg(theme.text());
    for row_y in popup_area.y..popup_area.y + popup_area.height {
        for col_x in popup_area.x..popup_area.x + popup_area.width {
            if let Some(cell) = buf.cell_mut((col_x, row_y)) {
                cell.set_style(fill_style);
            }
        }
    }

    for row_y in popup_area.y..popup_area.y + popup_area.height {
        if let Some(cell) = buf.cell_mut((popup_area.x, row_y)) {
            cell.set_symbol("┃");
            cell.set_style(Style::default().fg(theme.accent()).bg(bg));
        }
        if let Some(cell) = buf.cell_mut((popup_area.x + popup_area.width - 1, row_y)) {
            cell.set_symbol("┃");
            cell.set_style(Style::default().fg(theme.accent()).bg(bg));
        }
    }

    let inner_area = Rect {
        x: popup_area.x + 2,
        y: popup_area.y + 1,
        width: popup_area.width.saturating_sub(4),
        height: popup_area.height.saturating_sub(2),
    };

    let title_line = Line::from(vec![Span::styled(
        "Configuración de Proveedores & API Keys",
        Style::default()
            .fg(theme.amber())
            .add_modifier(Modifier::BOLD),
    )]);
    Paragraph::new(title_line).render(
        Rect {
            x: inner_area.x,
            y: inner_area.y,
            width: inner_area.width,
            height: 1,
        },
        buf,
    );

    // MODE 1: Inputting API Key text
    if state.provider_overlay_input_mode {
        if let Some(item) = PROVIDERS.get(state.provider_overlay_selected) {
            let prompt_y = inner_area.y + 3;
            let prompt_text = format!(
                "Ingresá la API Key para {} (variable: {}):",
                item.name, item.env_var
            );
            Paragraph::new(Line::from(Span::styled(
                prompt_text,
                Style::default()
                    .fg(theme.text())
                    .add_modifier(Modifier::BOLD),
            )))
            .render(
                Rect {
                    x: inner_area.x,
                    y: prompt_y,
                    width: inner_area.width,
                    height: 1,
                },
                buf,
            );

            let input_y = prompt_y + 2;
            let input_str = &state.provider_overlay_key_input;
            let masked = if input_str.len() > 12 {
                format!(
                    "{}...{}",
                    &input_str[..4],
                    &input_str[input_str.len() - 4..]
                )
            } else {
                input_str.clone()
            };

            let input_rect = Rect {
                x: inner_area.x,
                y: input_y,
                width: inner_area.width,
                height: 1,
            };
            let input_style = Style::default().fg(theme.text()).bg(highlight_bg);
            Block::default().style(input_style).render(input_rect, buf);

            let input_line = Line::from(vec![Span::styled(
                format!(" {}▏", masked),
                Style::default()
                    .fg(theme.amber())
                    .add_modifier(Modifier::BOLD),
            )]);
            Paragraph::new(input_line).render(input_rect, buf);

            let footer_y = inner_area.y + inner_area.height.saturating_sub(1);
            let footer = Line::from(vec![
                Span::styled(
                    "Enter ",
                    Style::default()
                        .fg(theme.good())
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled(
                    "Guardar en ~/.jules/.env  •  ",
                    Style::default().fg(theme.faint()),
                ),
                Span::styled(
                    "Esc ",
                    Style::default()
                        .fg(theme.amber())
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled("Volver", Style::default().fg(theme.faint())),
            ]);
            Paragraph::new(footer).render(
                Rect {
                    x: inner_area.x,
                    y: footer_y,
                    width: inner_area.width,
                    height: 1,
                },
                buf,
            );
        }
        return;
    }

    // MODE 2: Action sub-menu for selected provider
    if state.provider_overlay_sub_menu {
        if let Some(item) = PROVIDERS.get(state.provider_overlay_selected) {
            let is_configured = is_key_configured(item.env_var);

            let header_y = inner_area.y + 2;
            let header_line = Line::from(vec![
                Span::styled(format!("{} ", item.icon), Style::default().fg(theme.amber())),
                Span::styled(format!("Opciones para: {}", item.name), Style::default().fg(theme.text()).add_modifier(Modifier::BOLD)),
            ]);
            Paragraph::new(header_line).render(
                Rect { x: inner_area.x, y: header_y, width: inner_area.width, height: 1 },
                buf,
            );

            let status_y = header_y + 1;
            let status_text = match item.auth_kind {
                AuthKind::ApiKey => if is_configured {
                    Span::styled("Estado: ✓ API Key Vinculada", Style::default().fg(theme.good()))
                } else {
                    Span::styled("Estado: ○ Sin API Key Vinculada", Style::default().fg(theme.amber()))
                },
                AuthKind::OAuth => Span::styled("Estado: ⚡ OAuth Login", Style::default().fg(theme.accent())),
                AuthKind::None => Span::styled("Estado: ● Proveedor Libre / Local", Style::default().fg(theme.faint())),
            };
            Paragraph::new(Line::from(status_text)).render(
                Rect { x: inner_area.x, y: status_y, width: inner_area.width, height: 1 },
                buf,
            );

            let actions_y = status_y + 3;
            let actions_list_area = Rect {
                x: inner_area.x,
                y: actions_y,
                width: inner_area.width,
                height: 5,
            };

            let action_items = vec![
                ListItem::new(Line::from(vec![
                    Span::styled("  1. ", Style::default().fg(theme.amber())),
                    Span::styled("Activar como proveedor principal", Style::default().fg(theme.text())),
                ])),
                ListItem::new(Line::from(vec![
                    Span::styled("  2. ", Style::default().fg(theme.amber())),
                    Span::styled(
                        if is_configured { "Modificar API Key guardada" } else { "Vincular / Agregar API Key" },
                        Style::default().fg(theme.text()),
                    ),
                ])),
                ListItem::new(Line::from(vec![
                    Span::styled("  3. ", Style::default().fg(theme.amber())),
                    Span::styled("Borrar API Key vinculada", Style::default().fg(if is_configured { theme.text() } else { theme.dim() })),
                ])),
            ];

            let list = List::new(action_items).highlight_style(
                Style::default()
                    .fg(theme.text())
                    .bg(highlight_bg)
                    .add_modifier(Modifier::BOLD),
            );

            let mut list_state = ListState::default();
            list_state.select(Some(state.provider_overlay_action_selected));
            ratatui::widgets::StatefulWidget::render(list, actions_list_area, buf, &mut list_state);

            let footer_y = inner_area.y + inner_area.height.saturating_sub(1);
            let footer = Line::from(vec![
                Span::styled("↑/↓ ", Style::default().fg(theme.amber()).add_modifier(Modifier::BOLD)),
                Span::styled("Elegir acción  •  ", Style::default().fg(theme.faint())),
                Span::styled("Enter ", Style::default().fg(theme.amber()).add_modifier(Modifier::BOLD)),
                Span::styled("Confirmar  •  ", Style::default().fg(theme.faint())),
                Span::styled("Esc ", Style::default().fg(theme.amber()).add_modifier(Modifier::BOLD)),
                Span::styled("Volver a lista", Style::default().fg(theme.faint())),
            ]);
            Paragraph::new(footer).render(
                Rect { x: inner_area.x, y: footer_y, width: inner_area.width, height: 1 },
                buf,
            );
        }
        return;
    }

    // MODE 3: Main Provider List
    let list_area = Rect {
        x: inner_area.x,
        y: inner_area.y + 2,
        width: inner_area.width,
        height: inner_area.height.saturating_sub(5),
    };

    let items: Vec<ListItem> = PROVIDERS
        .iter()
        .map(|item| {
            let is_configured = is_key_configured(item.env_var);
            let is_active = state.active_provider.eq_ignore_ascii_case(item.id);

            let active_tag = if is_active {
                Span::styled(" [ACTIVO]", Style::default().fg(theme.amber()).add_modifier(Modifier::BOLD))
            } else {
                Span::raw("")
            };

            let status_span = match item.auth_kind {
                AuthKind::ApiKey => {
                    if is_configured {
                        Span::styled(" [✓ VINCULADA]", Style::default().fg(theme.good()))
                    } else {
                        Span::styled(
                            " [○ NO VINCULADA]",
                            Style::default().fg(theme.amber()),
                        )
                    }
                }
                AuthKind::OAuth => Span::styled(" [⚡ OAUTH]", Style::default().fg(theme.accent())),
                AuthKind::None => Span::styled(" [● LIBRE]", Style::default().fg(theme.faint())),
            };

            ListItem::new(Line::from(vec![
                Span::styled(format!("{} ", item.icon), Style::default().fg(theme.amber())),
                Span::styled(
                    format!("{:<18}", item.name),
                    Style::default()
                        .fg(theme.text())
                        .add_modifier(Modifier::BOLD),
                ),
                status_span,
                active_tag,
            ]))
        })
        .collect();

    let list = List::new(items).highlight_style(
        Style::default()
            .fg(theme.text())
            .bg(highlight_bg)
            .add_modifier(Modifier::BOLD),
    );

    let mut list_state = ListState::default();
    list_state.select(Some(state.provider_overlay_selected));
    ratatui::widgets::StatefulWidget::render(list, list_area, buf, &mut list_state);

    if let Some(item) = PROVIDERS.get(state.provider_overlay_selected) {
        let desc_y = inner_area.y + inner_area.height.saturating_sub(2);
        let desc_line = Line::from(vec![
            Span::styled("Info: ", Style::default().fg(theme.amber())),
            Span::styled(item.description, Style::default().fg(theme.dim())),
        ]);
        Paragraph::new(desc_line).render(
            Rect {
                x: inner_area.x,
                y: desc_y,
                width: inner_area.width,
                height: 1,
            },
            buf,
        );
    }

    if let Some(status_msg) = &state.provider_overlay_status_msg {
        let msg_y = inner_area.y + inner_area.height.saturating_sub(3);
        Paragraph::new(Line::from(Span::styled(
            status_msg.as_str(),
            Style::default().fg(theme.good()),
        )))
        .render(
            Rect {
                x: inner_area.x,
                y: msg_y,
                width: inner_area.width,
                height: 1,
            },
            buf,
        );
    }

    let footer_y = inner_area.y + inner_area.height.saturating_sub(1);
    let footer = Line::from(vec![
        Span::styled(
            "↑/↓ ",
            Style::default()
                .fg(theme.amber())
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled("Navegar  •  ", Style::default().fg(theme.faint())),
        Span::styled(
            "Enter ",
            Style::default()
                .fg(theme.amber())
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled("Opciones  •  ", Style::default().fg(theme.faint())),
        Span::styled(
            "Esc ",
            Style::default()
                .fg(theme.amber())
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled("Cerrar", Style::default().fg(theme.faint())),
    ]);
    Paragraph::new(footer).render(
        Rect {
            x: inner_area.x,
            y: footer_y,
            width: inner_area.width,
            height: 1,
        },
        buf,
    );
}
