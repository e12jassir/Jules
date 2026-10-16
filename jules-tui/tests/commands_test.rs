#[path = "../src/commands.rs"]
mod commands;

use commands::{matching_commands, slash_query};

#[test]
fn slash_query_detects_command_in_progress() {
    assert_eq!(slash_query("/mod"), Some("mod"));
    assert_eq!(slash_query("/"), Some(""));
    assert_eq!(slash_query("/model gpt"), None);
    assert_eq!(slash_query("hello"), None);
    assert_eq!(slash_query(""), None);
}

#[test]
fn matching_commands_filters_by_prefix() {
    let matches = matching_commands("mod");
    assert_eq!(matches.len(), 2);
    assert_eq!(matches[0].name, "model");
    assert_eq!(matches[1].name, "models");

    let all = matching_commands("");
    assert_eq!(all.len(), 14);

    let none = matching_commands("zzz");
    assert!(none.is_empty());
}

#[test]
fn matching_commands_finds_aliases_without_duplicate_actions() {
    let resume = matching_commands("res");
    assert_eq!(resume.len(), 1);
    assert_eq!(resume[0].name, "sessions");

    let continue_alias = matching_commands("continue");
    assert_eq!(continue_alias.len(), 1);
    assert_eq!(continue_alias[0].name, "sessions");
}

#[test]
fn slash_command_line_normalizes_session_aliases() {
    use commands::slash_command_line;

    assert_eq!(
        slash_command_line("/resume"),
        Some(("sessions", Vec::new()))
    );
    assert_eq!(
        slash_command_line("/continue project-123"),
        Some(("sessions", vec!["project-123".to_string()]))
    );
}

#[test]
fn slash_command_line_parses_name_and_args() {
    use commands::slash_command_line;

    assert_eq!(slash_command_line("hello"), None);
    assert_eq!(slash_command_line("/"), None);
    assert_eq!(
        slash_command_line("/status"),
        Some(("status", Vec::<String>::new()))
    );
    assert_eq!(
        slash_command_line("/model deepseek-v4-flash-free"),
        Some(("model", vec!["deepseek-v4-flash-free".to_string()]))
    );
    assert_eq!(
        slash_command_line("/provider cli opencode"),
        Some(("provider", vec!["cli".to_string(), "opencode".to_string()]))
    );
}

#[test]
fn slash_palette_enter_dispatches_exact_model_and_session_commands() {
    use commands::{slash_palette_action, SlashPaletteAction, SlashPaletteKey};

    for input in ["/models", "/sessions", "/resume", "/continue"] {
        assert_eq!(
            slash_palette_action(input, SlashPaletteKey::Enter),
            SlashPaletteAction::Dispatch,
            "{input} should dispatch on the first Enter"
        );
    }
}

#[test]
fn slash_palette_tab_only_completes_the_selected_command() {
    use commands::{slash_palette_action, SlashPaletteAction, SlashPaletteKey};

    assert_eq!(
        slash_palette_action("/models", SlashPaletteKey::Tab),
        SlashPaletteAction::Complete
    );
    assert_eq!(
        slash_palette_action("/resume", SlashPaletteKey::Tab),
        SlashPaletteAction::Complete
    );
}

#[test]
fn slash_palette_enter_completes_ambiguous_prefix_instead_of_dispatching() {
    use commands::{slash_palette_action, SlashPaletteAction, SlashPaletteKey};

    assert_eq!(
        slash_palette_action("/mod", SlashPaletteKey::Enter),
        SlashPaletteAction::Complete
    );
}
