use chrono::{Datelike, NaiveDate};
use serde_json::json;
use stock_select::cache::{
    decode_prepared_cache_rows, history_payload_for_code, load_prepared_cache,
    load_prepared_cache_for_mode, prepared_cache_data_path, prepared_cache_meta_path,
    prepared_cache_paths, write_prepared_cache, write_prepared_cache_for_mode,
};
use stock_select::model::{Method, PreparedRow};

#[test]
fn prepared_cache_paths_match_old_cli_layout() {
    let root = tempfile::tempdir().unwrap();
    let date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    assert_eq!(
        prepared_cache_data_path(root.path(), date),
        root.path().join("prepared/2026-05-25.bin")
    );
    assert_eq!(
        prepared_cache_meta_path(root.path(), date),
        root.path().join("prepared/2026-05-25.meta.json")
    );
}

#[test]
fn prepared_cache_paths_support_intraday_layout_without_overwriting_eod() {
    let root = tempfile::tempdir().unwrap();
    let date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let eod = prepared_cache_paths(root.path(), date, false);
    let intraday = prepared_cache_paths(root.path(), date, true);

    assert_eq!(eod.data_path, root.path().join("prepared/2026-05-25.bin"));
    assert_eq!(
        eod.meta_path,
        root.path().join("prepared/2026-05-25.meta.json")
    );
    assert_eq!(
        intraday.data_path,
        root.path().join("prepared/2026-05-25.intraday.bin")
    );
    assert_eq!(
        intraday.meta_path,
        root.path().join("prepared/2026-05-25.intraday.meta.json")
    );
}

#[test]
fn decodes_old_prepared_cache_binary_row() {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"SSPRBIN1");
    write_u64(&mut bytes, 1);
    write_string(&mut bytes, "000001.SZ");
    write_i32(
        &mut bytes,
        NaiveDate::from_ymd_opt(2026, 5, 25)
            .unwrap()
            .num_days_from_ce(),
    );
    for value in [10.0, 11.0, 9.0, 10.5, 1000.0, 12.0] {
        write_f64(&mut bytes, value);
    }
    write_option_f64(&mut bytes, Some(1.5));
    for value in [50.0, 40.0, 60.0] {
        write_f64(&mut bytes, value);
    }
    write_option_f64(&mut bytes, Some(10.2));
    write_option_f64(&mut bytes, Some(10.1));
    for value in [0.3, 0.2, 0.1] {
        write_f64(&mut bytes, value);
    }
    write_option_f64(&mut bytes, Some(10.0));
    write_option_f64(&mut bytes, Some(9.8));
    write_option_f64(&mut bytes, None);
    write_option_f64(&mut bytes, Some(1.2));
    for value in [true, false, true, false, true, false] {
        write_bool(&mut bytes, value);
    }

    let rows = decode_prepared_cache_rows(&bytes).unwrap();

    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].ts_code, "000001.SZ");
    assert_eq!(
        rows[0].trade_date,
        NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()
    );
    assert_eq!(rows[0].close, 10.5);
    assert_eq!(rows[0].turnover_rate, Some(1.5));
    assert_eq!(rows[0].zxdq, Some(10.2));
    assert_eq!(rows[0].zxdkx, Some(10.1));
    assert_eq!(rows[0].ma25, Some(10.0));
    assert!(rows[0].weekly_ma_bull);
    assert!(!rows[0].yellow_b1);
}

#[test]
fn load_prepared_cache_requires_matching_metadata() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let data_path = prepared_cache_data_path(root.path(), pick_date);
    std::fs::create_dir_all(data_path.parent().unwrap()).unwrap();
    std::fs::write(&data_path, prepared_cache_bytes()).unwrap();

    assert!(
        load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
            .unwrap()
            .is_none()
    );

    std::fs::write(
        prepared_cache_meta_path(root.path(), pick_date),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b1", "b2", "dribull"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": 3,
            "row_count": 1,
            "symbol_count": 1,
            "source_table": "daily_market"
        }))
        .unwrap(),
    )
    .unwrap();

    let rows = load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();

    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].ts_code, "000001.SZ");
}

#[test]
fn intraday_prepared_cache_read_write_does_not_overwrite_eod_cache() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();

    write_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &[prepared_row("000001.SZ", pick_date, 10.0)],
    )
    .unwrap();
    write_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
        &[prepared_row("000001.SZ", pick_date, 12.0)],
    )
    .unwrap();

    let eod = load_prepared_cache(root.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();
    let intraday = load_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
    )
    .unwrap()
    .unwrap();

    assert_eq!(eod[0].close, 10.0);
    assert_eq!(intraday[0].close, 12.0);
    assert_eq!(
        serde_json::from_slice::<serde_json::Value>(
            &std::fs::read(prepared_cache_paths(root.path(), pick_date, true).meta_path).unwrap()
        )
        .unwrap()["mode"],
        "intraday_snapshot"
    );
}

#[test]
fn load_intraday_prepared_cache_accepts_previous_trade_date_window() {
    let root = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 4).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 6, 3).unwrap();
    let stored_start_date = previous_trade_date - chrono::Duration::days(366);
    let requested_start_date = pick_date - chrono::Duration::days(366);
    write_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        pick_date,
        stored_start_date,
        pick_date,
        true,
        &[prepared_row("000001.SZ", pick_date, 12.0)],
    )
    .unwrap();

    let rows = load_prepared_cache_for_mode(
        root.path(),
        Method::B2,
        pick_date,
        requested_start_date,
        pick_date,
        true,
    )
    .unwrap()
    .unwrap();

    assert_eq!(rows[0].close, 12.0);
}

#[test]
fn builds_history_payload_for_candidate_code_from_prepared_rows() {
    let date1 = NaiveDate::from_ymd_opt(2026, 5, 24).unwrap();
    let date2 = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let rows = vec![
        prepared_row("000002.SZ", date1, 20.0),
        prepared_row("000001.SZ", date2, 10.5),
        prepared_row("000001.SZ", date1, 10.0),
    ];

    let history = history_payload_for_code(&rows, "000001.SZ");

    assert_eq!(history.len(), 2);
    assert_eq!(history[0]["close"], 10.0);
    assert_eq!(history[1]["close"], 10.5);
    assert_eq!(history[1]["volume"], 1000.0);
    assert_eq!(history[1]["turnover_n"], 12.0);
    assert_eq!(history[1]["turnover_rate"], 1.5);
    assert_eq!(history[1]["ma25"], 10.0);
    assert_eq!(history[1]["zxdq"], 10.2);
    assert_eq!(history[1]["zxdkx"], 10.1);
    assert_eq!(history[1]["macd_hist"], 0.1);
}

fn prepared_row(code: &str, trade_date: NaiveDate, close: f64) -> PreparedRow {
    PreparedRow {
        ts_code: code.to_string(),
        trade_date,
        open: close - 0.5,
        high: close + 1.0,
        low: close - 1.0,
        close,
        volume: 1000.0,
        turnover_n: 12.0,
        turnover_rate: Some(1.5),
        k: 50.0,
        d: 40.0,
        j: 60.0,
        zxdq: Some(10.2),
        zxdkx: Some(10.1),
        dif: 0.3,
        dea: 0.2,
        macd_hist: 0.1,
        ma25: Some(10.0),
        ma60: Some(9.8),
        ma144: None,
        chg_d: Some(1.2),
        weekly_ma_bull: true,
        max_vol_not_bearish: false,
        v_shrink: true,
        safe_mode: false,
        lt_filter: true,
        yellow_b1: false,
    }
}

fn prepared_cache_bytes() -> Vec<u8> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"SSPRBIN1");
    write_u64(&mut bytes, 1);
    write_string(&mut bytes, "000001.SZ");
    write_i32(
        &mut bytes,
        NaiveDate::from_ymd_opt(2026, 5, 25)
            .unwrap()
            .num_days_from_ce(),
    );
    for value in [10.0, 11.0, 9.0, 10.5, 1000.0, 12.0] {
        write_f64(&mut bytes, value);
    }
    write_option_f64(&mut bytes, Some(1.5));
    for value in [50.0, 40.0, 60.0] {
        write_f64(&mut bytes, value);
    }
    write_option_f64(&mut bytes, Some(10.2));
    write_option_f64(&mut bytes, Some(10.1));
    for value in [0.3, 0.2, 0.1] {
        write_f64(&mut bytes, value);
    }
    write_option_f64(&mut bytes, Some(10.0));
    write_option_f64(&mut bytes, Some(9.8));
    write_option_f64(&mut bytes, None);
    write_option_f64(&mut bytes, Some(1.2));
    for value in [true, false, true, false, true, false] {
        write_bool(&mut bytes, value);
    }
    bytes
}

fn write_string(out: &mut Vec<u8>, value: &str) {
    out.extend_from_slice(&(value.len() as u16).to_le_bytes());
    out.extend_from_slice(value.as_bytes());
}

fn write_bool(out: &mut Vec<u8>, value: bool) {
    out.push(u8::from(value));
}

fn write_option_f64(out: &mut Vec<u8>, value: Option<f64>) {
    match value {
        Some(value) => {
            write_bool(out, true);
            write_f64(out, value);
        }
        None => write_bool(out, false),
    }
}

fn write_u64(out: &mut Vec<u8>, value: u64) {
    out.extend_from_slice(&value.to_le_bytes());
}

fn write_i32(out: &mut Vec<u8>, value: i32) {
    out.extend_from_slice(&value.to_le_bytes());
}

fn write_f64(out: &mut Vec<u8>, value: f64) {
    out.extend_from_slice(&value.to_le_bytes());
}
