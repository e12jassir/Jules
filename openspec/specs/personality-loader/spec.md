# Personality Loader Specification

## Purpose

Define how Jules loads, assembles, and injects its personality system prompt from versioned files on disk.

## Requirements

### Requirement: Load Master Personality

PersonalityLoader MUST load `~/.jules/personality/master.md` as the base system prompt for all provider interactions.

#### Scenario: Master file loaded

- GIVEN `~/.jules/personality/master.md` exists and is readable
- WHEN PersonalityLoader.load() is called
- THEN the returned system prompt MUST contain the full content of master.md

#### Scenario: Master file missing

- GIVEN `~/.jules/personality/master.md` does not exist
- WHEN PersonalityLoader.load() is called
- THEN the system MUST raise an error indicating the master personality file is required

### Requirement: Provider Preset Merge

PersonalityLoader MUST merge the provider-specific preset file (`local.md`, `antigravity.md`, `opencode.md`) when available. The system MUST fall back to master.md alone if the preset file is missing, without raising an error.

#### Scenario: Preset exists and merges

- GIVEN master.md exists AND `~/.jules/personality/antigravity.md` exists
- WHEN PersonalityLoader.load(provider="antigravity") is called
- THEN the returned prompt MUST contain master.md content followed by antigravity.md content

#### Scenario: Preset missing falls back silently

- GIVEN master.md exists AND `~/.jules/personality/opencode.md` does NOT exist
- WHEN PersonalityLoader.load(provider="opencode") is called
- THEN the returned prompt MUST contain only master.md content with no error raised

### Requirement: Version Detection

PersonalityLoader MUST detect when master.md version changes between sessions. The system MUST log a warning and notify the StatusBar. The system MUST NOT crash or block on version changes.

#### Scenario: Version change detected

- GIVEN master.md contained version "1.0" in the last session
- WHEN the current session loads master.md with version "1.1"
- THEN the system MUST log a warning about the version change AND notify the StatusBar

#### Scenario: Version unchanged

- GIVEN master.md version matches the last known version
- WHEN PersonalityLoader loads the file
- THEN no warning MUST be emitted and no StatusBar notification MUST appear

#### Scenario: Version check non-blocking

- GIVEN version detection encounters a read error on the stored version
- WHEN PersonalityLoader runs version detection
- THEN the system MUST log the error and continue loading without crashing or blocking

### Requirement: Prompt Injection

The assembled system prompt MUST be passed to every provider call. Providers MUST NOT construct system prompts independently.

#### Scenario: All providers receive assembled prompt

- GIVEN PersonalityLoader has assembled the system prompt
- WHEN any provider (Ollama, Antigravity, OpenCode) is invoked
- THEN the provider call MUST include the PersonalityLoader output as the system prompt

#### Scenario: Provider does not override prompt

- GIVEN a provider implementation exists
- WHEN it constructs a request to the upstream model
- THEN it MUST NOT define its own system prompt content — only the PersonalityLoader output SHALL be used
