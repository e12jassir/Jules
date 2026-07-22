//! Mirrors `.home-box` / `.chat-inputbar` from jules_tui_mockup.html:
//!   solid background --field, NO line-drawn border (per user decision).
//!   prompt "›" in --amber, input text in --text, placeholder in --faint
//!   .statusline: mode (--accent) · model (--text) · provider · hint (right-aligned, --faint)

use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Paragraph, Widget},
};

use crate::palette;

pub struct InputBar<'a> {
    pub input: &'a str,
    pub cursor_pos: usize,
    pub placeholder: &'a str,
    pub mode: &'a str,
    pub model: &'a str,
    pub provider: &'a str,
    pub hint: &'a str,
    pub prompt_char: &'a str,
}

/// Number of terminal rows the input text needs to wrap into, given the
/// available width inside the panel (after the prompt_char + space
/// prefix). Grows the input panel dynamically instead of truncating long
/// text (user report, 2026-07-19: "cuando escribo mucho texto en el input
/// bar se desaparece"). `available_width` should already exclude the
/// "› " prefix (2 columns) — see `prompt_prefix_width()`.
pub fn wrapped_input_rows(input: &str, available_width: u16) -> u16 {
    if available_width == 0 {
        return 1;
    }
    if input.is_empty() {
        return 1;
    }
    // Ratatui's Paragraph wraps by grapheme/word; a simple character-count
    // based estimate matches it closely enough for layout sizing (the
    // same approximation thinking_block.rs already uses for its own
    // height estimate).
    let width = available_width as usize;
    (input.chars().count().max(1)).div_ceil(width).max(1) as u16
}

const PROMPT_PREFIX_WIDTH: u16 = 2; // "› " — prompt_char + space

#[cfg(test)]
mod tests {
    use super::wrapped_input_rows;

    #[test]
    fn empty_input_is_one_row() {
        assert_eq!(wrapped_input_rows("", 40), 1);
    }

    #[test]
    fn short_input_fits_one_row() {
        assert_eq!(wrapped_input_rows("hola", 40), 1);
    }

    #[test]
    fn long_input_wraps_to_multiple_rows() {
        let text = "a".repeat(85); // 85 chars at width 40 -> 3 rows
        assert_eq!(wrapped_input_rows(&text, 40), 3);
    }

    #[test]
    fn zero_width_never_panics() {
        assert_eq!(wrapped_input_rows("anything", 0), 1);
    }
}

impl<'a> InputBar<'a> {
    /// Standalone variant of `height()` usable before constructing a full
    /// `InputBar` (callers in ui.rs need the height to size the panel
    /// Rect *before* they have all the other fields — mode/model/etc —
    /// ready).
    pub fn probe_height(input: &str, panel_width: u16) -> u16 {
        let available = panel_width.saturating_sub(PROMPT_PREFIX_WIDTH).max(1);
        wrapped_input_rows(input, available) + 2
    }

    /// Total panel height this input needs: wrapped text rows + 1 blank
    /// separator row + 1 statusline row. Callers (ui.rs) use this to size
    /// the input panel's Rect before rendering, instead of a fixed
    /// `Constraint::Length(5)`.
    #[allow(dead_code)] // kept as the instance-method form of probe_height for API symmetry
    pub fn height(&self, panel_width: u16) -> u16 {
        Self::probe_height(self.input, panel_width)
    }

    pub fn get_cursor_position(&self, area: Rect) -> (u16, u16) {
        let available = area.width.saturating_sub(PROMPT_PREFIX_WIDTH).max(1) as usize;
        if !self.input.is_empty() {
            let cursor_chars = self.input[..self.cursor_pos.min(self.input.len())].chars().count();
            let row = (cursor_chars / available) as u16;
            let col = (cursor_chars % available) as u16;
            (
                area.x + PROMPT_PREFIX_WIDTH + col,
                area.y + row,
            )
        } else {
            (area.x + PROMPT_PREFIX_WIDTH, area.y)
        }
    }

    pub fn render_themed(self, area: Rect, buf: &mut ratatui::buffer::Buffer, theme: palette::Theme) {
        let available = area.width.saturating_sub(PROMPT_PREFIX_WIDTH).max(1);
        let text_rows = wrapped_input_rows(self.input, available);

        let rows = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(text_rows),
                Constraint::Length(1),
                Constraint::Length(1),
            ])
            .split(area);

        let prompt_area = rows[0];
        let prefix = format!("{} ", self.prompt_char);
        if self.input.is_empty() {
            let line = Line::from(vec![
                Span::styled(prefix, Style::default().fg(theme.amber())),
                Span::styled(self.placeholder, Style::default().fg(theme.faint())),
            ]);
            Paragraph::new(line).render(
                Rect { x: prompt_area.x, y: prompt_area.y, width: prompt_area.width, height: 1 },
                buf,
            );
        } else {
            // First row carries the prompt prefix; subsequent wrapped rows
            // are indented to align under the text (not under the prompt
            // char), matching how most terminal multi-line inputs behave.
            Paragraph::new(Span::styled(prefix.clone(), Style::default().fg(theme.amber())))
                .render(Rect { x: prompt_area.x, y: prompt_area.y, width: PROMPT_PREFIX_WIDTH, height: 1 }, buf);
            let text_area = Rect {
                x: prompt_area.x + PROMPT_PREFIX_WIDTH,
                y: prompt_area.y,
                width: prompt_area.width.saturating_sub(PROMPT_PREFIX_WIDTH),
                height: text_rows,
            };
            Paragraph::new(Span::styled(self.input, Style::default().fg(theme.text())))
                .wrap(ratatui::widgets::Wrap { trim: false })
                .render(text_area, buf);
        }

        // Cursor: locate which wrapped row/column cursor_pos falls into,
        // relative to text_area (same width used for the Paragraph wrap
        // above), so the cursor tracks correctly across multiple rows.
        if !self.input.is_empty() {
            let text_width = prompt_area.width.saturating_sub(PROMPT_PREFIX_WIDTH).max(1) as usize;
            let cursor_chars = self.input[..self.cursor_pos.min(self.input.len())].chars().count();
            let row = (cursor_chars / text_width) as u16;
            let col = (cursor_chars % text_width) as u16;
            let cursor_x = prompt_area.x + PROMPT_PREFIX_WIDTH + col;
            let cursor_y = prompt_area.y + row;
            if cursor_x < prompt_area.x + prompt_area.width && cursor_y < prompt_area.y + prompt_area.height {
                if let Some(cell) = buf.cell_mut((cursor_x, cursor_y)) {
                    cell.set_style(Style::default().bg(theme.accent()).fg(theme.void()));
                }
            }
        } else {
            let cursor_x = prompt_area.x + PROMPT_PREFIX_WIDTH;
            if cursor_x < prompt_area.x + prompt_area.width {
                if let Some(cell) = buf.cell_mut((cursor_x, prompt_area.y)) {
                    cell.set_style(Style::default().bg(theme.accent()).fg(theme.void()));
                }
            }
        }

        // separator row (blank, matches statusline's border-top spacing)
        let _ = rows[1];

        // status line
        let sep = Span::styled(" · ", Style::default().fg(theme.faint()));
        let mut status_spans = vec![
            Span::styled(self.mode, Style::default().fg(theme.accent())),
            sep.clone(),
            Span::styled(self.model, Style::default().fg(theme.text())),
            sep,
            Span::styled(self.provider, Style::default().fg(theme.dim())),
        ];
        let used = self.mode.len() + 3 + self.model.len() + 3 + self.provider.len();
        let hint_len = self.hint.len();
        let total_width = rows[2].width as usize;
        // Bug fix (2026-07-21): narrow terminals (e.g. 79 cols with a wide
        // sidebar) could make `used` alone exceed `total_width`. The old
        // `else` branch unconditionally pushed 2 extra spaces regardless
        // of how much room was actually left, pushing the rendered line
        // past the panel's real width and triggering a ratatui buffer
        // index panic ("index outside of buffer") in Paragraph's
        // LineTruncator. Always compute pad from the *actual* remaining
        // space, saturating to 0 instead of a fixed fallback.
        let pad = total_width
            .saturating_sub(used)
            .saturating_sub(hint_len)
            .min(total_width.saturating_sub(used));
        if pad > 0 {
            status_spans.push(Span::raw(" ".repeat(pad)));
        }
        status_spans.push(Span::styled(self.hint, Style::default().fg(theme.faint())));

        Paragraph::new(Line::from(status_spans)).render(rows[2], buf);
    }
}

/// Solid gray panel matching the "recuadro/panel gris" the user asked for
/// (2026-07-18) — only when `theme` is `Solid`. In `Transparent` theme, no
/// background is painted here at all: the real terminal background shows
/// through. No line-drawn borders in either theme — the panel is delimited
/// purely by its background fill (or nothing) plus internal padding.
pub fn bordered_block(theme: palette::Theme) -> Block<'static> {
    let mut style = Style::default().fg(theme.text());
    if let Some(bg) = theme.field_bg() {
        style = style.bg(bg);
    }
    // Padding inside the panel box: 2 columns on left, 2 on right, 1 on top, 0 on bottom.
    Block::default()
        .style(style)
        .padding(ratatui::widgets::Padding::new(2, 2, 1, 0))
}

pub fn draw_left_accent_bar(outer_area: Rect, buf: &mut ratatui::buffer::Buffer, theme: palette::Theme) {
    if outer_area.width == 0 || outer_area.x == 0 {
        return;
    }
    let line_x = outer_area.x - 1;
    for row_y in outer_area.y..outer_area.y + outer_area.height {
        if let Some(cell) = buf.cell_mut((line_x, row_y)) {
            cell.set_symbol("┃");
            cell.set_style(Style::default().fg(theme.accent()));
        }
    }
    // Hook cleanly with "╹" on the half-extension shadow row below the panel
    let next_row_y = outer_area.y + outer_area.height;
    if next_row_y < buf.area().height {
        if let Some(cell) = buf.cell_mut((line_x, next_row_y)) {
            cell.set_symbol("╹");
            cell.set_style(Style::default().fg(theme.accent()));
        }
    }
}

pub fn draw_panel_half_extension(outer_area: Rect, buf: &mut ratatui::buffer::Buffer, theme: palette::Theme) {
    if outer_area.width == 0 || outer_area.height == 0 {
        return;
    }
    let next_row_y = outer_area.y + outer_area.height;
    if next_row_y >= buf.area().height {
        return;
    }
    if let Some(panel_bg) = theme.field_bg() {
        for col_x in outer_area.x..outer_area.x + outer_area.width {
            if let Some(cell) = buf.cell_mut((col_x, next_row_y)) {
                cell.set_symbol("▀");
                cell.set_style(Style::default().fg(panel_bg));
            }
        }
    }
}



/// Slash command overlay: a small popup listing commands matching what
/// the user has typed after `/`, drawn just above the input panel (user
/// request, 2026-07-19 — ported from the Python/Textual prototype's
/// `#cmd-overlay`, which is now obsolete). `selected` highlights one row
/// for keyboard navigation (Up/Down to move, Tab/Enter to accept).
pub fn draw_command_overlay(
    area: Rect,
    buf: &mut ratatui::buffer::Buffer,
    matches: &[&crate::commands::SlashCommand],
    selected: Option<usize>,
    theme: palette::Theme,
) {
    use ratatui::widgets::{List, ListItem, ListState};

    if matches.is_empty() || area.height == 0 || area.width == 0 {
        return;
    }

    // Solid background fill — paint every cell explicitly with a space so
    // that whatever was rendered underneath (chat log, ASCII art, etc.)
    // is guaranteed to be overwritten before the list items are drawn.
    let bg = theme.field_bg().unwrap_or(ratatui::style::Color::Reset);
    let fill_style = Style::default().bg(bg);
    for row_y in area.y..area.y + area.height {
        for col_x in area.x..area.x + area.width {
            if let Some(cell) = buf.cell_mut((col_x, row_y)) {
                cell.set_symbol(" ");
                cell.set_style(fill_style);
            }
        }
    }

    // ┃ accent borders drawn OUTSIDE the background rect — same pattern
    // as draw_left_accent_bar — so the left border lands at the same
    // column as the input panel's accent bar (area.x - 1).
    // The border cells include `bg` in their style to avoid a color
    // discontinuity where the fill meets the ┃.
    let border_style = Style::default().fg(theme.faint());
    let buf_width = buf.area().width;
    let buf_height = buf.area().height;
    for row_y in area.y..area.y + area.height {
        // Left border — one column to the left of the fill area.
        if area.x > 0 {
            if let Some(cell) = buf.cell_mut((area.x - 1, row_y)) {
                cell.set_symbol("┃");
                cell.set_style(border_style);
            }
        }
        // Right border — one column past the right edge of the fill area.
        let right_x = area.x + area.width;
        if right_x < buf_width {
            if let Some(cell) = buf.cell_mut((right_x, row_y)) {
                cell.set_symbol("┃");
                cell.set_style(border_style);
            }
        }
        let _ = buf_height; // suppress unused warning
    }

    // Inner content area: 1 col gap on each side (the ┃ is already
    // outside the fill rect) and 1 row of vertical padding top/bottom.
    if area.width < 4 || area.height < 3 {
        return;
    }
    let inner = Rect {
        x: area.x + 1,
        y: area.y + 1,
        width: area.width.saturating_sub(2),
        height: area.height.saturating_sub(2),
    };

    let item_style = Style::default().bg(bg);
    let items: Vec<ListItem> = matches
        .iter()
        .map(|cmd| {
            ListItem::new(Line::from(vec![
                Span::styled(format!("/{:<12}", cmd.name), Style::default().fg(theme.amber())),
                Span::styled(cmd.description, Style::default().fg(theme.faint())),
            ]))
            .style(item_style)
        })
        .collect();

    // Highlight: slightly lighter background + bold text so the selected
    // row is clearly distinct without losing the amber command name color.
    let highlight_bg = theme.panel_bg().unwrap_or(theme.void());
    let list = List::new(items)
        .style(Style::default().bg(bg))
        .highlight_style(
            Style::default()
                .fg(theme.text())
                .add_modifier(Modifier::BOLD)
                .bg(highlight_bg),
        );

    let mut list_state = ListState::default();
    list_state.select(selected.or(Some(0)));

    ratatui::widgets::StatefulWidget::render(list, inner, buf, &mut list_state);
}
