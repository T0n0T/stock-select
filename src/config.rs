use std::env;
use std::path::PathBuf;

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

pub fn resolve_dsn_from_env(cli_dsn: Option<&str>) -> Result<String, ConfigError> {
    let env_value = env::var("POSTGRES_DSN").ok();
    resolve_dsn(cli_dsn, env_value.as_deref())
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
