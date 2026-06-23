//! Canonical Jules semantic palette for Ratatui.
//! Styles intentionally avoid backgrounds so terminal transparency is preserved.

use ratatui::style::{Color, Modifier, Style};

pub const BG: Color = Color::Indexed(0);
pub const SURFACE: Color = Color::Indexed(0); // Opaque terminal background for solid panels
pub const SURFACE_ALT: Color = Color::Indexed(8); // Bright black/dark gray for distinct elements
pub const BORDER: Color = Color::Indexed(8);
pub const BORDER_DIM: Color = Color::Indexed(8);
pub const TEXT_BRIGHT: Color = Color::Indexed(15);
pub const TEXT_MAIN: Color = Color::Indexed(7);
pub const TEXT_MUTED: Color = Color::Indexed(8);
pub const TEXT_DIM: Color = Color::Indexed(8);
// Brand accent maps to Magenta (color 5) to respect terminal palette
pub const ACCENT: Color = Color::Indexed(5);
pub const ACCENT_DIM: Color = Color::Indexed(5);
// Green, Yellow, Red map to their standard ANSI counterparts
pub const GREEN: Color = Color::Indexed(2);
pub const YELLOW: Color = Color::Indexed(3);
pub const RED: Color = Color::Indexed(1);

pub const TEXT: Color = TEXT_BRIGHT;
pub const MUTED: Color = TEXT_MUTED;
pub const SECONDARY: Color = ACCENT_DIM;
pub const SUCCESS: Color = GREEN;
pub const WARNING: Color = YELLOW;
pub const ERROR: Color = RED;

pub fn text() -> Style {
    Style::default().fg(TEXT)
}

pub fn accent() -> Style {
    Style::default().fg(ACCENT)
}

pub fn muted() -> Style {
    Style::default().fg(MUTED)
}

pub fn dim() -> Style {
    Style::default().fg(TEXT_DIM)
}

pub fn secondary() -> Style {
    Style::default().fg(SECONDARY)
}

pub fn success() -> Style {
    Style::default().fg(SUCCESS)
}

pub fn warning() -> Style {
    Style::default().fg(WARNING)
}

pub fn error() -> Style {
    Style::default().fg(ERROR)
}

pub fn border() -> Style {
    Style::default().fg(BORDER)
}

pub fn border_dim() -> Style {
    Style::default().fg(BORDER_DIM)
}

pub fn bright() -> Style {
    Style::default().fg(TEXT_BRIGHT)
}

pub fn title() -> Style {
    accent().add_modifier(Modifier::BOLD)
}

pub fn header() -> Style {
    secondary().add_modifier(Modifier::BOLD)
}

/// Cursor block: solid white background, drawn as a space with reversed fg/bg.
/// This is used for the manually-drawn blinking cursor in the input bar.
pub fn cursor_block() -> Style {
    Style::default()
        .fg(Color::White)
        .bg(Color::White)
}
