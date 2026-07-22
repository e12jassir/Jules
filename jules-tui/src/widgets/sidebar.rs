//! Mirrors `.chat-side` from jules_tui_mockup.html: panels — CONTEXTO,
//! ROUTER, MEMORIA, DOCTOR — plus the "• Jules {version}" identity line
//! pinned to the panel's own last row. Panel titles use `h5` styling:
//! small, letter-spaced, --faint.

use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span},
    widgets::{Paragraph, Widget, Wrap},
};

use crate::app::{AppState, DoctorStatus, RoutingMode};
use crate::palette;

pub struct Sidebar<'a> {
    pub state: &'a AppState,
    pub theme: palette::Theme,
    pub version: &'a str,
}

fn panel_title(title: &str, theme: palette::Theme) -> Line<'static> {
    Line::from(Span::styled(
        title.to_string(),
        Style::default()
            .fg(theme.faint())
            .add_modifier(Modifier::BOLD),
    ))
}

fn kv_line(label: &str, value: String, _width: u16, theme: palette::Theme) -> Line<'static> {
    Line::from(vec![
        Span::styled(format!("{label} "), Style::default().fg(theme.dim())),
        Span::styled(value, Style::default().fg(theme.text()).add_modifier(Modifier::BOLD)),
    ])
}

impl<'a> Widget for Sidebar<'a> {
    fn render(self, area: Rect, buf: &mut ratatui::buffer::Buffer) {
        let s = self.state;

        // DOCTOR section height: title + blank + content rows.
        // Only non-passing checks are shown, so height tracks issue count.
        let doctor_content_rows = if s.doctor_running || s.doctor_checks.is_empty() {
            1u16 // "checking..." or "run /doctor to check"
        } else {
            let issues = s.doctor_checks.iter().filter(|c| c.status != DoctorStatus::Pass).count();
            if issues == 0 { 1 } else { issues.min(10) as u16 }
        };
        let doctor_height = 2 + doctor_content_rows; // title + blank + rows

        let rows = Layout::default()
            .direction(Direction::Vertical)
            .constraints([
                Constraint::Length(1),             // top padding
                Constraint::Length(5),             // CONTEXTO title + blank + 3 kv
                Constraint::Length(2),             // gap
                Constraint::Length(5),             // ROUTER title + blank + active + mode
                Constraint::Length(2),             // gap
                Constraint::Length(6),             // MEMORIA title + blank + episodes + match
                Constraint::Length(2),             // gap
                Constraint::Length(doctor_height), // DOCTOR (dynamic)
                Constraint::Min(1),                // filler
                Constraint::Length(1),             // "• Jules {version}"
                Constraint::Length(1),             // bottom padding
            ])
            .split(area);

        // ── CONTEXTO ────────────────────────────────────────────────────
        let ctx_lines = vec![
            panel_title("CONTEXTO", self.theme),
            Line::default(),
            kv_line("tokens", format!("{}", s.ctx_tokens), area.width, self.theme),
            kv_line("used", format!("{}%", s.ctx_used_pct), area.width, self.theme),
            kv_line(
                "quota",
                format!("{} {}%", s.ctx_quota_provider, s.ctx_quota_pct),
                area.width,
                self.theme,
            ),
        ];
        Paragraph::new(ctx_lines)
            .wrap(Wrap { trim: true })
            .render(rows[1], buf);

        // ── ROUTER ───────────────────────────────────────────────────────
        let mode_str = match s.routing_mode {
            RoutingMode::Manual => "manual",
            RoutingMode::Auto => "auto",
        };
        let mut router_lines = vec![
            panel_title("ROUTER", self.theme),
            Line::default(),
            kv_line("active", s.active_model.clone(), area.width, self.theme),
        ];
        let mode_line = if let (RoutingMode::Auto, Some(reason)) = (s.routing_mode, &s.routing_reason) {
            format!("{} — {}", mode_str, reason)
        } else {
            mode_str.to_string()
        };
        router_lines.push(kv_line("mode", mode_line, area.width, self.theme));
        Paragraph::new(router_lines)
            .wrap(Wrap { trim: true })
            .render(rows[3], buf);

        // ── MEMORIA ──────────────────────────────────────────────────────
        let mem_lines = vec![
            panel_title("MEMORIA", self.theme),
            Line::default(),
            kv_line("episodes", format!("{} retrieved", s.mem_episodes), area.width, self.theme),
            Line::from(Span::styled(
                format!("top match {}% — {}", s.mem_top_match_pct, s.mem_top_match_note),
                Style::default().fg(self.theme.faint()),
            )),
        ];
        Paragraph::new(mem_lines)
            .wrap(Wrap { trim: true })
            .render(rows[5], buf);

        // ── DOCTOR ───────────────────────────────────────────────────────
        let mut doctor_lines: Vec<Line> = vec![
            panel_title("DOCTOR", self.theme),
            Line::default(),
        ];

        if s.doctor_running {
            // Auto-run in progress on startup.
            doctor_lines.push(Line::from(Span::styled(
                "checking...",
                Style::default().fg(self.theme.faint()),
            )));
        } else if s.doctor_checks.is_empty() {
            doctor_lines.push(Line::from(Span::styled(
                "run /doctor to check",
                Style::default().fg(self.theme.faint()),
            )));
        } else {
            let issues: Vec<&crate::app::DoctorCheck> = s
                .doctor_checks
                .iter()
                .filter(|c| c.status != DoctorStatus::Pass)
                .collect();

            if issues.is_empty() {
                doctor_lines.push(Line::from(Span::styled(
                    "✓ all systems go",
                    Style::default().fg(self.theme.good()),
                )));
            } else {
                for check in issues.iter().take(10) {
                    let (icon, icon_style) = match check.status {
                        DoctorStatus::Fail => ("✗", Style::default().fg(self.theme.warn())),
                        DoctorStatus::Warn => ("⚠", Style::default().fg(self.theme.amber())),
                        DoctorStatus::Pass => unreachable!(),
                    };
                    let name_style = match check.status {
                        DoctorStatus::Fail => Style::default()
                            .fg(self.theme.text())
                            .add_modifier(Modifier::BOLD),
                        _ => Style::default().fg(self.theme.text()),
                    };
                    doctor_lines.push(Line::from(vec![
                        Span::styled(format!("{icon} "), icon_style),
                        Span::styled(check.name.clone(), name_style),
                    ]));
                }
            }
        }

        Paragraph::new(doctor_lines)
            .wrap(Wrap { trim: true })
            .render(rows[7], buf);

        // ── Identity ─────────────────────────────────────────────────────
        let identity_area = rows[9];
        if identity_area.height > 0 {
            Paragraph::new(Line::from(Span::styled(
                format!("• Jules {}", self.version),
                Style::default().fg(self.theme.faint()),
            )))
            .alignment(Alignment::Left)
            .render(identity_area, buf);
        }
    }
}
