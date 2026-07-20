use std::path::{Path, PathBuf};

use std::collections::BTreeSet;
use stock_select::config::{
    default_runtime_root_from_home, resolve_config_value_from,
    resolve_db_check_tables_from_sources, resolve_dsn_from_sources,
    resolve_runtime_root_from_sources,
};

#[test]
fn config_value_uses_cli_then_shell_then_dotenv() {
    let dotenv = "POSTGRES_DSN=postgresql://dotenv\nTUSHARE_TOKEN='dotenv-token'\n";

    assert_eq!(
        resolve_config_value_from(
            Some("cli-token"),
            Some("shell-token"),
            dotenv,
            "TUSHARE_TOKEN"
        ),
        Some("cli-token".to_string())
    );
    assert_eq!(
        resolve_config_value_from(None, Some("shell-token"), dotenv, "TUSHARE_TOKEN"),
        Some("shell-token".to_string())
    );
    assert_eq!(
        resolve_config_value_from(None, None, dotenv, "TUSHARE_TOKEN"),
        Some("dotenv-token".to_string())
    );
}

#[test]
fn dsn_uses_postgres_dsn_sources() {
    let dsn = resolve_dsn_from_sources(
        None,
        Some("postgresql://shell"),
        "POSTGRES_DSN=postgresql://dotenv\n",
    )
    .unwrap();

    assert_eq!(dsn, "postgresql://shell");
}

#[test]
fn default_runtime_root_matches_old_cli_layout() {
    assert_eq!(
        default_runtime_root_from_home(Some(Path::new("/home/tester"))),
        PathBuf::from("/home/tester/.agents/skills/stock-select/runtime")
    );
    assert_eq!(
        default_runtime_root_from_home(None),
        PathBuf::from("./runtime")
    );
}

#[test]
fn runtime_root_uses_cli_then_shell_then_dotenv_then_old_default() {
    let dotenv = "STOCK_SELECT_RUNTIME_ROOT=runtime-from-dotenv\n";
    let fallback_home = Some(Path::new("/home/tester"));

    assert_eq!(
        resolve_runtime_root_from_sources(
            Some(Path::new("runtime-from-cli")),
            Some("runtime-from-shell"),
            dotenv,
            fallback_home,
        ),
        PathBuf::from("runtime-from-cli")
    );
    assert_eq!(
        resolve_runtime_root_from_sources(None, Some("runtime-from-shell"), dotenv, fallback_home),
        PathBuf::from("runtime-from-shell")
    );
    assert_eq!(
        resolve_runtime_root_from_sources(None, None, dotenv, fallback_home),
        PathBuf::from("runtime-from-dotenv")
    );
    assert_eq!(
        resolve_runtime_root_from_sources(None, None, "", fallback_home),
        PathBuf::from("/home/tester/.agents/skills/stock-select/runtime")
    );
}

#[test]
fn db_check_tables_use_defaults_until_explicitly_configured() {
    let defaults = BTreeSet::from([
        "index_idx_factor_pro".to_string(),
        "index_limit_cpt_list".to_string(),
        "index_moneyflow_cnt_ths".to_string(),
        "index_ths_daily".to_string(),
        "stock_stk_factor_pro".to_string(),
    ]);

    assert_eq!(
        resolve_db_check_tables_from_sources(None, "").unwrap(),
        defaults
    );
    assert_eq!(
        resolve_db_check_tables_from_sources(Some(""), "STOCK_SELECT_DB_CHECK=index_ths_daily\n")
            .unwrap(),
        BTreeSet::from(["stock_stk_factor_pro".to_string()])
    );
    assert_eq!(
        resolve_db_check_tables_from_sources(None, "STOCK_SELECT_DB_CHECK=\n").unwrap(),
        BTreeSet::from(["stock_stk_factor_pro".to_string()])
    );
    assert_eq!(
        resolve_db_check_tables_from_sources(
            Some(" INDEX_THS_DAILY, stock_moneyflow_ths, index_ths_daily, "),
            "",
        )
        .unwrap(),
        BTreeSet::from([
            "index_ths_daily".to_string(),
            "stock_moneyflow_ths".to_string(),
            "stock_stk_factor_pro".to_string(),
        ])
    );
}

#[test]
fn db_check_tables_reject_unknown_or_qualified_names() {
    let unknown = resolve_db_check_tables_from_sources(Some("missing_table"), "")
        .unwrap_err()
        .to_string();
    assert!(unknown.contains("missing_table"));
    assert!(unknown.contains("index_ths_daily"));

    for value in ["public.index_ths_daily", "index_*", "*"] {
        assert!(
            resolve_db_check_tables_from_sources(Some(value), "").is_err(),
            "{value} should be rejected"
        );
    }
}
