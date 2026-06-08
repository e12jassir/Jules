//! Sidebar widget — model, memory, and stats panels.

use ratatui::{
    buffer::Buffer,
    layout::{Constraint, Layout, Rect},
    style::Style,
    widgets::{Block, Borders, Paragraph, Widget},
};

use crate::app::AppState;

pub struct Sidebar<'a> {
    state: &'a AppState,
}

impl<'a> Sidebar<'a> {
    pub fn new(state: &'a AppState) -> Self {
        Self { state }
    }
}

impl Widget for Sidebar<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let [model_area, memory_area, stats_area] = Layout::vertical([
            Constraint::Length(4),
            Constraint::Length(4),
            Constraint::Min(0),
        ])
        .areas(area);

        // Model panel
        Paragraph::new(format!("  {}", self.state.active_model))
            .style(Style::default())
            .block(Block::default().borders(Borders::ALL).title(" Model "))
            .render(model_area, buf);

        // Memory panel
        let ep_str = format!("  Episodes: {}", self.state.episodes);
        Paragraph::new(ep_str)
            .style(Style::default())
            .block(Block::default().borders(Borders::ALL).title(" Memory "))
            .render(memory_area, buf);

        // Stats panel
        let online_str = if self.state.online { "online" } else { "offline" };
        let scoring_str = if self.state.scoring_healthy { "healthy" } else { "degraded" };
        let stats = format!("  {}\n  scoring: {}", online_str, scoring_str);
        Paragraph::new(stats)
            .style(Style::default())
            .block(Block::default().borders(Borders::ALL).title(" Stats "))
            .render(stats_area, buf);
    }
}
