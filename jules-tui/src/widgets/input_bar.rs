//! Input bar widget — text input with slash command detection.

use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::Style,
    widgets::{Block, Borders, Paragraph, Widget},
};

use crate::app::AppState;

pub struct InputBar<'a> {
    state: &'a AppState,
}

impl<'a> InputBar<'a> {
    pub fn new(state: &'a AppState) -> Self {
        Self { state }
    }

    /// Returns true if the current input starts a slash command.
    pub fn is_slash_command(input: &str) -> bool {
        input.starts_with('/')
    }

    /// Build display content: show hint prefix for slash commands.
    pub fn display_content(input: &str) -> String {
        input.to_string()
    }
}

impl Widget for InputBar<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let title = if Self::is_slash_command(&self.state.input) {
            " Command "
        } else {
            " Input "
        };
        let block = Block::default().borders(Borders::ALL).title(title);
        let content = Self::display_content(&self.state.input);
        Paragraph::new(content)
            .style(Style::default())
            .block(block)
            .render(area, buf);
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn slash_prefix_detected() {
        assert!(InputBar::is_slash_command("/status"));
        assert!(InputBar::is_slash_command("/"));
    }

    #[test]
    fn non_slash_not_detected() {
        assert!(!InputBar::is_slash_command("hello"));
        assert!(!InputBar::is_slash_command(""));
    }

    #[test]
    fn display_content_returns_input() {
        assert_eq!(InputBar::display_content("hello"), "hello");
        assert_eq!(InputBar::display_content("/status"), "/status");
    }
}
