//! Theme system: 6 selectable themes, cycled with ctrl+y.
//!
//! `System` is the default: background stays translucent (nothing painted
//! on empty/panel zones, the real terminal background shows through — this
//! was the original reason Fase 1.5 moved off Textual), but all foreground
//! (text) colors are fixed, readable light/white tones instead of depending
//! on the terminal's own palette (user decision, 2026-07-18: legibility on
//! any terminal background, including light ones, matters more than full
//! transparency of the text layer).
//!
//! The other 5 themes are well-known color schemes (Dracula, Nord, Gruvbox
//! Dark, Tokyo Night, Catppuccin Mocha) and paint solid backgrounds on
//! panels/inputs/user messages using their own palette (per user decision,
//! 2026-07-18: "todos me sirven... coge unos 5").
//!
//! No theme uses line-drawn borders (┌─┐└┘│) — panels are delimited by
//! their background fill only, never by box-drawing characters.

use ratatui::style::Color;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Theme {
    System,
    Dracula,
    Nord,
    GruvboxDark,
    TokyoNight,
    CatppuccinMocha,
}

/// Fixed display order for the `/themes` picker overlay — mirrors
/// `Theme::next()`'s cycle order.
pub const ALL_THEMES: &[Theme] = &[
    Theme::System,
    Theme::Dracula,
    Theme::Nord,
    Theme::GruvboxDark,
    Theme::TokyoNight,
    Theme::CatppuccinMocha,
];

/// Full set of colors a theme needs to paint the app. Each `Theme` variant
/// resolves to one of these via `Theme::colors()`.
pub struct Colors {
    /// Panel-level background (sidebar, status bars, thinking block).
    /// `None` means: paint nothing, let the terminal background show
    /// through (System theme only).
    pub panel_bg: Option<Color>,
    /// Input field background (home box, chat input bar). Same rule as
    /// `panel_bg` for `None`.
    pub field_bg: Option<Color>,
    /// User message bubble background. Same rule as `panel_bg` for `None`.
    pub user_message_bg: Option<Color>,

    /// Primary readable text — Jules' replies, input text, values.
    pub text: Color,
    /// Slightly muted text — user's own message body, secondary values.
    pub dim: Color,
    /// Faint text — placeholders, hints, labels, taglines.
    pub faint: Color,
    /// Accent color — mode label, cursor block, left accent bar.
    pub accent: Color,
    /// Amber/warm color — prompt char, "Jules" who-label, tip label.
    pub amber: Color,
    /// Success/positive indicator.
    pub good: Color,
    /// Warning indicator.
    pub warn: Color,
    /// Base app background color, used behind the cursor block so it
    /// reads correctly regardless of theme.
    pub void: Color,
}

impl Theme {
    #[allow(dead_code)] // kept as an alias of `next()` for API stability
    pub fn toggle(self) -> Self {
        self.next()
    }

    /// Cycle through all 6 themes in a fixed order, wrapping around.
    pub fn next(self) -> Self {
        match self {
            Theme::System => Theme::Dracula,
            Theme::Dracula => Theme::Nord,
            Theme::Nord => Theme::GruvboxDark,
            Theme::GruvboxDark => Theme::TokyoNight,
            Theme::TokyoNight => Theme::CatppuccinMocha,
            Theme::CatppuccinMocha => Theme::System,
        }
    }

    pub fn label(self) -> &'static str {
        match self {
            Theme::System => "system",
            Theme::Dracula => "dracula",
            Theme::Nord => "nord",
            Theme::GruvboxDark => "gruvbox",
            Theme::TokyoNight => "tokyonight",
            Theme::CatppuccinMocha => "catppuccin",
        }
    }

    pub fn colors(self) -> Colors {
        match self {
            Theme::System => Colors {
                panel_bg: None,
                field_bg: None,
                user_message_bg: None,
                // Fixed, high-contrast light tones — readable regardless of
                // the terminal's own background color (user decision,
                // 2026-07-18: "asegurate de pintar los colores de la fuente
                // que sean legibles blancos y no se que mas").
                text: Color::White,
                dim: Color::Rgb(0xe0, 0xe0, 0xe0),
                faint: Color::Rgb(0xb0, 0xb0, 0xb8),
                accent: Color::Rgb(0x8a, 0xa6, 0xff),
                amber: Color::Rgb(0xff, 0xc0, 0x7a),
                good: Color::Rgb(0x6f, 0xe9, 0x9a),
                warn: Color::Rgb(0xf0, 0xc8, 0x5d),
                void: Color::Rgb(0x0b, 0x0d, 0x12),
            },
            Theme::Dracula => Colors {
                panel_bg: Some(Color::Rgb(0x28, 0x2a, 0x36)),
                field_bg: Some(Color::Rgb(0x28, 0x2a, 0x36)),
                user_message_bg: Some(Color::Rgb(0x28, 0x2a, 0x36)),
                text: Color::Rgb(0xf8, 0xf8, 0xf2),
                dim: Color::Rgb(0xbd, 0xbd, 0xd0),
                faint: Color::Rgb(0x62, 0x72, 0xa4),
                accent: Color::Rgb(0xbd, 0x93, 0xf9),
                amber: Color::Rgb(0xff, 0xb8, 0x6c),
                good: Color::Rgb(0x50, 0xfa, 0x7b),
                warn: Color::Rgb(0xf1, 0xfa, 0x8c),
                void: Color::Rgb(0x1e, 0x1f, 0x29),
            },
            Theme::Nord => Colors {
                panel_bg: Some(Color::Rgb(0x3b, 0x42, 0x52)),
                field_bg: Some(Color::Rgb(0x3b, 0x42, 0x52)),
                user_message_bg: Some(Color::Rgb(0x3b, 0x42, 0x52)),
                text: Color::Rgb(0xec, 0xef, 0xf4),
                dim: Color::Rgb(0xd8, 0xde, 0xe9),
                faint: Color::Rgb(0x81, 0x8a, 0xa1),
                accent: Color::Rgb(0x88, 0xc0, 0xd0),
                amber: Color::Rgb(0xd0, 0x87, 0x70),
                good: Color::Rgb(0xa3, 0xbe, 0x8c),
                warn: Color::Rgb(0xeb, 0xcb, 0x8b),
                void: Color::Rgb(0x2e, 0x34, 0x40),
            },
            Theme::GruvboxDark => Colors {
                panel_bg: Some(Color::Rgb(0x3c, 0x38, 0x36)),
                field_bg: Some(Color::Rgb(0x3c, 0x38, 0x36)),
                user_message_bg: Some(Color::Rgb(0x3c, 0x38, 0x36)),
                text: Color::Rgb(0xeb, 0xdb, 0xb2),
                dim: Color::Rgb(0xd5, 0xc4, 0xa1),
                faint: Color::Rgb(0x92, 0x83, 0x74),
                accent: Color::Rgb(0x83, 0xa5, 0x98),
                amber: Color::Rgb(0xfe, 0x80, 0x19),
                good: Color::Rgb(0xb8, 0xbb, 0x26),
                warn: Color::Rgb(0xfa, 0xbd, 0x2f),
                void: Color::Rgb(0x28, 0x28, 0x28),
            },
            Theme::TokyoNight => Colors {
                panel_bg: Some(Color::Rgb(0x24, 0x28, 0x3b)),
                field_bg: Some(Color::Rgb(0x24, 0x28, 0x3b)),
                user_message_bg: Some(Color::Rgb(0x24, 0x28, 0x3b)),
                text: Color::Rgb(0xc0, 0xca, 0xf5),
                dim: Color::Rgb(0xa9, 0xb1, 0xd6),
                faint: Color::Rgb(0x56, 0x5f, 0x89),
                accent: Color::Rgb(0x7a, 0xa2, 0xf7),
                amber: Color::Rgb(0xe0, 0xaf, 0x68),
                good: Color::Rgb(0x9e, 0xce, 0x6a),
                warn: Color::Rgb(0xe0, 0xaf, 0x68),
                void: Color::Rgb(0x1a, 0x1b, 0x26),
            },
            Theme::CatppuccinMocha => Colors {
                panel_bg: Some(Color::Rgb(0x31, 0x32, 0x44)),
                field_bg: Some(Color::Rgb(0x31, 0x32, 0x44)),
                user_message_bg: Some(Color::Rgb(0x31, 0x32, 0x44)),
                text: Color::Rgb(0xcd, 0xd6, 0xf4),
                dim: Color::Rgb(0xba, 0xc2, 0xde),
                faint: Color::Rgb(0x6c, 0x70, 0x86),
                accent: Color::Rgb(0x89, 0xb4, 0xfa),
                amber: Color::Rgb(0xfa, 0xb3, 0x87),
                good: Color::Rgb(0xa6, 0xe3, 0xa1),
                warn: Color::Rgb(0xf9, 0xe2, 0xaf),
                void: Color::Rgb(0x1e, 0x1e, 0x2e),
            },
        }
    }

    pub fn panel_bg(self) -> Option<Color> {
        self.colors().panel_bg
    }

    pub fn field_bg(self) -> Option<Color> {
        self.colors().field_bg
    }

    pub fn user_message_bg(self) -> Option<Color> {
        self.colors().user_message_bg
    }

    /// Jules' reply background — ALWAYS None, in every theme. Per explicit
    /// user decision: Jules' own text never gets a background block, only
    /// the user's messages and UI chrome do.
    pub fn jules_message_bg(self) -> Option<Color> {
        None
    }

    pub fn text(self) -> Color {
        self.colors().text
    }

    pub fn dim(self) -> Color {
        self.colors().dim
    }

    pub fn faint(self) -> Color {
        self.colors().faint
    }

    pub fn accent(self) -> Color {
        self.colors().accent
    }

    pub fn amber(self) -> Color {
        self.colors().amber
    }

    pub fn good(self) -> Color {
        self.colors().good
    }

    pub fn warn(self) -> Color {
        self.colors().warn
    }

    pub fn void(self) -> Color {
        self.colors().void
    }
}
