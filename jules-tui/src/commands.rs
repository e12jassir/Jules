//! Slash command definitions and matching for the command overlay.
//! Mirrors the command set from the Python/Textual prototype
//! (`jules/cli/commands.py`, now obsolete per user decision 2026-07-19),
//! adapted to the Rust frontend. Command *execution* is out of scope here
//! — this module only detects `/` input and lists matching commands; the
//! caller decides what happens on selection.

/// One registered slash command: name (without the leading `/`) and a
/// short human-readable description shown in the overlay.
pub struct SlashCommand {
    pub name: &'static str,
    pub description: &'static str,
}

pub const COMMANDS: &[SlashCommand] = &[
    SlashCommand { name: "exit", description: "Cerrar Jules" },
    SlashCommand { name: "sessions", description: "Ver sesiones anteriores" },
    SlashCommand { name: "memory", description: "Ver episodios recientes" },
    SlashCommand { name: "status", description: "Estado de providers" },
    SlashCommand { name: "doctor", description: "Correr diagnóstico" },
    SlashCommand { name: "model", description: "Cambiar modelo para el proveedor activo" },
    SlashCommand { name: "models", description: "Elegir modelo desde el catálogo de proveedores" },
    SlashCommand { name: "provider", description: "Configurar proveedor (cli | oauth | api | local)" },
    SlashCommand { name: "login", description: "Login OAuth: openai | claude" },
    SlashCommand { name: "logout", description: "Borrar token OAuth guardado" },
    SlashCommand { name: "auth", description: "Ver estado OAuth guardado" },
    SlashCommand { name: "clear", description: "Limpiar el chat log" },
    SlashCommand { name: "themes", description: "Elegir el tema visual" },
    SlashCommand { name: "help", description: "Mostrar ayuda" },
];

/// Returns commands whose name starts with `query` (the text typed after
/// `/`, lowercased). Empty query matches everything, mirroring the Python
/// prototype's overlay behavior of showing the full list right after `/`.
pub fn matching_commands(query: &str) -> Vec<&'static SlashCommand> {
    let query = query.to_lowercase();
    COMMANDS
        .iter()
        .filter(|c| c.name.starts_with(query.as_str()))
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
    Some((name, args))
}
