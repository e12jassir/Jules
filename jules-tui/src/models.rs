//! Model catalog for the `/models` picker overlay — mirrors the
//! provider-grouped model list from OpenCode's TUI (`ctrl+a`/model select
//! popup), adapted to Jules' own provider set. Data below is hardcoded
//! (mock, same status as `AppState::active_model`/`active_provider` in
//! app.rs) until Batch 1 wires the real provider/model list from the
//! backend.

/// One selectable model entry within a provider group.
#[derive(Debug, Clone, Copy)]
pub struct ModelEntry {
    pub name: &'static str,
    pub full_name: &'static str,
    pub free: bool,
}

/// A provider section in the picker, e.g. "Google" grouping several
/// `ModelEntry` rows underneath it with a provider icon.
#[derive(Debug, Clone, Copy)]
pub struct ProviderGroup {
    pub provider: &'static str,
    pub icon: &'static str,
    pub models: &'static [ModelEntry],
}

pub const PROVIDER_GROUPS: &[ProviderGroup] = &[
    ProviderGroup {
        provider: "Anthropic / Claude",
        icon: "✦",
        models: &[
            ModelEntry { name: "claude-3.7-sonnet", full_name: "openrouter/anthropic/claude-3.7-sonnet", free: false },
            ModelEntry { name: "claude-3.5-haiku", full_name: "openrouter/anthropic/claude-3.5-haiku", free: false },
        ],
    },
    ProviderGroup {
        provider: "OpenAI / GPT",
        icon: "⚡",
        models: &[
            ModelEntry { name: "gpt-4o", full_name: "openrouter/openai/gpt-4o", free: false },
            ModelEntry { name: "gpt-4o-mini", full_name: "openrouter/openai/gpt-4o-mini", free: false },
            ModelEntry { name: "gpt-5.4-mini", full_name: "codex/openai/gpt-5.4-mini", free: true },
        ],
    },
    ProviderGroup {
        provider: "Google Gemini",
        icon: "◈",
        models: &[
            ModelEntry { name: "gemini-2.5-flash", full_name: "google/gemini-2.5-flash", free: true },
            ModelEntry { name: "gemini-2.5-pro", full_name: "google/gemini-2.5-pro", free: false },
            ModelEntry { name: "gemini-3.5-flash-low", full_name: "antigravity/gemini-3.5-flash-low", free: true },
        ],
    },
    ProviderGroup {
        provider: "OpenRouter",
        icon: "⌁",
        models: &[
            ModelEntry { name: "deepseek-r1", full_name: "openrouter/deepseek/deepseek-r1", free: false },
            ModelEntry { name: "deepseek-chat", full_name: "openrouter/deepseek/deepseek-chat", free: false },
            ModelEntry { name: "free", full_name: "openrouter/openrouter/free", free: true },
            ModelEntry { name: "nemotron-3-nano-30b-a3b:free", full_name: "openrouter/nvidia/nemotron-3-nano-30b-a3b:free", free: true },
        ],
    },
    ProviderGroup {
        provider: "OpenCode Zen",
        icon: "⌥",
        models: &[
            ModelEntry { name: "deepseek-v4-flash-free", full_name: "opencode/deepseek-v4-flash-free", free: true },
            ModelEntry { name: "laguna-s-2.1-free", full_name: "opencode/laguna-s-2.1-free", free: true },
            ModelEntry { name: "mimo-v2.5-free", full_name: "opencode/mimo-v2.5-free", free: true },
        ],
    },
    ProviderGroup {
        provider: "Ollama Local",
        icon: "🦙",
        models: &[
            ModelEntry { name: "llama3.2:1b", full_name: "ollama/llama3.2:1b", free: true },
        ],
    },
];

/// Flattened `(provider, icon, model)` row used for rendering and filtering the
/// picker as a single navigable list.
#[derive(Debug, Clone, Copy)]
pub struct ModelRow {
    pub provider: &'static str,
    pub icon: &'static str,
    pub model: ModelEntry,
}

/// Helper function to get icon for a provider.
pub fn get_provider_icon(provider: &str) -> &'static str {
    for group in PROVIDER_GROUPS {
        if group.provider.eq_ignore_ascii_case(provider) || provider.to_lowercase().contains(&group.provider.to_lowercase()) {
            return group.icon;
        }
    }
    "○"
}

/// Builds the flattened, filterable row list matching `query`.
/// Providers with 0 configured models are automatically omitted until models exist for them.
pub fn filtered_rows(query: &str) -> Vec<ModelRow> {
    let query = query.to_lowercase();
    let mut rows = Vec::new();
    for group in PROVIDER_GROUPS {
        if group.models.is_empty() {
            continue; // Skip providers with no models
        }
        for model in group.models {
            let matches = query.is_empty()
                || model.name.to_lowercase().contains(&query)
                || group.provider.to_lowercase().contains(&query);
            if !matches {
                continue;
            }
            rows.push(ModelRow {
                provider: group.provider,
                icon: group.icon,
                model: *model,
            });
        }
    }
    rows
}

