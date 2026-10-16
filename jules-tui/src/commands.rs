//! Slash command definitions and matching for the command overlay.
//! Mirrors the command set from the Python/Textual prototype
//! (`jules/cli/commands.py`, now obsolete per user decision 2026-07-19),
//! adapted to the Rust frontend. Command *execution* is out of scope here
//! — this module only detects `/` input and lists matching commands; the
//! caller decides what happens on selection.

/// One registered slash command. `name` is the canonical command sent to
/// the backend; aliases only help discovery and are normalized before
/// dispatch, so one action is never shown twice in the overlay.
pub struct SlashCommand {
    pub name: &'static str,
    pub description: &'static str,
    pub aliases: &'static [&'static str],
}

pub const COMMANDS: &[SlashCommand] = &[
    SlashCommand {
        name: "exit",
        description: "Cerrar Jules",
        aliases: &[],
    },
    SlashCommand {
        name: "sessions",
        description: "Ver sesiones anteriores",
        aliases: &["resume", "continue"],
    },
    SlashCommand {
        name: "memory",
        description: "Ver episodios recientes",
        aliases: &[],
    },
    SlashCommand {
        name: "status",
        description: "Estado de providers",
        aliases: &[],
    },
    SlashCommand {
        name: "doctor",
        description: "Correr diagnóstico",
        aliases: &[],
    },
    SlashCommand {
        name: "model",
        description: "Cambiar modelo para el proveedor activo",
        aliases: &[],
    },
    SlashCommand {
        name: "models",
        description: "Elegir modelo desde el catálogo de proveedores",
        aliases: &[],
    },
    SlashCommand {
        name: "provider",
        description: "Configurar proveedor (cli | oauth | api | local)",
        aliases: &[],
    },
    SlashCommand {
        name: "login",
        description: "Login OAuth: openai | claude",
        aliases: &[],
    },
    SlashCommand {
        name: "logout",
        description: "Borrar token OAuth guardado",
        aliases: &[],
    },
    SlashCommand {
        name: "auth",
        description: "Ver estado OAuth guardado",
        aliases: &[],
    },
    SlashCommand {
        name: "clear",
        description: "Limpiar el chat log",
        aliases: &[],
    },
    SlashCommand {
        name: "themes",
        description: "Elegir el tema visual",
        aliases: &[],
    },
    SlashCommand {
        name: "help",
        description: "Mostrar ayuda",
        aliases: &[],
    },
];

/// Resolve a command name or known alias to its canonical registry name.
/// Unknown commands remain unknown so existing backend command handling is
/// preserved for commands the TUI does not list yet.
pub fn canonical_command(name: &str) -> Option<&'static str> {
    COMMANDS.iter().find_map(|command| {
        (command.name.eq_ignore_ascii_case(name)
            || command
                .aliases
                .iter()
                .any(|alias| alias.eq_ignore_ascii_case(name)))
        .then_some(command.name)
    })
}

/// The keyboard input that the slash-command palette handles itself.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SlashPaletteKey {
    Enter,
    Tab,
}

/// The one action a slash-command palette key may request from its caller.
/// Keeping this decision in `commands` ensures Home and Chat cannot drift.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SlashPaletteAction {
    Complete,
    Dispatch,
}

/// Decide whether a palette key completes the selected command or submits it.
///
/// Tab is always completion. Enter dispatches only a bare, exact registered
/// command name or alias; prefixes, unknown text, and inputs with arguments
/// complete the highlighted command instead. `slash_command_line` remains
/// responsible for normalizing the alias at dispatch time.
pub fn slash_palette_action(input: &str, key: SlashPaletteKey) -> SlashPaletteAction {
    if key == SlashPaletteKey::Tab {
        return SlashPaletteAction::Complete;
    }

    let is_exact_bare_command = slash_query(input)
        .filter(|query| !query.is_empty())
        .and_then(canonical_command)
        .is_some();

    if is_exact_bare_command {
        SlashPaletteAction::Dispatch
    } else {
        SlashPaletteAction::Complete
    }
}

/// Returns canonical commands whose name or aliases start with `query` (the
/// text typed after `/`, lowercased). Each command is inspected once, so an
/// alias never creates a duplicate action in the overlay.
pub fn matching_commands(query: &str) -> Vec<&'static SlashCommand> {
    let query = query.to_lowercase();
    COMMANDS
        .iter()
        .filter(|command| {
            command.name.starts_with(query.as_str())
                || command
                    .aliases
                    .iter()
                    .any(|alias| alias.starts_with(query.as_str()))
        })
        .collect()
}

/// Extract the command query from raw input, e.g. `"/mod"` -> `Some("mod")`,
/// `"/model gpt"` -> `None` (once there's a space, we're past the command
/// name and into arguments — the overlay should not show anymore).
/// `"hello"` -> `None` (not a slash command at all).
pub fn slash_query(input: &str) -> Option<&str> {
    let rest = input.strip_prefix('/')?;
    if rest.contains(' ') {
        None
    } else {
        Some(rest)
    }
}

/// Parsed name+args from a *complete* submitted line, e.g.
/// `"/model deepseek"` -> `Some(("model", vec!["deepseek"]))`,
/// `"/status"` -> `Some(("status", vec![]))`. Returns `None` for anything
/// not starting with `/` — that's a normal chat message, not a command.
/// Unlike `slash_query` (used for the live overlay while typing), this
/// runs once on Enter and always returns a full command, even with args.
pub fn slash_command_line(input: &str) -> Option<(&str, Vec<String>)> {
    let rest = input.trim().strip_prefix('/')?;
    let mut parts = rest.split_whitespace();
    let name = parts.next().unwrap_or("");
    if name.is_empty() {
        return None;
    }
    let args = parts.map(str::to_string).collect();
    Some((canonical_command(name).unwrap_or(name), args))
}
