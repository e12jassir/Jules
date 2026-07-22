//! Mirrors `.toolblock .thinking` from jules_tui_mockup.html:
//!   background: #0c0f16, border: 1px solid --border, color: --dim,
//!   the "Thinking:" label styled italic in --faint.
//!
//! Collapsed state (thinking_expanded = false) renders only the label line,
//! matching the "hide the reasoning, keep the fact that it happened" intent
//! confirmed with the user.

use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Paragraph, Widget, Wrap},
};

use crate::palette;

pub struct ThinkingBlock<'a> {
    pub content: &'a str,
    pub expanded: bool,
    pub theme: palette::Theme,
}

impl<'a> ThinkingBlock<'a> {
    pub fn new(content: &'a str, expanded: bool, theme: palette::Theme) -> Self {
        Self {
            content,
            expanded,
            theme,
        }
    }

    /// Height in terminal rows this block will need once rendered, so the
    /// caller (chat_log) can lay out the rest of the message around it.
    pub fn height(&self, width: u16) -> u16 {
        if !self.expanded {
            return 1;
        }
        let inner_width = width.saturating_sub(2).max(1) as usize;
        let label = "Thinking: ";
        let wrapped = textwrap_len(label, self.content, inner_width);
        wrapped as u16
    }
}

impl<'a> Widget for ThinkingBlock<'a> {
    fn render(self, area: Rect, buf: &mut ratatui::buffer::Buffer) {
        if !self.expanded {
            let line = Line::from(vec![Span::styled(
                "Thinking",
                Style::default()
                    .fg(self.theme.faint())
                    .add_modifier(Modifier::ITALIC),
            )]);
            Paragraph::new(line).render(area, buf);
            return;
        }

        // No line-drawn border, per user decision (2026-07-18) — the block
        // is delimited by its background fill only (themes with a solid
        // panel_bg), or by nothing at all (System theme).
        let mut block_style = Style::default();
        if let Some(bg) = self.theme.panel_bg() {
            block_style = block_style.bg(bg);
        }
        let block = Block::default().style(block_style);

        let text = Line::from(vec![
            Span::styled(
                "Thinking: ",
                Style::default()
                    .fg(self.theme.faint())
                    .add_modifier(Modifier::ITALIC),
            ),
            Span::styled(self.content, Style::default().fg(self.theme.dim())),
        ]);

        Paragraph::new(text)
            .block(block)
            .wrap(Wrap { trim: true })
            .render(area, buf);
    }
}

/// Rough line-count estimate for "label: content" wrapped at `width` columns.
/// Good enough for layout sizing — Ratatui's own Wrap handles the real thing.
fn textwrap_len(label: &str, content: &str, width: usize) -> usize {
    let total_chars = label.len() + content.len();
    if width == 0 {
        return 1;
    }
    total_chars.div_ceil(width).max(1)
}
