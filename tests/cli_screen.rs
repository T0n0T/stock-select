use assert_cmd::Command;
use chrono::NaiveDate;
use predicates::prelude::*;
use serde_json::Value;
use stock_select::cache::write_prepared_cache;
use stock_select::model::{Method, PreparedRow};

#[test]
fn b2_screen_requires_resolved_dsn_instead_of_stub_success() {
    let temp = tempfile::tempdir().unwrap();
    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.current_dir(temp.path())
        .env_remove("POSTGRES_DSN")
        .args([
            "screen",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
        ])
        .assert()
        .failure()
        .stderr(predicate::str::contains("A database DSN is required."));
}

#[test]
fn b2_screen_accepts_pool_file_for_custom_pool() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        NaiveDate::from_ymd_opt(2025, 5, 24).unwrap(),
        pick_date,
        &[
            prepared_row("000001.SZ", 23, 10.0, 1000.0, 45.0),
            prepared_row("000001.SZ", 24, 10.2, 1000.0, 30.0),
            prepared_row("000001.SZ", 25, 10.6, 1300.0, 42.0),
            prepared_row("000002.SZ", 23, 20.0, 1000.0, 45.0),
            prepared_row("000002.SZ", 24, 20.2, 1000.0, 30.0),
            prepared_row("000002.SZ", 25, 21.0, 1300.0, 42.0),
        ],
    )
    .unwrap();
    let pool_file = temp.path().join("pool.txt");
    std::fs::write(&pool_file, "000002").unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "screen",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--dsn",
        "postgresql://fixture",
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--pool-file",
        pool_file.to_str().unwrap(),
    ])
    .assert()
    .success();

    let payload: Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("candidates/2026-05-25.b2.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(payload["pool_source"], "custom");
    assert_eq!(payload["candidates"][0]["code"], "000002.SZ");
}

#[test]
fn b2_screen_reuses_prepared_cache_without_resolved_dsn() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_two_code_cache(temp.path(), pick_date);

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.current_dir(temp.path())
        .env_remove("POSTGRES_DSN")
        .args([
            "screen",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
        ])
        .assert()
        .success()
        .stdout(predicate::str::contains(
            "screen complete: candidates/2026-05-25.b2.json",
        ));

    assert!(temp.path().join("candidates/2026-05-25.b2.json").exists());
}

#[test]
fn b2_screen_pool_source_custom_uses_stock_select_pool_file() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_two_code_cache(temp.path(), pick_date);
    let pool_file = temp.path().join("env-pool.txt");
    std::fs::write(&pool_file, "000002").unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.env("STOCK_SELECT_POOL_FILE", &pool_file)
        .args([
            "screen",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--dsn",
            "postgresql://fixture",
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
            "--pool-source",
            "custom",
        ])
        .assert()
        .success();

    let payload: Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("candidates/2026-05-25.b2.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(payload["pool_source"], "custom");
    assert_eq!(payload["pool_file"], pool_file.to_string_lossy().as_ref());
    assert_eq!(payload["candidates"][0]["code"], "000002.SZ");
}

fn write_two_code_cache(root: &std::path::Path, pick_date: NaiveDate) {
    write_prepared_cache(
        root,
        Method::B2,
        pick_date,
        NaiveDate::from_ymd_opt(2025, 5, 24).unwrap(),
        pick_date,
        &[
            prepared_row("000001.SZ", 23, 10.0, 1000.0, 45.0),
            prepared_row("000001.SZ", 24, 10.2, 1000.0, 30.0),
            prepared_row("000001.SZ", 25, 10.6, 1300.0, 42.0),
            prepared_row("000002.SZ", 23, 20.0, 1000.0, 45.0),
            prepared_row("000002.SZ", 24, 20.2, 1000.0, 30.0),
            prepared_row("000002.SZ", 25, 21.0, 1300.0, 42.0),
        ],
    )
    .unwrap();
}

fn prepared_row(code: &str, day: u32, close: f64, volume: f64, j: f64) -> PreparedRow {
    PreparedRow {
        ts_code: code.to_string(),
        trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
        open: close - 0.2,
        high: close + 0.1,
        low: close - 0.3,
        close,
        volume,
        turnover_n: volume * close,
        turnover_rate: Some(volume / 100.0),
        k: 50.0,
        d: 40.0,
        j,
        zxdq: Some(close),
        zxdkx: Some(close - 0.5),
        dif: 0.3,
        dea: 0.2,
        macd_hist: 0.1,
        ma25: Some(close),
        ma60: Some(close - 1.0),
        ma144: None,
        chg_d: None,
        weekly_ma_bull: false,
        max_vol_not_bearish: true,
        v_shrink: false,
        safe_mode: true,
        lt_filter: true,
        yellow_b1: false,
        db_factors: Default::default(),
    }
}
