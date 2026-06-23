//! Welcome screen shown while the backend finishes booting.

use ratatui::{
    buffer::Buffer,
    layout::{Alignment, Constraint, Flex, Layout, Rect},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Paragraph, Widget},
};

use crate::{
    app::{AppState, TIPS},
    theme,
    widgets::input_bar::InputBar,
};

const VERSION: &str = env!("CARGO_PKG_VERSION");
const ROSE_ART: &[&str] = &[
    "     ██╗██╗   ██╗██╗     ███████╗███████╗",
    "     ██║██║   ██║██║     ██╔════╝██╔════╝",
    "     ██║██║   ██║██║     █████╗  ███████╗",
    "██   ██║██║   ██║██║     ██╔══╝  ╚════██║",
    "╚█████╔╝╚██████╔╝███████╗███████╗███████║",
    " ╚════╝  ╚═════╝ ╚══════╝╚══════╝╚══════╝",
];

pub struct WelcomeScreen<'a> {
    state: &'a AppState,
}

impl<'a> WelcomeScreen<'a> {
    pub fn new(state: &'a AppState) -> Self {
        Self { state }
    }

    fn tip_text(state: &AppState) -> &'static str {
        if TIPS.is_empty() {
            "Jules is starting up"
        } else {
            TIPS[state.tip_index % TIPS.len()]
        }
    }

    fn status_line(state: &AppState) -> Line<'static> {
        let path = if let Ok(home) = std::env::var("HOME") {
            if state.project_path.starts_with(&home) {
                state.project_path.replacen(&home, "~", 1)
            } else {
                state.project_path.clone()
            }
        } else {
            state.project_path.clone()
        };
        Line::from(vec![
            Span::styled(path, theme::accent()),
        ])
    }

    fn decorative_input(state: &AppState) -> Text<'static> {
        let mut spans = vec![Span::styled("> ", theme::accent())];

        if state.input.is_empty() {
            if state.input_focused {
                if state.cursor_visible {
                    spans.push(Span::styled("█", theme::cursor_block()));
                } else {
                    spans.push(Span::styled(" ", theme::text()));
                }
            } else {
                spans.push(Span::styled("Pregúntame cualquier cosa...", theme::muted()));
            }
        } else {
            spans.push(Span::styled(state.input.clone(), theme::text()));
            if state.input_focused && state.cursor_visible {
                spans.push(Span::styled("█", theme::cursor_block()));
            }
        }

        Text::from(Line::from(spans))
    }

    fn active_model_line(state: &AppState) -> Line<'static> {
        if state.backend_ready {
            Line::from(vec![
                Span::styled("Modelo: ", theme::muted()),
                Span::styled(state.active_model.clone(), theme::accent()),
            ])
        } else {
            Line::from(vec![
                Span::styled("● conectando backend", theme::muted()),
            ])
        }
    }

    fn key_bindings() -> Line<'static> {
        Line::from(vec![
            Span::styled("ctrl+m", theme::accent()),
            Span::styled(" modelos    ", theme::muted()),
            Span::styled("ctrl+p", theme::accent()),
            Span::styled(" comandos    ", theme::muted()),
            Span::styled("ctrl+h", theme::accent()),
            Span::styled(" ayuda    ", theme::muted()),
            Span::styled("tab", theme::accent()),
            Span::styled(" modelo    ", theme::muted()),
            Span::styled("ctrl+c", theme::accent()),
            Span::styled(" salir", theme::muted()),
        ])
    }

    /// Build providers row from available_models (de-duped, labeled).
    fn providers_row(state: &AppState) -> Line<'static> {
        const LABELS: &[(&str, &str)] = &[
            ("ollama", "Ollama"),
            ("antigravity", "Antigravity"),
            ("opencode", "OpenCode"),
            ("codex", "Codex"),
            ("google", "Google AI"),
            ("openrouter", "OpenRouter"),
            ("openai_oauth", "OpenAI"),
            ("openai", "OpenAI"),
        ];
        let label_for = |p: &str| -> String {
            LABELS.iter()
                .find(|(k, _)| *k == p)
                .map(|(_, v)| v.to_string())
                .unwrap_or_else(|| {
                    let mut s = p.to_string();
                    if let Some(c) = s.get_mut(0..1) { c.make_ascii_uppercase(); }
                    s
                })
        };

        let mut seen = std::collections::HashSet::new();
        let mut providers: Vec<String> = Vec::new();
        for m in &state.available_models {
            if let Some(p) = m.first() {
                if seen.insert(p.clone()) {
                    providers.push(label_for(p));
                }
            }
        }
        if providers.is_empty() {
            providers = vec!["Ollama".into(), "OpenCode".into(), "Google AI".into(), "OpenRouter".into(), "OpenAI".into()];
        }

        let mut spans: Vec<Span<'static>> = Vec::new();
        for (i, p) in providers.into_iter().enumerate() {
            if i > 0 { spans.push(Span::styled(" · ", theme::muted())); }
            spans.push(Span::styled(p, theme::muted()));
        }
        Line::from(spans)
    }

    fn rose_art() -> Text<'static> {
        Text::from(
            ROSE_ART
                .iter()
                .map(|line| Line::styled((*line).to_string(), theme::accent()))
                .collect::<Vec<_>>(),
        )
    }
}

impl Widget for WelcomeScreen<'_> {
    fn render(self, area: Rect, buf: &mut Buffer) {
        let [body_area, bottom_area] = Layout::vertical([
            Constraint::Min(0),
            Constraint::Length(2),
        ])
        .areas(area);

        let [_, center_area, _] = Layout::vertical([
            Constraint::Min(1),
            Constraint::Length(19),
            Constraint::Min(1),
        ])
        .flex(Flex::Center)
        .areas(body_area);

        let [_, content_area, _] = Layout::horizontal([
            Constraint::Min(1),
            Constraint::Length(68),
            Constraint::Min(1),
        ])
        .flex(Flex::Center)
        .areas(center_area);

        let [rose_area, tagline_area, input_area, status_area, providers_area, keys_area, tip_area, _] =
            Layout::vertical([
                Constraint::Length(6),
                Constraint::Length(2),
                Constraint::Length(3),
                Constraint::Length(1),
                Constraint::Length(1),
                Constraint::Length(2),
                Constraint::Length(2),
                Constraint::Min(0),
            ])
            .areas(content_area);

        Paragraph::new(Self::rose_art())
            .alignment(Alignment::Center)
            .render(rose_area, buf);
        Paragraph::new("Tu asistente de IA. Tu memoria. Tu compañera.")
            .style(theme::muted())
            .alignment(Alignment::Center)
            .render(tagline_area, buf);

        Paragraph::new(Self::decorative_input(self.state))
            .style(theme::text())
            .block(
                Block::default()
                    .borders(Borders::NONE)
                    .padding(ratatui::widgets::Padding::new(2, 2, 1, 1))
                    .style(ratatui::style::Style::default().bg(theme::SURFACE)),
            )
            .render(input_area, buf);

        Paragraph::new(Self::active_model_line(self.state))
            .alignment(Alignment::Center)
            .render(status_area, buf);

        // Slash autocomplete popup — rendered above input box
        if self.state.slash_autocomplete {
            let suggestions = InputBar::slash_suggestions(&self.state.input, &self.state.available_models);
            if !suggestions.is_empty() {
                let popup_h = suggestions.len() as u16 + 2;
                let popup_area = Rect {
                    x: input_area.x,
                    y: input_area.y.saturating_sub(popup_h),
                    width: input_area.width,
                    height: popup_h,
                };
                let lines: Vec<Line<'static>> = suggestions
                    .into_iter()
                    .enumerate()
                    .map(|(i, (label, _))| {
                        let style = if i == InputBar::selected_index(self.state) {
                            theme::title()
                        } else {
                            theme::muted()
                        };
                        Line::from(vec![Span::raw("  "), Span::styled(label, style)])
                    })
                    .collect();
                Paragraph::new(lines)
                    .block(
                        Block::default()
                            .borders(Borders::ALL)
                            .border_style(theme::accent())
                            .style(ratatui::style::Style::default().bg(theme::SURFACE)),
                    )
                    .render(popup_area, buf);
            }
        }

        Paragraph::new(Self::providers_row(self.state))
            .alignment(Alignment::Center)
            .render(providers_area, buf);

        Paragraph::new(Self::key_bindings())
            .alignment(Alignment::Center)
            .render(keys_area, buf);

        Paragraph::new(Line::from(vec![
            Span::styled("● ", theme::accent()),
            Span::styled(Self::tip_text(self.state), theme::muted()),
        ]))
        .alignment(Alignment::Center)
        .render(tip_area, buf);

        let bottom_inner = Rect {
            x: bottom_area.x,
            y: bottom_area.y.saturating_add(1),
            width: bottom_area.width,
            height: 1,
        };

        // Opencode-style footer: "Chat · <model> <provider>"
        let mut footer_spans = vec![
            Span::styled("Chat", theme::accent()),
            Span::styled(" · ", theme::muted()),
        ];
        let (provider, model) = if let Some((p, m)) = self.state.active_model.split_once(':') {
            (p.to_string(), m.to_string())
        } else {
            ("---".to_string(), self.state.active_model.clone())
        };
        footer_spans.push(Span::styled(model, theme::text()));
        footer_spans.push(Span::styled(format!(" {provider}"), theme::muted()));

        Paragraph::new(Line::from(footer_spans))
            .alignment(Alignment::Left)
            .render(bottom_inner, buf);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::app::AppState;

    #[test]
    fn tip_text_uses_rotating_index() {
        let mut state = AppState::default();
        state.tip_index = 1;

        assert_eq!(WelcomeScreen::tip_text(&state), TIPS[1]);
    }

    #[test]
    fn status_line_includes_project_path() {
        let mut state = AppState::default();
        state.project_path = "~/Jules".into();

        let line = WelcomeScreen::status_line(&state);
        let text: String = line
            .spans
            .iter()
            .map(|span| span.content.as_ref())
            .collect();

        assert_eq!(text, "~/Jules");
    }

    #[test]
    fn status_line_shortens_home_path() {
        let mut state = AppState::default();
        if let Ok(home) = std::env::var("HOME") {
            state.project_path = format!("{home}/dev/Jules");
            let line = WelcomeScreen::status_line(&state);
            let text: String = line
                .spans
                .iter()
                .map(|span| span.content.as_ref())
                .collect();
            assert_eq!(text, "~/dev/Jules");
        }
    }

    #[test]
    fn active_model_line_mentions_models() {
        let mut state = AppState::default();
        state.backend_ready = true;
        state.active_model = "ollama:llama3.2:1b".into();

        let line = WelcomeScreen::active_model_line(&state);
        let text: String = line.spans.iter().map(|s| s.content.as_ref()).collect();

        assert!(text.contains("ollama:llama3.2:1b"));
    }
}
