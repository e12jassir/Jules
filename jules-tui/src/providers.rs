//! Provider definitions and API Key management for the `/provider` overlay picker.

use std::env;
use std::fs;
use std::path::PathBuf;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuthKind {
    ApiKey,
    OAuth,
    None,
}

#[derive(Debug, Clone, Copy)]
pub struct ProviderItem {
    pub id: &'static str,
    pub name: &'static str,
    pub icon: &'static str,
    pub category: &'static str,
    pub auth_kind: AuthKind,
    pub env_var: &'static str,
    pub default_model: &'static str,
    pub description: &'static str,
}

pub const PROVIDERS: &[ProviderItem] = &[
    ProviderItem {
        id: "openrouter",
        name: "OpenRouter",
        icon: "⌁",
        category: "Populares",
        auth_kind: AuthKind::ApiKey,
        env_var: "OPENROUTER_API_KEY",
        default_model: "openrouter:anthropic/claude-3.7-sonnet",
        description: "Acceso a Claude 3.7, GPT-4o, Gemini, DeepSeek, etc.",
    },
    ProviderItem {
        id: "google",
        name: "Google Gemini API",
        icon: "◈",
        category: "Populares",
        auth_kind: AuthKind::ApiKey,
        env_var: "GOOGLE_AI_API_KEY",
        default_model: "google:gemini-2.5-flash",
        description: "API directa de Google (Gemini 2.5 Flash / Pro)",
    },
    ProviderItem {
        id: "openai",
        name: "OpenAI / GPT",
        icon: "⚡",
        category: "Populares",
        auth_kind: AuthKind::ApiKey,
        env_var: "OPENAI_API_KEY",
        default_model: "openai_oauth:gpt-5.4-mini",
        description: "API Key de OpenAI (GPT-4o, GPT-4o-mini)",
    },
    ProviderItem {
        id: "anthropic",
        name: "Anthropic / Claude",
        icon: "✦",
        category: "Populares",
        auth_kind: AuthKind::ApiKey,
        env_var: "ANTHROPIC_API_KEY",
        default_model: "openrouter:anthropic/claude-3.7-sonnet",
        description: "API Key de Anthropic para modelos Claude",
    },
    ProviderItem {
        id: "opencode",
        name: "OpenCode Zen",
        icon: "⌥",
        category: "Libres & Locales",
        auth_kind: AuthKind::None,
        env_var: "",
        default_model: "opencode:deepseek-v4-flash-free",
        description: "Servidor libre con modelos DeepSeek, Laguna, Mimo",
    },
    ProviderItem {
        id: "antigravity",
        name: "Antigravity",
        icon: "✦",
        category: "Libres & Locales",
        auth_kind: AuthKind::None,
        env_var: "",
        default_model: "antigravity:gemini-3.5-flash-low",
        description: "Modelos optimizados AGY",
    },
    ProviderItem {
        id: "ollama",
        name: "Ollama Local",
        icon: "🦙",
        category: "Libres & Locales",
        auth_kind: AuthKind::None,
        env_var: "",
        default_model: "ollama:llama3.2:1b",
        description: "Modelos locales ejecutados en tu máquina",
    },
];

pub fn get_env_file_path() -> PathBuf {
    let home = env::var("HOME").unwrap_or_else(|_| ".".to_string());
    let mut path = PathBuf::from(home);
    path.push(".jules");
    path.push(".env");
    path
}

pub fn is_key_configured(env_var: &str) -> bool {
    if env_var.is_empty() {
        return false;
    }
    if env::var(env_var).map(|v| !v.trim().is_empty()).unwrap_or(false) {
        return true;
    }
    let path = get_env_file_path();
    if path.exists() {
        if let Ok(content) = fs::read_to_string(&path) {
            for line in content.lines() {
                if let Some((k, v)) = line.split_once('=') {
                    if k.trim() == env_var && !v.trim().is_empty() {
                        return true;
                    }
                }
            }
        }
    }
    false
}

pub fn save_api_key(env_var: &str, key: &str) -> Result<(), String> {
    if env_var.is_empty() {
        return Err("No hay variable de entorno especificada para este proveedor".to_string());
    }
    env::set_var(env_var, key);

    let path = get_env_file_path();
    if let Some(parent) = path.parent() {
        let _ = fs::create_dir_all(parent);
    }

    let mut lines = Vec::new();
    if path.exists() {
        if let Ok(content) = fs::read_to_string(&path) {
            for line in content.lines() {
                if !line.trim().starts_with(&format!("{env_var}=")) {
                    lines.push(line.to_string());
                }
            }
        }
    }
    lines.push(format!("{env_var}={key}"));
    fs::write(&path, lines.join("\n") + "\n").map_err(|e| e.to_string())
}

pub fn delete_api_key(env_var: &str) -> Result<(), String> {
    if env_var.is_empty() {
        return Err("No hay variable de entorno especificada para este proveedor".to_string());
    }
    env::remove_var(env_var);

    let path = get_env_file_path();
    if path.exists() {
        if let Ok(content) = fs::read_to_string(&path) {
            let lines: Vec<String> = content
                .lines()
                .filter(|line| !line.trim().starts_with(&format!("{env_var}=")))
                .map(|line| line.to_string())
                .collect();
            fs::write(&path, lines.join("\n") + "\n").map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}
