//! Mirrors `.thread .msg` from jules_tui_mockup.html:
//!   .who        — 48px-equivalent right-aligned label, --faint (--amber for jules)
//!   .bubble     — message body, --text (dimmer for user: #b7bccb-ish -> --dim)
//!   .toolblock  — thinking block (see thinking_block.rs)
//!   .tagline-small — trailing meta line with a small colored square

use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Paragraph, Widget, Wrap},
};

use crate::app::{ChatMessage, Role};
use crate::palette;
use crate::widgets::thinking_block::ThinkingBlock;

pub struct ChatLog<'a> {
    pub messages: &'a [ChatMessage],
    pub thinking_expanded: bool,
    pub theme: palette::Theme,
    /// Rows scrolled up from the bottom (0 = pinned to latest). Clamped
    /// against total content height during render, since only this widget
    /// knows the actual rendered height of each message.
    pub scroll_offset: u16,
}

impl<'a> ChatLog<'a> {
    pub fn new(
        messages: &'a [ChatMessage],
        thinking_expanded: bool,
        theme: palette::Theme,
        scroll_offset: u16,
    ) -> Self {
        Self {
            messages,
            thinking_expanded,
            theme,
            scroll_offset,
        }
    }
}

const WHO_WIDTH: u16 = 8;

impl<'a> Widget for ChatLog<'a> {
    fn render(self, area: Rect, buf: &mut ratatui::buffer::Buffer) {
        let bubble_width = area.width.saturating_sub(WHO_WIDTH + 2);

        // Total content height across all messages (each message's own
        // height + 1 blank separator row), used to clamp scroll_offset so
        // it can never scroll past the actual top of the transcript.
        let total_height: u32 = self
            .messages
            .iter()
            .map(|m| message_height(m, bubble_width, self.thinking_expanded, self.theme) as u32 + 1)
            .sum();
        let viewport_height = area.height as u32;
        let max_scroll = total_height.saturating_sub(viewport_height) as u16;
        let scroll_offset = self.scroll_offset.min(max_scroll);

        // viewport_top is measured from transcript line 0.
        // scroll_offset = 0 means pinned to bottom (viewport_top = max_scroll).
        // scroll_offset > 0 means scrolled up towards top.
        let viewport_top = (max_scroll - scroll_offset) as i64;
        let viewport_bottom = viewport_top + area.height as i64;

        let mut absolute_y: i64 = 0;

        for msg in self.messages {
            let msg_height = message_height(msg, bubble_width, self.thinking_expanded, self.theme);
            let msg_top = absolute_y;
            let msg_bottom = absolute_y + msg_height as i64;
            absolute_y = msg_bottom + 1; // blank line between messages

            if msg_bottom <= viewport_top || msg_top >= viewport_bottom {
                continue; // fully outside the visible viewport
            }

            // Render message into offscreen temp_buf, then copy visible lines into viewport
            let temp_rect = Rect {
                x: 0,
                y: 0,
                width: area.x + area.width,
                height: msg_height,
            };
            let mut temp_buf = ratatui::buffer::Buffer::empty(temp_rect);
            let msg_draw_area = Rect {
                x: area.x,
                y: 0,
                width: area.width,
                height: msg_height,
            };

            render_message(
                msg,
                msg_draw_area,
                &mut temp_buf,
                self.thinking_expanded,
                self.theme,
            );

            let screen_y = area.y as i64 + (msg_top - viewport_top);

            for row_in_msg in 0..msg_height {
                let target_y = screen_y + row_in_msg as i64;
                if target_y >= area.y as i64 && target_y < (area.y + area.height) as i64 {
                    for x in 0..(area.x + area.width) {
                        if let Some(cell) = temp_buf.cell((x, row_in_msg)) {
                            if let Some(target_cell) = buf.cell_mut((x, target_y as u16)) {
                                *target_cell = cell.clone();
                            }
                        }
                    }
                }
            }
        }
    }
}

fn render_message(
    msg: &ChatMessage,
    area: Rect,
    buf: &mut ratatui::buffer::Buffer,
    thinking_expanded: bool,
    theme: palette::Theme,
) {
    // User messages get a solid background block (in Solid theme only) —
    // Jules' replies never do, in either theme. Confirmed with user, 2026-07-18.
    let msg_bg = match msg.role {
        Role::User => theme.user_message_bg(),
        Role::Jules => theme.jules_message_bg(),
    };
    if let Some(bg) = msg_bg {
        let block = Block::default().style(Style::default().bg(bg));
        block.render(area, buf);
    }

    // Left accent bar drawn directly adjacent to the left edge of user messages (1 column to the left),
    // sitting outside the message bubble without sharing its background color.
    if matches!(msg.role, Role::User) && area.x >= 1 {
        let line_x = area.x - 1;
        for row_y in area.y..area.y + area.height {
            if let Some(cell) = buf.cell_mut((line_x, row_y)) {
                cell.set_symbol("┃");
                cell.set_style(Style::default().fg(theme.accent()));
            }
        }
    }

    // 2 columns of blank margin inside the message bubble
    let body_area = Rect {
        x: area.x + 2,
        y: area.y,
        width: area.width.saturating_sub(2),
        height: area.height,
    };

    if matches!(msg.role, Role::User) {
        if body_area.height >= 2 {
            let center_y = body_area.y + 1;
            let body_line = Paragraph::new(Line::from(Span::styled(
                msg.body.as_str(),
                Style::default().fg(theme.dim()),
            )))
            .wrap(Wrap { trim: true });
            body_line.render(
                Rect {
                    x: body_area.x,
                    y: center_y,
                    width: body_area.width,
                    height: 1,
                },
                buf,
            );
        }
        return;
    }

    let mut y = body_area.y;

    if let Some(thinking) = &msg.thinking {
        let block = ThinkingBlock::new(thinking, thinking_expanded, theme);
        let h = block.height(body_area.width).min(body_area.height);
        let block_area = Rect {
            x: body_area.x,
            y,
            width: body_area.width,
            height: h,
        };
        block.render(block_area, buf);
        y += h;
    }

    let body_color = match msg.role {
        Role::User => theme.dim(),
        Role::Jules => theme.text(),
    };
    let remaining_h = body_area.y + body_area.height - y;
    if remaining_h > 0 {
        let body_area_rect = Rect {
            x: body_area.x,
            y,
            width: body_area.width,
            height: remaining_h,
        };
        let lines = parse_markdown_lines(&msg.body, theme);
        let body_line = Paragraph::new(lines).wrap(Wrap { trim: false });
        let body_h = wrapped_height(&msg.body, body_area.width).min(remaining_h);
        body_line.render(
            Rect {
                x: body_area_rect.x,
                y: body_area_rect.y,
                width: body_area_rect.width,
                height: body_h,
            },
            buf,
        );
        y += body_h;
    }

    if let Some(tagline) = &msg.tagline {
        let remaining_h = body_area.y + body_area.height - y;
        if remaining_h > 0 {
            let tagline_area = Rect {
                x: body_area.x,
                y,
                width: body_area.width,
                height: 1,
            };
            let line = Line::from(vec![
                Span::styled("■ ", Style::default().fg(theme.good())),
                Span::styled(
                    tagline.as_str(),
                    Style::default()
                        .fg(theme.faint())
                        .add_modifier(Modifier::DIM),
                ),
            ]);
            Paragraph::new(line).render(tagline_area, buf);
        }
    }
}

fn parse_markdown_lines(text: &str, theme: palette::Theme) -> Vec<Line<'static>> {
    let mut result = Vec::new();
    let mut in_code_block = false;

    for raw_line in text.lines() {
        let line = raw_line.trim_end();
        if line.trim_start().starts_with("```") {
            in_code_block = !in_code_block;
            continue;
        }

        if in_code_block {
            result.push(Line::from(vec![
                Span::styled("  │ ", Style::default().fg(theme.accent())),
                Span::styled(line.to_string(), Style::default().fg(theme.amber())),
            ]));
            continue;
        }

        if line.starts_with("### ") {
            let content = &line[4..];
            result.push(Line::from(Span::styled(
                format!("### {}", content),
                Style::default()
                    .fg(theme.accent())
                    .add_modifier(Modifier::BOLD),
            )));
        } else if line.starts_with("## ") {
            let content = &line[3..];
            result.push(Line::from(Span::styled(
                format!("## {}", content),
                Style::default()
                    .fg(theme.amber())
                    .add_modifier(Modifier::BOLD),
            )));
        } else if line.starts_with("# ") {
            let content = &line[2..];
            result.push(Line::from(Span::styled(
                format!("# {}", content),
                Style::default()
                    .fg(theme.accent())
                    .add_modifier(Modifier::BOLD),
            )));
        } else if line.starts_with("- ") || line.starts_with("* ") {
            let content = &line[2..];
            let spans = parse_inline_markdown(content, theme);
            let mut line_spans = vec![Span::styled("• ", Style::default().fg(theme.accent()))];
            line_spans.extend(spans);
            result.push(Line::from(line_spans));
        } else if line.trim_start().starts_with("\\[") && line.trim_end().ends_with("\\]") {
            let trimmed = line.trim();
            let eq = &trimmed[2..trimmed.len() - 2];
            result.push(Line::from(vec![
                Span::styled("  ", Style::default()),
                Span::styled(
                    eq.trim().to_string(),
                    Style::default()
                        .fg(theme.accent())
                        .add_modifier(Modifier::BOLD),
                ),
            ]));
        } else {
            let spans = parse_inline_markdown(line, theme);
            result.push(Line::from(spans));
        }
    }

    if result.is_empty() {
        result.push(Line::from(Span::styled(
            "",
            Style::default().fg(theme.text()),
        )));
    }

    result
}

fn parse_inline_markdown(line: &str, theme: palette::Theme) -> Vec<Span<'static>> {
    let mut spans = Vec::new();
    let mut remaining = line;

    while !remaining.is_empty() {
        if let Some(start) = remaining.find('`') {
            let after = &remaining[start + 1..];
            if let Some(end) = after.find('`') {
                if start > 0 {
                    spans.extend(parse_bold_and_italic(&remaining[..start], theme));
                }
                let code_text = &after[..end];
                spans.push(Span::styled(
                    code_text.to_string(),
                    Style::default().fg(theme.amber()),
                ));
                remaining = &after[end + 1..];
                continue;
            }
        }

        spans.extend(parse_bold_and_italic(remaining, theme));
        break;
    }

    if spans.is_empty() {
        spans.push(Span::styled(
            line.to_string(),
            Style::default().fg(theme.text()),
        ));
    }

    spans
}

fn parse_bold_and_italic(text: &str, theme: palette::Theme) -> Vec<Span<'static>> {
    let mut spans = Vec::new();
    let mut remaining = text;

    while !remaining.is_empty() {
        if let Some(start) = remaining.find("**") {
            if start > 0 {
                spans.extend(parse_italic(&remaining[..start], theme));
            }
            let after_first = &remaining[start + 2..];
            if let Some(end) = after_first.find("**") {
                let bold_text = &after_first[..end];
                spans.push(Span::styled(
                    bold_text.to_string(),
                    Style::default()
                        .fg(theme.text())
                        .add_modifier(Modifier::BOLD),
                ));
                remaining = &after_first[end + 2..];
            } else {
                spans.extend(parse_italic(&remaining[start..], theme));
                break;
            }
        } else {
            spans.extend(parse_italic(remaining, theme));
            break;
        }
    }

    spans
}

fn parse_italic(text: &str, theme: palette::Theme) -> Vec<Span<'static>> {
    let mut spans = Vec::new();
    let mut remaining = text;

    while !remaining.is_empty() {
        if let Some(start) = remaining.find('*') {
            if start > 0 {
                spans.push(Span::styled(
                    remaining[..start].to_string(),
                    Style::default().fg(theme.text()),
                ));
            }
            let after = &remaining[start + 1..];
            if let Some(end) = after.find('*') {
                let italic_text = &after[..end];
                spans.push(Span::styled(
                    italic_text.to_string(),
                    Style::default()
                        .fg(theme.text())
                        .add_modifier(Modifier::ITALIC),
                ));
                remaining = &after[end + 1..];
            } else {
                spans.push(Span::styled(
                    remaining[start..].to_string(),
                    Style::default().fg(theme.text()),
                ));
                break;
            }
        } else {
            spans.push(Span::styled(
                remaining.to_string(),
                Style::default().fg(theme.text()),
            ));
            break;
        }
    }

    spans
}

fn wrapped_height(text: &str, width: u16) -> u16 {
    if width == 0 {
        return 1;
    }
    let w = width as usize;
    let mut total_rows = 0;
    for line in text.lines() {
        let chars = line.chars().count();
        if chars == 0 {
            total_rows += 1;
        } else {
            total_rows += chars.div_ceil(w);
        }
    }
    (total_rows as u16).max(1)
}

fn message_height(
    msg: &ChatMessage,
    width: u16,
    thinking_expanded: bool,
    theme: palette::Theme,
) -> u16 {
    // User message panels are fixed at 3 rows (blank / message centered /
    // blank), per user decision (2026-07-18) — matches the reference
    // screenshot regardless of message length. Jules' replies keep the
    // original dynamic height.
    if matches!(msg.role, Role::User) {
        return 3;
    }
    let body_width = width.saturating_sub(3);
    let mut h = wrapped_height(&msg.body, body_width);
    if let Some(thinking) = &msg.thinking {
        h += ThinkingBlock::new(thinking, thinking_expanded, theme).height(body_width);
    }
    if msg.tagline.is_some() {
        h += 1;
    }
    h.max(1)
}
