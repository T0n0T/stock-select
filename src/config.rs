use std::env;
use std::path::{Path, PathBuf};

use chrono::{Duration, NaiveDate};
use thiserror::Error;

pub const DEFAULT_SCREEN_LOOKBACK_DAYS: i64 = 366;

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ConfigError {
    #[error("A database DSN is required.")]
    MissingDsn,
}

pub fn resolve_dsn(cli_dsn: Option<&str>, env_dsn: Option<&str>) -> Result<String, ConfigError> {
    if let Some(value) = non_empty(cli_dsn) {
        return Ok(value.to_string());
    }
    if let Some(value) = non_empty(env_dsn) {
        return Ok(value.to_string());
    }
    Err(ConfigError::MissingDsn)
}

pub fn resolve_config_value(cli_value: Option<&str>, env_name: &str) -> Option<String> {
    if let Some(value) = non_empty(cli_value) {
        return Some(value.to_string());
    }
    if let Some(value) = env::var(env_name)
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
    {
        return Some(value.to_string());
    }
    dotenv_value(Path::new(".env"), env_name)
}

pub fn resolve_dsn_from_env(cli_dsn: Option<&str>) -> Result<String, ConfigError> {
    resolve_config_value(cli_dsn, "POSTGRES_DSN").ok_or(ConfigError::MissingDsn)
}

pub fn default_runtime_root() -> PathBuf {
    match env::var_os("HOME") {
        Some(home) => PathBuf::from(home)
            .join(".agents")
            .join("skills")
            .join("stock-select")
            .join("runtime"),
        None => PathBuf::from(".").join("runtime"),
    }
}

pub fn screen_window(pick_date: NaiveDate) -> (NaiveDate, NaiveDate) {
    (
        pick_date - Duration::days(DEFAULT_SCREEN_LOOKBACK_DAYS),
        pick_date,
    )
}

fn non_empty(value: Option<&str>) -> Option<&str> {
    value.map(str::trim).filter(|item| !item.is_empty())
}

fn dotenv_value(path: &Path, key: &str) -> Option<String> {
    let content = std::fs::read_to_string(path).ok()?;
    parse_dotenv_value(&content, key)
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

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

    use super::*;

    #[test]
    fn cli_dsn_takes_precedence_over_env_dsn() {
        let dsn = resolve_dsn(Some("postgresql://cli"), Some("postgresql://env")).unwrap();
        assert_eq!(dsn, "postgresql://cli");
    }

    #[test]
    fn env_dsn_is_used_when_cli_dsn_missing() {
        let dsn = resolve_dsn(None, Some("postgresql://env")).unwrap();
        assert_eq!(dsn, "postgresql://env");
    }

    #[test]
    fn resolves_value_from_dotenv_when_cli_and_env_missing() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(
            temp.path().join(".env"),
            "\n# comment\nSTOCK_SELECT_RS_TEST_TOKEN = 'dotenv-token'\n",
        )
        .unwrap();
        let old_dir = std::env::current_dir().unwrap();
        std::env::set_current_dir(temp.path()).unwrap();

        let value = resolve_config_value(None, "STOCK_SELECT_RS_TEST_TOKEN").unwrap();

        std::env::set_current_dir(old_dir).unwrap();
        assert_eq!(value, "dotenv-token");
    }

    #[test]
    fn cli_value_takes_precedence_over_dotenv() {
        let temp = tempfile::tempdir().unwrap();
        std::fs::write(
            temp.path().join(".env"),
            "STOCK_SELECT_RS_TEST_TOKEN=dotenv-token\n",
        )
        .unwrap();
        let old_dir = std::env::current_dir().unwrap();
        std::env::set_current_dir(temp.path()).unwrap();

        let value = resolve_config_value(Some("cli-token"), "STOCK_SELECT_RS_TEST_TOKEN").unwrap();

        std::env::set_current_dir(old_dir).unwrap();
        assert_eq!(value, "cli-token");
    }

    #[test]
    fn missing_dsn_returns_clear_error() {
        let err = resolve_dsn(Some(" "), None).unwrap_err();
        assert_eq!(err, ConfigError::MissingDsn);
    }

    #[test]
    fn screen_window_uses_366_calendar_days() {
        let pick_date = NaiveDate::from_ymd_opt(2026, 5, 26).unwrap();
        let (start, end) = screen_window(pick_date);
        assert_eq!(start, NaiveDate::from_ymd_opt(2025, 5, 25).unwrap());
        assert_eq!(end, pick_date);
    }
}
