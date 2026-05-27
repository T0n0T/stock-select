use std::fs;

use chrono::NaiveDate;
use stock_select_rs::cli::{
    PoolSource, filter_custom_pool_rows_for_test, resolve_custom_pool_codes_for_test,
};
use stock_select_rs::model::PreparedRow;

fn prepared(code: &str) -> PreparedRow {
    PreparedRow {
        ts_code: code.to_string(),
        trade_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
        open: 1.0,
        high: 1.0,
        low: 1.0,
        close: 1.0,
        volume: 1.0,
        turnover_n: 1.0,
        k: 50.0,
        d: 50.0,
        j: 50.0,
        zxdq: Some(1.0),
        zxdkx: Some(1.0),
        dif: 0.0,
        dea: 0.0,
        macd_hist: 0.0,
        ma25: Some(2.0),
        ma60: Some(1.0),
        ma144: Some(1.0),
        chg_d: Some(1.0),
        weekly_ma_bull: true,
        max_vol_not_bearish: true,
        v_shrink: true,
        safe_mode: true,
        lt_filter: true,
        yellow_b1: false,
    }
}

#[test]
fn custom_pool_codes_normalize_and_deduplicate_tokens() {
    let temp = tempfile::tempdir().unwrap();
    let pool_file = temp.path().join("pool.txt");
    fs::write(&pool_file, "603138 300058.SZ junk-000001 603138.SH\n").unwrap();

    let resolved =
        resolve_custom_pool_codes_for_test(Some(pool_file.clone()), temp.path()).unwrap();

    assert_eq!(resolved.path, pool_file);
    assert_eq!(resolved.codes, vec!["603138.SH", "300058.SZ", "000001.SZ"]);
}

#[test]
fn custom_pool_intersects_with_prepared_universe_in_prepared_order() {
    let temp = tempfile::tempdir().unwrap();
    let pool_file = temp.path().join("pool.txt");
    fs::write(&pool_file, "300058 603138 000001").unwrap();
    let prepared = vec![
        prepared("000001.SZ"),
        prepared("300058.SZ"),
        prepared("688001.SH"),
    ];

    let filtered = filter_custom_pool_rows_for_test(
        &prepared,
        NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
        PoolSource::Custom,
        Some(pool_file),
        temp.path(),
    )
    .unwrap();

    let codes = filtered
        .iter()
        .map(|row| row.ts_code.as_str())
        .collect::<Vec<_>>();
    assert_eq!(codes, vec!["000001.SZ", "300058.SZ"]);
}
