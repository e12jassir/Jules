//! Chat log widget — renders conversation messages and streaming buffer.
//! No background color set (transparency rule).

use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::Style,
    text::{Line, Span, Text},
    widgets::{Block, Paragraph, Widget, Wrap},
};

use crate::app::AppState;

pub struct ChatLog<'a> {
    state: &'a AppState,
}

impl<'a> ChatLog<'a> {
    pub fn new(state: &'a AppState) -> Self {
        Self { state }
    }

    fn build_text(&self) -> Text<'static> {
        let mut lines: Vec<Line<'static>> = Vec::new();

        for (is_user, content) in &self.state.messages {
            let prefix = if *is_user { "You: " } else { "Jules: " };
            let line = Line::from(vec![
                Span::raw(prefix.to_string()),
                Span::raw(content.clone()),
            ]);
            lines.push(line);
        }

        // Append streaming buffer if active
        if self.state.is_streaming && !self.state.streaming_buf.is_empty() {
            lines.push(Line::from(vec![
                Span::raw("Jules: "),
                Span::raw(self.state.streaming_buf.clone()),
                Span::raw("▌"),
            ]));
        }

        Text::from(lines)
    }
}

impl Widget for ChatLog<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let text = self.build_text();
        // No bg — Style::default() has no background
        let para = Paragraph::new(text)
            .style(Style::default())
            .block(Block::default())
            .wrap(Wrap { trim: false });
        para.render(area, buf);
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app::{AppState, TuiMode};

    fn state_with_messages() -> AppState {
        let mut s = AppState::default();
        s.mode = TuiMode::Chat;
        s.messages.push((true, "hello".into()));
        s.messages.push((false, "world".into()));
        s
    }

    #[test]
    fn builds_text_with_correct_prefixes() {
        let state = state_with_messages();
        let widget = ChatLog::new(&state);
        let text = widget.build_text();
        let rendered: Vec<String> = text.lines.iter()
            .map(|l| l.spans.iter().map(|s| s.content.as_ref()).collect::<String>())
            .collect();
        assert!(rendered[0].starts_with("You: "));
        assert!(rendered[1].starts_with("Jules: "));
    }

    #[test]
    fn streaming_buf_adds_cursor_line() {
        let mut state = AppState::default();
        state.is_streaming = true;
        state.streaming_buf = "partial".into();
        let widget = ChatLog::new(&state);
        let text = widget.build_text();
        let last = text.lines.last().unwrap();
        let full: String = last.spans.iter().map(|s| s.content.as_ref()).collect();
        assert!(full.contains("partial"));
        assert!(full.contains("▌"));
    }

    #[test]
    fn empty_state_produces_empty_text() {
        let state = AppState::default();
        let text = ChatLog::new(&state).build_text();
        assert!(text.lines.is_empty());
    }
}
