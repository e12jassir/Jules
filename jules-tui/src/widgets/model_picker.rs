//! Model picker widget — Tab-triggered overlay to cycle available models.

use ratatui::{
    buffer::Buffer,
    layout::Rect,
    style::Style,
    widgets::{Block, Borders, List, ListItem, Widget},
};

use crate::app::AppState;

pub struct ModelPicker<'a> {
    state: &'a AppState,
}

impl<'a> ModelPicker<'a> {
    pub fn new(state: &'a AppState) -> Self {
        Self { state }
    }

    /// Return the index of the next model, wrapping around.
    pub fn next_model_index(current: &str, models: &[Vec<String>]) -> Option<usize> {
        if models.is_empty() {
            return None;
        }
        let current_key = current.to_string();
        let current_idx = models.iter().position(|m| {
            m.len() >= 2 && format!("{}:{}", m[0], m[1]) == current_key
        });
        Some(match current_idx {
            Some(i) => (i + 1) % models.len(),
            None => 0,
        })
    }

    /// Return the model key string (provider:model) for a given index.
    pub fn model_key(models: &[Vec<String>], idx: usize) -> Option<String> {
        models.get(idx).filter(|m| m.len() >= 2)
            .map(|m| format!("{}:{}", m[0], m[1]))
    }
}

impl Widget for ModelPicker<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let items: Vec<ListItem> = self.state.available_models.iter()
            .map(|m| {
                let key = if m.len() >= 2 {
                    format!("{}:{}", m[0], m[1])
                } else {
                    m.join(":")
                };
                let marker = if key == self.state.active_model { "▶ " } else { "  " };
                ListItem::new(format!("{}{}", marker, key))
            })
            .collect();

        List::new(items)
            .style(Style::default())
            .block(Block::default().borders(Borders::ALL).title(" Models "))
            .render(area, buf);
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn models() -> Vec<Vec<String>> {
        vec![
            vec!["google".into(), "gemini-3.5".into()],
            vec!["ollama".into(), "llama3.2:1b".into()],
        ]
    }

    #[test]
    fn next_index_advances() {
        let idx = ModelPicker::next_model_index("google:gemini-3.5", &models());
        assert_eq!(idx, Some(1));
    }

    #[test]
    fn next_index_wraps_around() {
        let idx = ModelPicker::next_model_index("ollama:llama3.2:1b", &models());
        assert_eq!(idx, Some(0));
    }

    #[test]
    fn next_index_unknown_returns_zero() {
        let idx = ModelPicker::next_model_index("unknown:model", &models());
        assert_eq!(idx, Some(0));
    }

    #[test]
    fn model_key_builds_correctly() {
        assert_eq!(
            ModelPicker::model_key(&models(), 0),
            Some("google:gemini-3.5".into())
        );
    }

    #[test]
    fn model_key_out_of_bounds_returns_none() {
        assert!(ModelPicker::model_key(&models(), 99).is_none());
    }
}
