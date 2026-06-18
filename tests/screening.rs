use chrono::{Duration, NaiveDate};
use stock_select::cache::{
    load_prepared_cache, load_prepared_cache_for_mode, prepared_cache_data_path,
    prepared_cache_meta_path, prepared_cache_paths, write_prepared_cache,
    write_prepared_cache_for_mode,
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
fn screen_prepare_front_adjusts_ohlc_indicators_and_preserves_raw_turnover_basis() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 2).unwrap();
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        dsn: "postgresql://fixture".to_string(),
        recompute: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_dsn, _start_date, _end_date| {
        let mut first = market_row_with_open_delta(1, 10.0, 10.0, 0.5);
        first.adj_factor = Some(0.5);
        let mut latest = market_row_with_open_delta(2, 6.0, 20.0, 0.5);
        latest.adj_factor = Some(1.0);
        Ok(vec![first, latest])
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

    assert_eq!(prepared[0].open, 4.75);
    assert_eq!(prepared[0].high, 5.0);
    assert_eq!(prepared[0].low, 4.5);
    assert_eq!(prepared[0].close, 5.0);
    assert_eq!(prepared[1].close, 6.0);
    assert!((prepared[1].chg_d.unwrap() - 20.0).abs() < 1e-9);
    assert_eq!(prepared[0].turnover_n, 97.5);
    assert_eq!(prepared[1].turnover_n, 97.5 + 115.0);
    assert!(!prepared[1].db_factors.contains_key("adj_factor"));
}

#[test]
fn screen_prepare_front_adjusts_local_qfq_factor_fallbacks() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 5, 1).unwrap();
    let pick_date = first_date + Duration::days(12);
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        dsn: "postgresql://fixture".to_string(),
        recompute: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_dsn, _start_date, _end_date| {
        Ok((0..13)
            .map(|offset| {
                let mut row = market_row_at_date(
                    first_date + Duration::days(offset),
                    if offset < 12 { 10.0 } else { 6.0 },
                    100.0,
                );
                row.adj_factor = Some(if offset < 12 { 0.5 } else { 1.0 });
                row
            })
            .collect())
    })
    .unwrap();
    let prepared = load_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        pick_date - Duration::days(366),
        pick_date,
    )
    .unwrap()
    .unwrap();
    let latest = prepared.last().unwrap();

    assert!((latest.db_factors["roc_qfq"] - 20.0).abs() < 1e-9);
    assert!((latest.db_factors["mtm_qfq"] - 1.0).abs() < 1e-9);
}

#[test]
fn screen_prepare_uses_shared_nan_aware_rolling_indicators() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(24);
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        dsn: "postgresql://fixture".to_string(),
        recompute: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_dsn, _start_date, _end_date| {
        Ok((0..25)
            .map(|offset| {
                let close = if offset == 7 {
                    f64::NAN
                } else {
                    10.0 + offset as f64 * 0.1
                };
                market_row_at_date(first_date + Duration::days(offset), close, 100.0)
            })
            .collect())
    })
    .unwrap();

    let prepared = load_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        pick_date - Duration::days(366),
        pick_date,
    )
    .unwrap()
    .unwrap();

    assert_eq!(prepared.len(), 25);
    assert_eq!(prepared.last().unwrap().ma25, None);
}

#[test]
fn screen_prepare_fills_local_intraday_compatible_db_factors_without_overwriting_existing_values() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(24);
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        dsn: "postgresql://fixture".to_string(),
        recompute: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_dsn, _start_date, _end_date| {
        Ok((0..25)
            .map(|offset| {
                let close = 10.0 + offset as f64;
                let mut row = MarketRow {
                    ts_code: "000001.SZ".to_string(),
                    trade_date: first_date + Duration::days(offset),
                    open: close - 0.5,
                    high: close + 1.0,
                    low: close - 1.0,
                    close,
                    vol: 1000.0 + offset as f64,
                    turnover_rate: Some(1.0 + offset as f64 / 10.0),
                    adj_factor: None,
                    db_factors: Default::default(),
                };
                if offset == 24 {
                    row.db_factors.insert("psy_qfq".to_string(), 88.8);
                }
                row
            })
            .collect())
    })
    .unwrap();

    let prepared = load_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        pick_date - Duration::days(366),
        pick_date,
    )
    .unwrap()
    .unwrap();
    let latest = prepared.last().unwrap();

    assert!((latest.db_factors["boll_width_pct"] - 94.1433681197616).abs() < 1e-9);
    assert!((latest.db_factors["bias1_qfq"] - 7.936507936507936).abs() < 1e-9);
    assert_eq!(latest.db_factors["roc_qfq"], 54.54545454545454);
    assert_eq!(latest.db_factors["mtm_qfq"], 12.0);
    assert_eq!(latest.db_factors["psy_qfq"], 88.8);
    assert_eq!(latest.db_factors["wr_qfq"], 9.090909090909092);
    assert!((latest.db_factors["dist_to_up_limit_pct"] - 6.764705882352932).abs() < 1e-9);
    assert!((latest.db_factors["dist_to_down_limit_pct"] - 12.647058823529415).abs() < 1e-9);
    assert!(!latest.db_factors.contains_key("turnover_rate_f"));
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
fn screen_missing_pick_date_rows_reports_latest_cached_date() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 8).unwrap();
    let start_date = pick_date - Duration::days(366);
    write_prepared_cache_for_mode(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
        &[prepared_row_at_date(
            "000001.SZ",
            pick_date,
            10.5,
            1000.0,
            45.0,
        )],
    )
    .unwrap();

    let err = run_screen_with_loader(
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
        |_dsn, _start_date, _end_date| {
            Ok(vec![market_row_at_date(
                NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
                10.0,
                1000.0,
            )])
        },
    )
    .unwrap_err();

    let message = err.to_string();
    assert!(message.contains("No prepared rows found for pick_date 2026-06-08"));
    assert!(message.contains("latest cached trade_date is 2026-06-05"));
    assert!(message.contains("--intraday"));
    assert!(!prepared_cache_data_path(temp.path(), pick_date).exists());
}

#[test]
fn screen_b3_writes_b3_candidate_artifact() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 4).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 3).unwrap();
    write_prepared_cache(
        temp.path(),
        Method::B3,
        pick_date,
        start_date,
        pick_date,
        &[
            prepared_row("000001.SZ", 1, 10.0, 1000.0, 30.0),
            prepared_row("000001.SZ", 2, 10.1, 900.0, 35.0),
            prepared_row("000001.SZ", 3, 10.6, 1200.0, 45.0),
            prepared_row("000001.SZ", 4, 10.7, 600.0, 46.0),
        ],
    )
    .unwrap();

    let output_path = run_screen_with_loader(
        ScreenRequest {
            method: Method::B3,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_dsn, _start_date, _end_date| panic!("b3 screen test should reuse prepared cache"),
    )
    .unwrap();

    assert_eq!(
        output_path,
        temp.path().join("candidates/2026-05-04.b3.json")
    );
    let payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    assert_eq!(payload["method"], "b3");
    assert_eq!(payload["count"], 1);
    assert_eq!(payload["candidates"][0]["code"], "000001.SZ");
    assert_eq!(payload["candidates"][0]["signal"], "B3+");
    assert_eq!(payload["stats"]["selected_b2"], 0);
    assert_eq!(payload["stats"]["selected_b3"], 0);
    assert_eq!(payload["stats"]["selected_b3_plus"], 1);
}

#[test]
fn screen_lsh_writes_lsh_candidate_artifact() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(429);
    let start_date = pick_date - Duration::days(366);
    let mut rows = lsh_prepared_rows("000001.SZ", first_date, 430, true);
    let latest = rows.last_mut().unwrap();
    latest.ma60 = latest.ma25.map(|ma25| ma25 + 1.0);
    write_prepared_cache(
        temp.path(),
        Method::Lsh,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();

    let output_path = run_screen_with_loader(
        ScreenRequest {
            method: Method::Lsh,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_dsn, _start_date, _end_date| panic!("lsh screen test should reuse prepared cache"),
    )
    .unwrap();

    assert_eq!(
        output_path,
        temp.path().join("candidates/2026-03-06.lsh.json")
    );
    let payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    assert_eq!(payload["method"], "lsh");
    assert_eq!(payload["count"], 1);
    assert_eq!(payload["candidates"][0]["code"], "000001.SZ");
    assert_eq!(payload["candidates"][0]["signal"], "LSH");
    assert_eq!(payload["stats"]["selected_lsh"], 1);
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
fn screen_export_factors_derives_environment_from_prepared_cross_section() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 4).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 3).unwrap();
    let mut rows = vec![
        prepared_row("000001.SZ", 1, 10.0, 1000.0, 30.0),
        prepared_row("000001.SZ", 2, 10.1, 900.0, 35.0),
        prepared_row("000001.SZ", 3, 10.6, 1200.0, 45.0),
        prepared_row("000001.SZ", 4, 10.7, 600.0, 46.0),
        prepared_row("000002.SZ", 3, 20.0, 1000.0, 35.0),
        prepared_row("000002.SZ", 4, 21.0, 1000.0, 40.0),
        prepared_row("000003.SZ", 3, 30.0, 1000.0, 35.0),
        prepared_row("000003.SZ", 4, 31.5, 1000.0, 40.0),
    ];
    for row in rows.iter_mut().filter(|row| row.trade_date == pick_date) {
        row.chg_d = Some(5.0);
    }
    write_prepared_cache(
        temp.path(),
        Method::B3,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();

    run_screen_with_loader(
        ScreenRequest {
            method: Method::B3,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            dsn: "postgresql://fixture".to_string(),
            recompute: false,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: true,
            environment_state: None,
        },
        |_dsn, _start_date, _end_date| {
            panic!("environment export test should reuse prepared cache")
        },
    )
    .unwrap();

    let factors: serde_json::Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("factors/2026-05-04.b3/factors.json")).unwrap(),
    )
    .unwrap();

    assert!(!temp.path().join("environment/history.jsonl").exists());
    assert!(!factors["rows"].as_array().unwrap().is_empty());
    assert_eq!(factors["rows"][0]["factors"]["env"], "strong");
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
                adj_factor: None,
                db_factors: Default::default(),
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
fn intraday_screen_export_factors_runs_through_local_factor_fill() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 5, 1).unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 24).unwrap();
    let start_date = previous_trade_date - Duration::days(366);
    let pool_file = temp.path().join("pool.txt");
    std::fs::write(&pool_file, "000001.SZ").unwrap();
    let provider = StaticRtKProvider::new([
        ("*.SH", vec![]),
        (
            "*.SZ",
            vec![RawRtKRow::from_value(serde_json::json!({
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "open": 27.4,
                "high": 28.45,
                "low": 27.2,
                "close": 28.392,
                "vol": 200000.0,
                "amount": 5678400.0,
                "trade_time": "14:59:59"
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
            pool_source: PoolSource::Custom,
            pool_file: Some(pool_file),
            export_factors: true,
            environment_state: Some("neutral".to_string()),
        },
        &provider,
        "15:00:00",
        |_dsn, _trade_date| Ok(previous_trade_date),
        |dsn, actual_start, actual_end| {
            assert_eq!(dsn, "postgresql://fixture");
            assert_eq!(actual_start, start_date);
            assert_eq!(actual_end, previous_trade_date);
            Ok((0..24)
                .map(|offset| {
                    let close = if offset < 23 {
                        30.0 - offset as f64 * 0.1
                    } else {
                        27.3
                    };
                    MarketRow {
                        ts_code: "000001.SZ".to_string(),
                        trade_date: first_date + Duration::days(offset),
                        open: close + 0.1,
                        high: close + 0.2,
                        low: close - 0.2,
                        close,
                        vol: 1000.0 + offset as f64,
                        turnover_rate: Some(1.0),
                        adj_factor: None,
                        db_factors: Default::default(),
                    }
                })
                .collect())
        },
    )
    .unwrap();

    let factor_path = temp
        .path()
        .join("factors/2026-05-25.intraday.b2/factors.json");
    let factors: serde_json::Value =
        serde_json::from_slice(&std::fs::read(factor_path).unwrap()).unwrap();
    assert_eq!(factors["rows"].as_array().unwrap().len(), 1);
    let row_factors = &factors["rows"][0]["factors"];
    assert!(row_factors["boll_width_pct"].is_number());
    assert!(row_factors["bias1_qfq"].is_number());
    assert!(row_factors["roc_qfq"].is_number());
    assert!(row_factors["mtm_qfq"].is_number());
    assert!(row_factors["psy_qfq"].is_number());
    assert!(row_factors["wr_qfq"].is_number());
    assert!(row_factors["dist_to_up_limit_pct"].is_number());
    assert!(row_factors["dist_to_down_limit_pct"].is_number());
    assert!(row_factors["chip_vwap"].is_number());
    assert!(row_factors["turnover_rate_f"].is_null());
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
                adj_factor: None,
                db_factors: Default::default(),
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
        adj_factor: None,
        db_factors: Default::default(),
    }
}

fn market_row_at_date(trade_date: NaiveDate, close: f64, vol: f64) -> MarketRow {
    MarketRow {
        ts_code: "000001.SZ".to_string(),
        trade_date,
        open: close - 0.8,
        high: close,
        low: close - 1.0,
        close,
        vol,
        turnover_rate: Some(vol / 100.0),
        adj_factor: None,
        db_factors: Default::default(),
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
        db_factors: Default::default(),
    }
}

fn lsh_prepared_rows(
    code: &str,
    first_date: NaiveDate,
    len: usize,
    constructive_weekly_monthly: bool,
) -> Vec<PreparedRow> {
    (0..len)
        .map(|offset| {
            let trade_date = first_date + Duration::days(offset as i64);
            let base_close = if constructive_weekly_monthly {
                10.0 + offset as f64 * 0.03 + (offset as f64 * offset as f64) * 0.0001
            } else {
                50.0 - offset as f64 * 0.03
            };
            let is_latest = offset + 1 == len;
            let close = if is_latest {
                base_close + 1.0
            } else {
                base_close
            };
            let ma25 = if is_latest { close - 0.7 } else { close - 0.5 };
            let is_previous = offset + 2 == len;
            let is_two_before = offset + 3 == len;
            PreparedRow {
                ts_code: code.to_string(),
                trade_date,
                open: if is_latest { close - 0.5 } else { close - 0.1 },
                high: close + 0.2,
                low: if is_previous {
                    ma25 - 0.1
                } else if is_latest {
                    ma25 + 0.1
                } else {
                    close - 0.2
                },
                close,
                volume: if is_two_before {
                    1200.0
                } else if is_previous {
                    900.0
                } else {
                    1000.0
                },
                turnover_n: 1000.0 * close,
                turnover_rate: Some(1.0),
                k: 50.0,
                d: 40.0,
                j: 45.0,
                zxdq: Some(close),
                zxdkx: Some(close - 0.5),
                dif: 0.3,
                dea: 0.2,
                macd_hist: 0.1,
                ma25: Some(ma25),
                ma60: Some(close - 1.0),
                ma144: Some(close - 1.5),
                chg_d: None,
                weekly_ma_bull: true,
                max_vol_not_bearish: true,
                v_shrink: false,
                safe_mode: true,
                lt_filter: true,
                yellow_b1: false,
                db_factors: Default::default(),
            }
        })
        .collect()
}
