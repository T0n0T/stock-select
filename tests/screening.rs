use chrono::{Duration, NaiveDate};
use stock_select::cache::{
    load_prepared_cache, load_prepared_cache_for_mode, prepared_cache_data_path,
    prepared_cache_meta_path, prepared_cache_paths, write_prepared_cache,
};
use stock_select::intraday::{RawRtKRow, StaticRtKProvider};
use stock_select::model::{MarketRow, Method, PreparedRow};
use stock_select::screening::{
    PoolSource, ScreenRequest, run_intraday_screen_with_loaders, run_intraday_screen_with_provider,
    run_screen_with_loader,
};

#[test]
fn screen_loads_market_rows_writes_prepared_cache_and_candidate_file() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 3).unwrap();
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        dsn: "postgresql://fixture".to_string(),
        recompute: false,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    let output_path = run_screen_with_loader(request, |dsn, start_date, end_date| {
        assert_eq!(dsn, "postgresql://fixture");
        assert_eq!(start_date, NaiveDate::from_ymd_opt(2025, 5, 2).unwrap());
        assert_eq!(end_date, pick_date);
        Ok(vec![
            market_row(1, 10.0, 100.0),
            market_row(2, 10.1, 90.0),
            market_row(3, 10.6, 120.0),
        ])
    })
    .unwrap();

    assert_eq!(
        output_path,
        temp.path().join("candidates/2026-05-03.b2.json")
    );
    assert!(prepared_cache_data_path(temp.path(), pick_date).exists());
    assert!(prepared_cache_meta_path(temp.path(), pick_date).exists());
    let prepared = load_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        NaiveDate::from_ymd_opt(2025, 5, 2).unwrap(),
        pick_date,
    )
    .unwrap()
    .unwrap();
    assert_eq!(prepared.len(), 3);

    let payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    assert_eq!(payload["method"], "b2");
    assert_eq!(payload["pool_source"], "turnover-top");
    assert_eq!(payload["count"], 0);
    assert_eq!(payload["candidates"].as_array().unwrap().len(), 0);
}

#[test]
fn screen_prepare_matches_old_indicator_basics() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 2).unwrap();
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        dsn: "postgresql://fixture".to_string(),
        recompute: false,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_dsn, _start_date, _end_date| {
        Ok(vec![
            market_row_with_open_delta(1, 10.0, 10.0, 0.5),
            market_row_with_open_delta(2, 11.0, 20.0, 0.5),
        ])
    })
    .unwrap();
    let prepared = load_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        NaiveDate::from_ymd_opt(2025, 5, 1).unwrap(),
        pick_date,
    )
    .unwrap()
    .unwrap();

    assert_eq!(prepared[0].turnover_n, 97.5);
    assert_eq!(prepared[1].turnover_n, 97.5 + 215.0);
    assert_eq!(prepared[0].turnover_rate, Some(0.1));
    assert_eq!(prepared[1].turnover_rate, Some(0.2));
    assert_eq!(prepared[0].j, 50.0);
    assert!(prepared[1].dif > prepared[0].dif);
}

#[test]
fn screen_custom_pool_intersects_prepared_universe_before_strategy() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    write_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
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
    std::fs::write(&pool_file, "000002 junk-000003 000002.SZ").unwrap();

    let output_path = run_screen_with_loader(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::Custom,
            pool_file: Some(pool_file.clone()),
            export_factors: false,
            environment_state: None,
        },
        |_dsn, _start_date, _end_date| panic!("custom pool test should reuse prepared cache"),
    )
    .unwrap();

    let payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    assert_eq!(payload["pool_source"], "custom");
    assert_eq!(payload["pool_file"], pool_file.to_string_lossy().as_ref());
    assert_eq!(payload["candidates"].as_array().unwrap().len(), 1);
    assert_eq!(payload["candidates"][0]["code"], "000002.SZ");
}

#[test]
fn screen_b2_does_not_repeat_signal_in_same_j_turn_up_cycle() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 5).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 4).unwrap();
    write_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &[
            prepared_row("000001.SZ", 1, 10.0, 1000.0, 30.0),
            prepared_row("000001.SZ", 2, 10.1, 1000.0, 32.0),
            prepared_row("000001.SZ", 3, 10.5, 1300.0, 35.0),
            prepared_row("000001.SZ", 4, 10.6, 1100.0, 36.0),
            prepared_row("000001.SZ", 5, 11.0, 1400.0, 38.0),
        ],
    )
    .unwrap();

    let output_path = run_screen_with_loader(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_dsn, _start_date, _end_date| panic!("b2 repeat test should reuse prepared cache"),
    )
    .unwrap();

    let payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    assert_eq!(payload["count"], 0);
    assert_eq!(payload["stats"]["selected_b2"], 0);
}

#[test]
fn screen_b2_requires_close_above_long_term_reference_after_new_stock_window() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(114);
    let start_date = pick_date - Duration::days(366);
    let mut rows = Vec::new();
    for offset in 0..112 {
        rows.push(prepared_row_at_date(
            "000001.SZ",
            first_date + Duration::days(offset),
            20.0,
            1000.0,
            30.0,
        ));
    }
    rows.push(prepared_row_at_date(
        "000001.SZ",
        first_date + Duration::days(112),
        9.4,
        1000.0,
        30.0,
    ));
    rows.push(prepared_row_at_date(
        "000001.SZ",
        first_date + Duration::days(113),
        9.5,
        1000.0,
        35.0,
    ));
    rows.push(prepared_row_at_date(
        "000001.SZ",
        pick_date,
        10.0,
        1300.0,
        45.0,
    ));
    write_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();

    let output_path = run_screen_with_loader(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_dsn, _start_date, _end_date| panic!("above_lt test should reuse prepared cache"),
    )
    .unwrap();

    let payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    assert_eq!(payload["count"], 0);
    assert_eq!(payload["stats"]["selected_b2"], 0);
}

#[test]
fn screen_b2_golden_fixture_selects_mature_trend_start() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(114);
    let start_date = pick_date - Duration::days(366);
    let mut rows = Vec::new();
    for offset in 0..112 {
        rows.push(prepared_row_at_date(
            "000001.SZ",
            first_date + Duration::days(offset),
            10.0 + offset as f64 * 0.03,
            1000.0,
            30.0,
        ));
    }
    rows.push(prepared_row_at_date(
        "000001.SZ",
        first_date + Duration::days(112),
        13.36,
        1000.0,
        30.0,
    ));
    rows.push(prepared_row_at_date(
        "000001.SZ",
        first_date + Duration::days(113),
        13.46,
        1000.0,
        35.0,
    ));
    rows.push(prepared_row_at_date(
        "000001.SZ",
        pick_date,
        14.00,
        1300.0,
        45.0,
    ));
    write_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();

    let output_path = run_screen_with_loader(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_dsn, _start_date, _end_date| panic!("golden fixture should reuse prepared cache"),
    )
    .unwrap();

    let payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    assert_eq!(payload["count"], 1);
    assert_eq!(payload["candidates"][0]["code"], "000001.SZ");
    assert_eq!(payload["candidates"][0]["signal"], "B2");
    assert_eq!(payload["candidates"][0]["close"], 14.0);
    assert_eq!(payload["stats"]["total_symbols"], 1);
    assert_eq!(payload["stats"]["eligible"], 1);
    assert_eq!(payload["stats"]["selected"], 1);
    assert_eq!(payload["stats"]["selected_b2"], 1);
    assert_eq!(payload["stats"]["fail_no_signal"], 0);
}

#[test]
fn screen_can_export_runtime_factor_artifact_before_selection() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(114);
    let start_date = pick_date - Duration::days(366);
    let mut rows = Vec::new();
    for offset in 0..112 {
        rows.push(prepared_row_at_date(
            "000001.SZ",
            first_date + Duration::days(offset),
            10.0 + offset as f64 * 0.03,
            1000.0,
            30.0,
        ));
    }
    rows.push(prepared_row_at_date(
        "000001.SZ",
        first_date + Duration::days(112),
        13.36,
        1000.0,
        30.0,
    ));
    rows.push(prepared_row_at_date(
        "000001.SZ",
        first_date + Duration::days(113),
        13.46,
        1000.0,
        35.0,
    ));
    rows.push(prepared_row_at_date(
        "000001.SZ",
        pick_date,
        14.00,
        1300.0,
        45.0,
    ));
    write_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();

    run_screen_with_loader(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: true,
            environment_state: Some("strong".to_string()),
        },
        |_dsn, _start_date, _end_date| panic!("factor export test should reuse prepared cache"),
    )
    .unwrap();

    let factor_dir = temp.path().join("factors/2026-04-25.b2");
    let factors: serde_json::Value =
        serde_json::from_slice(&std::fs::read(factor_dir.join("factors.json")).unwrap()).unwrap();
    let manifest: serde_json::Value =
        serde_json::from_slice(&std::fs::read(factor_dir.join("manifest.json")).unwrap()).unwrap();

    assert_eq!(factors["method"], "b2");
    assert_eq!(factors["artifact_key"], "2026-04-25");
    assert_eq!(factors["rows"].as_array().unwrap().len(), 1);
    assert_eq!(factors["rows"][0]["code"], "000001.SZ");
    assert_eq!(factors["rows"][0]["factors"]["signal"], "B2");
    assert_eq!(factors["rows"][0]["factors"]["env"], "strong");
    assert!(factors["rows"][0]["factors"]["close_to_zxdkx_pct"].is_number());
    assert_eq!(manifest["method"], "b2");
    assert_eq!(manifest["row_count"], 1);
    assert_eq!(manifest["factor_source"], "rust_factor_library");
}

#[test]
fn intraday_screen_writes_intraday_prepared_cache_without_overwriting_eod_cache() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 24).unwrap();
    let start_date = previous_trade_date - Duration::days(366);
    let provider = StaticRtKProvider::new([
        ("*.SH", vec![]),
        (
            "*.SZ",
            vec![RawRtKRow::from_value(serde_json::json!({
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "open": 10.2,
                "high": 10.8,
                "low": 10.1,
                "close": 10.6,
                "vol": 130000.0,
                "amount": 1390000.0,
                "trade_time": "14:59:59"
            }))],
        ),
        ("*.BJ", vec![]),
    ]);

    let output_path = run_intraday_screen_with_provider(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        &provider,
        "15:00:00",
        |dsn, actual_start, actual_end| {
            assert_eq!(dsn, "postgresql://fixture");
            assert_eq!(actual_start, start_date);
            assert_eq!(actual_end, previous_trade_date);
            Ok(vec![MarketRow {
                ts_code: "000001.SZ".to_string(),
                trade_date: previous_trade_date,
                open: 10.0,
                high: 10.3,
                low: 9.9,
                close: 10.1,
                vol: 1000.0,
                turnover_rate: Some(1.0),
            }])
        },
    )
    .unwrap();

    assert_eq!(
        output_path,
        temp.path().join("candidates/2026-05-25.intraday.b2.json")
    );
    assert!(!prepared_cache_data_path(temp.path(), pick_date).exists());
    assert!(!prepared_cache_meta_path(temp.path(), pick_date).exists());
    assert!(
        prepared_cache_paths(temp.path(), pick_date, true)
            .data_path
            .exists()
    );
    assert!(
        prepared_cache_paths(temp.path(), pick_date, true)
            .meta_path
            .exists()
    );
    let prepared = load_prepared_cache_for_mode(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
    )
    .unwrap()
    .unwrap();
    assert_eq!(prepared.last().unwrap().trade_date, pick_date);
    assert_eq!(prepared.last().unwrap().close, 10.6);
}

#[test]
fn intraday_screen_uses_previous_trade_date_loader_for_history_window() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 22).unwrap();
    let start_date = previous_trade_date - Duration::days(366);
    let provider = StaticRtKProvider::new([
        ("*.SH", vec![]),
        (
            "*.SZ",
            vec![RawRtKRow::from_value(serde_json::json!({
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "open": 10.2,
                "high": 10.8,
                "low": 10.1,
                "close": 10.6,
                "vol": 130000.0,
                "amount": 1390000.0
            }))],
        ),
        ("*.BJ", vec![]),
    ]);

    run_intraday_screen_with_loaders(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        &provider,
        "15:00:00",
        |dsn, trade_date| {
            assert_eq!(dsn, "postgresql://fixture");
            assert_eq!(trade_date, pick_date);
            Ok(previous_trade_date)
        },
        |dsn, actual_start, actual_end| {
            assert_eq!(dsn, "postgresql://fixture");
            assert_eq!(actual_start, start_date);
            assert_eq!(actual_end, previous_trade_date);
            Ok(vec![MarketRow {
                ts_code: "000001.SZ".to_string(),
                trade_date: previous_trade_date,
                open: 10.0,
                high: 10.3,
                low: 9.9,
                close: 10.1,
                vol: 1000.0,
                turnover_rate: Some(1.0),
            }])
        },
    )
    .unwrap();
}

fn market_row(day: u32, close: f64, vol: f64) -> MarketRow {
    market_row_with_open_delta(day, close, vol, 0.8)
}

fn market_row_with_open_delta(day: u32, close: f64, vol: f64, open_delta: f64) -> MarketRow {
    MarketRow {
        ts_code: "000001.SZ".to_string(),
        trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
        open: close - open_delta,
        high: close,
        low: close - 1.0,
        close,
        vol,
        turnover_rate: Some(vol / 100.0),
    }
}

fn prepared_row(code: &str, day: u32, close: f64, volume: f64, j: f64) -> PreparedRow {
    prepared_row_at_date(
        code,
        NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
        close,
        volume,
        j,
    )
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
    }
}
