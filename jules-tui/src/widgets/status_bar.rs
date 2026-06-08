//! Status bar widget — cwd, scoring state, boot latency.

use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::Style,
    widgets::{Paragraph, Widget},
};

use crate::app::AppState;

pub struct StatusBar<'a> {
    state: &'a AppState,
}

impl<'a> StatusBar<'a> {
    pub fn new(state: &'a AppState) -> Self {
        Self { state }
    }

    /// Build the one-line status string.
    pub fn status_line(state: &AppState) -> String {
        let scoring = if state.scoring_healthy { "✓ scoring" } else { "✗ scoring" };
        let boot = if state.boot_ms > 0.0 {
            format!(" | boot {:.0}ms", state.boot_ms)
        } else {
            String::new()
        };
        format!(" {} | {} episodes{}", scoring, state.episodes, boot)
    }
}

impl Widget for StatusBar<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let line = Self::status_line(self.state);
        Paragraph::new(line)
            .style(Style::default())
            .render(area, buf);
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app::AppState;

    #[test]
    fn status_line_healthy_scoring() {
        let mut s = AppState::default();
        s.scoring_healthy = true;
        s.episodes = 42;
        s.boot_ms = 123.0;
        let line = StatusBar::status_line(&s);
        assert!(line.contains("✓ scoring"));
        assert!(line.contains("42 episodes"));
        assert!(line.contains("123ms"));
    }

    #[test]
    fn status_line_unhealthy_scoring() {
        let mut s = AppState::default();
        s.scoring_healthy = false;
        let line = StatusBar::status_line(&s);
        assert!(line.contains("✗ scoring"));
    }

    #[test]
    fn status_line_no_boot_ms_omits_boot() {
        let s = AppState::default(); // boot_ms = 0.0
        let line = StatusBar::status_line(&s);
        assert!(!line.contains("boot"));
    }
}
