use std::path::{Path, PathBuf};

use stock_select::config::{
    default_runtime_root_from_home, resolve_config_value_from, resolve_dsn_from_sources,
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
