use assert_cmd::Command;
use chrono::{Duration, NaiveDate};
use predicates::prelude::*;
use serde_json::Value;
use stock_select::cache::{prepared_cache_start_date, write_prepared_cache};
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
fn b3_screen_export_factors_without_cached_environment_reaches_daily_loader() {
    let temp = tempfile::tempdir().unwrap();
    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.current_dir(temp.path())
        .env_remove("POSTGRES_DSN")
        .args([
            "screen",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-06-09",
            "--method",
            "b3",
            "--export-factors",
        ])
        .assert()
        .failure()
        .stderr(predicate::str::contains("A database DSN is required."))
        .stderr(predicate::str::contains("No manual, persisted, or prepared").not());
}

#[test]
fn b2_screen_accepts_pool_file_for_custom_pool() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_two_code_cache(temp.path(), pick_date);
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
    let rows = [
        b2_positive_monthly_rows("000001.SZ", pick_date, 10.0),
        b2_positive_monthly_rows("000002.SZ", pick_date, 20.0),
    ]
    .into_iter()
    .flatten()
    .collect::<Vec<_>>();
    write_prepared_cache(
        root,
        Method::B2,
        pick_date,
        prepared_cache_start_date(pick_date),
        pick_date,
        &rows,
    )
    .unwrap();
}

fn b2_positive_monthly_rows(code: &str, pick_date: NaiveDate, base_close: f64) -> Vec<PreparedRow> {
    let len = 90;
    let first_date = pick_date - Duration::days((len - 1) as i64);
    let mut rows = (0..len)
        .map(|offset| {
            let close = base_close + offset as f64 * 0.03;
            prepared_row_at_date(
                code,
                first_date + Duration::days(offset as i64),
                close,
                1000.0,
                25.0,
            )
        })
        .collect::<Vec<_>>();
    let prev2 = len - 3;
    let prev = len - 2;
    let latest = len - 1;
    rows[prev2].close = rows[prev].close - 0.05;
    rows[prev2].open = rows[prev2].close - 0.2;
    rows[prev2].high = rows[prev2].close;
    rows[prev2].low = rows[prev2].close - 0.3;
    rows[prev2].j = 28.0;
    rows[prev].close = rows[prev2].close + 0.10;
    rows[prev].open = rows[prev].close - 0.2;
    rows[prev].high = rows[prev].close;
    rows[prev].low = rows[prev].close - 0.3;
    rows[prev].j = 32.0;
    rows[latest].close = rows[prev].close * 1.04;
    rows[latest].open = rows[latest].close - 0.8;
    rows[latest].high = rows[latest].close;
    rows[latest].low = rows[latest].close - 0.3;
    rows[latest].volume = rows[prev].volume + 500.0;
    rows[latest].turnover_n = rows[latest].volume * rows[latest].close;
    rows[latest].j = 45.0;
    rows
}

fn prepared_row_at_date(
    code: &str,
    trade_date: NaiveDate,
    close: f64,
    volume: f64,
    j: f64,
) -> PreparedRow {
    PreparedRow {
        ts_code: code.to_string(),
        trade_date,
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
