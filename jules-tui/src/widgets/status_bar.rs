//! Bottom status line: absolute cwd on the left.
//! When sidebar is hidden, renders "• Jules {version}" on the far right
//! with exact 2 spaces margin.

use ratatui::{
    layout::Rect,
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Paragraph, Widget},
};

use crate::palette;

pub struct BottomBar<'a> {
    pub cwd: &'a str,
    pub version: &'a str,
    pub sidebar_visible: bool,
    pub is_streaming: bool,
    pub anim_tick: usize,
    pub theme: palette::Theme,
}

pub fn format_relative_cwd(cwd: &str, git_branch: Option<&str>) -> String {
    let path = if let Ok(home) = std::env::var("HOME") {
        if cwd.starts_with(&home) {
            cwd.replacen(&home, "~", 1)
        } else {
            cwd.to_string()
        }
    } else {
        cwd.to_string()
    };
    match git_branch {
        Some(branch) => format!("{}:{}", path, branch),
        None => path,
    }
}

impl<'a> Widget for BottomBar<'a> {
    fn render(self, area: Rect, buf: &mut ratatui::buffer::Buffer) {
        let left_spans = if self.is_streaming {
            let frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];
            let spinner = frames[self.anim_tick % frames.len()];
            let mut spans = vec![
                Span::raw("  "),
                Span::styled(
                    spinner,
                    Style::default()
                        .fg(self.theme.accent())
                        .add_modifier(Modifier::BOLD),
                ),
                Span::raw("  "),
            ];
            if let Some(bg) = self.theme.field_bg() {
                spans.push(Span::styled(
                    " esc ",
                    Style::default()
                        .fg(self.theme.text())
                        .bg(bg)
                        .add_modifier(Modifier::BOLD),
                ));
            } else {
                spans.push(Span::styled(
                    "esc",
                    Style::default()
                        .fg(self.theme.amber())
                        .add_modifier(Modifier::BOLD),
                ));
            }
            spans.push(Span::styled(
                " interrupt",
                Style::default().fg(self.theme.faint()),
            ));
            spans
        } else {
            vec![Span::styled(
                format!("  {}", self.cwd),
                Style::default().fg(self.theme.faint()),
            )]
        };

        let mut spans = left_spans;

        if !self.sidebar_visible {
            let right_text = format!("• Jules {}", self.version);
            let total_width = area.width as usize;
            let left_len = if self.is_streaming {
                25
            } else {
                self.cwd.chars().count() + 2
            };
            let right_len = right_text.chars().count();

            let pad = total_width
                .saturating_sub(left_len)
                .saturating_sub(right_len)
                .saturating_sub(1);

            if pad > 0 {
                spans.push(Span::raw(" ".repeat(pad)));
                spans.push(Span::styled(
                    right_text,
                    Style::default().fg(self.theme.faint()),
                ));
            }
        }

        Paragraph::new(Line::from(spans)).render(area, buf);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::buffer::Buffer;
    use ratatui::layout::Rect;

    #[test]
    fn test_bottom_bar_idle_and_streaming() {
        let area = Rect::new(0, 0, 80, 1);

        // Idle mode
        let mut buf_idle = Buffer::empty(area);
        let bar_idle = BottomBar {
            cwd: "/home/test/project",
            version: "0.4.0",
            sidebar_visible: true,
            is_streaming: false,
            anim_tick: 0,
            theme: palette::Theme::System,
        };
        bar_idle.render(area, &mut buf_idle);
        let idle_symbols: String = buf_idle.content().iter().map(|c| c.symbol()).collect();
        assert!(idle_symbols.contains("/home/test/project"));

        // Streaming loading mode
        let mut buf_stream = Buffer::empty(area);
        let bar_stream = BottomBar {
            cwd: "/home/test/project",
            version: "0.4.0",
            sidebar_visible: true,
            is_streaming: true,
            anim_tick: 3,
            theme: palette::Theme::System,
        };
        bar_stream.render(area, &mut buf_stream);
        let stream_symbols: String = buf_stream.content().iter().map(|c| c.symbol()).collect();
        assert!(stream_symbols.contains("esc"));
        assert!(stream_symbols.contains("interrupt"));
    }
}
