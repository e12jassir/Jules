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
    assert_eq!(matches.len(), 1);
    assert_eq!(matches[0].name, "model");

    let all = matching_commands("");
    assert_eq!(all.len(), 13);

    let none = matching_commands("zzz");
    assert!(none.is_empty());
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
