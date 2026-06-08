# Delta for textual-tui

## MODIFIED Requirements

### Requirement: TUI Launch

The system MUST open the Rust TUI when `jules` is invoked with no arguments. The system MUST open the Textual TUI when `jules --legacy` is invoked. The system MUST preserve `jules doctor` as a classic CLI command that does NOT launch any TUI.
(Previously: `jules` with no arguments opened the Textual TUI unconditionally.)

#### Scenario: No-arg launch opens Rust TUI

- GIVEN Jules is installed and the Rust binary is present in PATH
- WHEN the user runs `jules` with no arguments
- THEN the Rust TUI MUST open

#### Scenario: --legacy flag opens Textual TUI

- GIVEN Jules is installed
- WHEN the user runs `jules --legacy`
- THEN the Textual TUI MUST open and display the WelcomeScreen

#### Scenario: Doctor remains classic CLI

- GIVEN Jules is installed
- WHEN the user runs `jules doctor`
- THEN output MUST be plain text to stdout without launching any TUI

## REMOVED Requirements

### Requirement: Startup Budget (Textual)

(Reason: The 500ms startup budget applied to the Textual TUI. The Rust TUI replaces it as the default entrypoint with a 10ms budget defined in the `rust-tui` spec. The Textual TUI is now a fallback; its startup budget is no longer enforced as a primary system requirement.)
