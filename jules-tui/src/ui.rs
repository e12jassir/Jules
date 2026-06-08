//! Root layout and frame draw function.
//! IMPORTANT: No `bg` color is set on any widget — compositor transparency preserved.

use ratatui::{
    layout::{Constraint, Flex, Layout, Rect},
    widgets::{Block, Borders, Clear, Paragraph},
    Frame,
};

use crate::app::{AppState, TuiMode};
use crate::widgets::{
    chat_log::ChatLog, input_bar::InputBar, model_picker::ModelPicker, sidebar::Sidebar,
    status_bar::StatusBar,
};

/// Draw the full TUI frame. Called on every AppState change.
pub fn draw(frame: &mut Frame, state: &AppState) {
    let area = frame.area();

    let [main_area, sidebar_area] =
        Layout::horizontal([Constraint::Min(0), Constraint::Length(28)]).areas(area);

    let [chat_area, input_area, status_area] = Layout::vertical([
        Constraint::Min(0),
        Constraint::Length(3),
        Constraint::Length(1),
    ])
    .areas(main_area);

    frame.render_widget(ChatLog::new(state), chat_area);
    frame.render_widget(InputBar::new(state), input_area);
    frame.render_widget(StatusBar::new(state), status_area);
    frame.render_widget(Sidebar::new(state), sidebar_area);

    match &state.mode {
        TuiMode::ModelPicker => {
            let popup = centered_rect(area, 60, 40);
            frame.render_widget(Clear, popup);
            frame.render_widget(ModelPicker::new(state), popup);
        }
        TuiMode::Connecting => {
            let popup = centered_rect(area, 50, 20);
            frame.render_widget(Clear, popup);
            frame.render_widget(
                Paragraph::new("Connecting to backend…")
                    .block(Block::default().borders(Borders::ALL).title(" Jules ")),
                popup,
            );
        }
        TuiMode::Error(message) => {
            let popup = centered_rect(area, 70, 25);
            frame.render_widget(Clear, popup);
            frame.render_widget(
                Paragraph::new(message.clone()).block(
                    Block::default()
                        .borders(Borders::ALL)
                        .title(" Backend error "),
                ),
                popup,
            );
        }
        TuiMode::Chat => {}
    }
}

fn centered_rect(area: Rect, percent_x: u16, percent_y: u16) -> Rect {
    let [_, middle, _]: [Rect; 3] = Layout::vertical([
        Constraint::Percentage((100 - percent_y) / 2),
        Constraint::Percentage(percent_y),
        Constraint::Percentage((100 - percent_y) / 2),
    ])
    .flex(Flex::Center)
    .areas(area);

    let [_, popup, _]: [Rect; 3] = Layout::horizontal([
        Constraint::Percentage((100 - percent_x) / 2),
        Constraint::Percentage(percent_x),
        Constraint::Percentage((100 - percent_x) / 2),
    ])
    .flex(Flex::Center)
    .areas(middle);

    popup
}
