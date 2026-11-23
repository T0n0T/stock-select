use std::collections::BTreeSet;
use std::env;
use std::path::{Path, PathBuf};

pub const STOCK_SELECT_DB_CHECK_ENV: &str = "STOCK_SELECT_DB_CHECK";

pub const DB_CHECK_CORE_TABLES: &[&str] = &["stock_stk_factor_pro"];

pub const DB_CHECK_DEFAULT_TABLES: &[&str] = &[
    "index_idx_factor_pro",
    "index_weight",
    "stock_moneyflow",
    "index_sw_member",
    "calc_daily_industry_moneyflow",
];

pub const DB_CHECK_ALLOWED_TABLES: &[&str] = &[
    "stock_stk_factor_pro",
    "calc_daily_indicators",
    "calc_daily_rolling_factors",
    "calc_daily_czsc_structure",
    "calc_indicator_state",
    "stock_moneyflow",
    "index_weight",
    "index_sw_member",
    "index_idx_factor_pro",
    "calc_daily_industry_moneyflow",
    "index_limit_cpt_list",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ConfigError {
    MissingDuckDbPath,
}

impl std::fmt::Display for ConfigError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::MissingDuckDbPath => write!(
                f,
                "DUCKDB_PATH is required; set it in .env or pass --duckdb-path."
            ),
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

pub fn resolve_db_check_tables() -> anyhow::Result<BTreeSet<String>> {
    let env_value = env::var(STOCK_SELECT_DB_CHECK_ENV).ok();
    let dotenv = std::fs::read_to_string(".env").unwrap_or_default();
    resolve_db_check_tables_from_sources(env_value.as_deref(), &dotenv)
}

pub fn resolve_db_check_tables_from_sources(
    env_value: Option<&str>,
    dotenv_content: &str,
) -> anyhow::Result<BTreeSet<String>> {
    let configured = match env_value {
        Some(value) => Some(value.to_string()),
        None => parse_dotenv_value_preserving_empty(dotenv_content, STOCK_SELECT_DB_CHECK_ENV)
            .map(str::to_string),
    };

    let mut strict_tables = DB_CHECK_CORE_TABLES
        .iter()
        .map(|table| (*table).to_string())
        .collect::<BTreeSet<_>>();
    match configured {
        None => strict_tables.extend(
            DB_CHECK_DEFAULT_TABLES
                .iter()
                .map(|table| (*table).to_string()),
        ),
        Some(value) => {
            for raw_table in value.split(',') {
                let table = raw_table.trim().to_ascii_lowercase();
                if table.is_empty() {
                    continue;
                }
                if !DB_CHECK_ALLOWED_TABLES.contains(&table.as_str()) {
                    anyhow::bail!(
                        "unknown database table in {STOCK_SELECT_DB_CHECK_ENV}: {table}; allowed tables: {}",
                        DB_CHECK_ALLOWED_TABLES.join(", ")
                    );
                }
                strict_tables.insert(table);
            }
        }
    }
    Ok(strict_tables)
}

pub fn resolve_duckdb_path_from_env(cli_duckdb_path: Option<&str>) -> Result<String, ConfigError> {
    resolve_config_value(cli_duckdb_path, "DUCKDB_PATH").ok_or(ConfigError::MissingDuckDbPath)
}

pub fn resolve_duckdb_path_from_sources(
    cli_duckdb_path: Option<&str>,
    env_duckdb_path: Option<&str>,
    dotenv_content: &str,
) -> Result<String, ConfigError> {
    resolve_config_value_from(
        cli_duckdb_path,
        env_duckdb_path,
        dotenv_content,
        "DUCKDB_PATH",
    )
    .ok_or(ConfigError::MissingDuckDbPath)
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

fn parse_dotenv_value_preserving_empty<'a>(content: &'a str, key: &str) -> Option<&'a str> {
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let Some((left, right)) = trimmed.split_once('=') else {
            continue;
        };
        if left.trim() == key {
            return Some(strip_dotenv_quotes(right.trim()));
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
