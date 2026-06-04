use std::env;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConfigError {
    MissingDsn,
}

impl std::fmt::Display for ConfigError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MissingDsn => write!(f, "A database DSN is required."),
        }
    }
}

impl std::error::Error for ConfigError {}

pub fn resolve_config_value(cli_value: Option<&str>, env_name: &str) -> Option<String> {
    let env_value = env::var(env_name).ok();
    let dotenv = std::fs::read_to_string(".env").unwrap_or_default();
    resolve_config_value_from(cli_value, env_value.as_deref(), &dotenv, env_name)
}

pub fn resolve_config_value_from(
    cli_value: Option<&str>,
    env_value: Option<&str>,
    dotenv_content: &str,
    env_name: &str,
) -> Option<String> {
    if let Some(value) = non_empty(cli_value) {
        return Some(value.to_string());
    }
    if let Some(value) = non_empty(env_value) {
        return Some(value.to_string());
    }
    parse_dotenv_value(dotenv_content, env_name)
}

pub fn resolve_dsn_from_env(cli_dsn: Option<&str>) -> Result<String, ConfigError> {
    resolve_config_value(cli_dsn, "POSTGRES_DSN").ok_or(ConfigError::MissingDsn)
}

pub fn resolve_dsn_from_sources(
    cli_dsn: Option<&str>,
    env_dsn: Option<&str>,
    dotenv_content: &str,
) -> Result<String, ConfigError> {
    resolve_config_value_from(cli_dsn, env_dsn, dotenv_content, "POSTGRES_DSN")
        .ok_or(ConfigError::MissingDsn)
}

pub fn default_runtime_root() -> PathBuf {
    resolve_runtime_root(None)
}

pub fn resolve_runtime_root(cli_runtime_root: Option<&Path>) -> PathBuf {
    let env_value = env::var("STOCK_SELECT_RUNTIME_ROOT").ok();
    let dotenv = std::fs::read_to_string(".env").unwrap_or_default();
    resolve_runtime_root_from_sources(
        cli_runtime_root,
        env_value.as_deref(),
        &dotenv,
        env::var_os("HOME").as_deref().map(Path::new),
    )
}

pub fn resolve_runtime_root_from_sources(
    cli_runtime_root: Option<&Path>,
    env_runtime_root: Option<&str>,
    dotenv_content: &str,
    fallback_home: Option<&Path>,
) -> PathBuf {
    if let Some(path) = cli_runtime_root {
        return path.to_path_buf();
    }
    if let Some(value) = resolve_config_value_from(
        None,
        env_runtime_root,
        dotenv_content,
        "STOCK_SELECT_RUNTIME_ROOT",
    ) {
        return PathBuf::from(value);
    }
    default_runtime_root_from_home(fallback_home)
}

pub fn default_runtime_root_from_home(home: Option<&Path>) -> PathBuf {
    match home {
        Some(home) => home
            .join(".agents")
            .join("skills")
            .join("stock-select")
            .join("runtime"),
        None => PathBuf::from(".").join("runtime"),
    }
}

fn parse_dotenv_value(content: &str, key: &str) -> Option<String> {
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some((left, right)) = trimmed.split_once('=') else {
            continue;
        };
        if left.trim() != key {
            continue;
        }
        let value = strip_dotenv_quotes(right.trim());
        if let Some(value) = non_empty(Some(value)) {
            return Some(value.to_string());
        }
    }
    None
}

fn strip_dotenv_quotes(value: &str) -> &str {
    if value.len() >= 2 {
        let bytes = value.as_bytes();
        if (bytes[0] == b'"' && bytes[value.len() - 1] == b'"')
            || (bytes[0] == b'\'' && bytes[value.len() - 1] == b'\'')
        {
            return &value[1..value.len() - 1];
        }
    }
    value
}

fn non_empty(value: Option<&str>) -> Option<&str> {
    value.map(str::trim).filter(|item| !item.is_empty())
}
