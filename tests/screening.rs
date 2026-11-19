use chrono::{Datelike, Duration, NaiveDate};
use stock_select::cache::{
    load_prepared_cache, load_prepared_cache_for_mode, load_prepared_dataset_for_mode,
    prepared_cache_data_path, prepared_cache_meta_path, prepared_cache_paths, write_prepared_cache,
    write_prepared_cache_for_mode,
};
use stock_select::intraday::{MacdPeriodState, RawRtKRow, StaticRtKProvider};
use stock_select::model::{DbDataGap, MarketDataset, MarketRow, Method, PreparedRow};
use stock_select::screening::{
    load_db_native_prepared_window_with_loader,
    PoolSource, ScreenRequest, prepared_cache_start_date,
    run_db_native_intraday_screen_with_loaders, run_db_native_screen_with_dataset_loader,
    run_db_native_screen_with_loader, run_intraday_screen_with_loaders,
    run_intraday_screen_with_provider, run_screen_with_loader, screen_window,
};

#[test]
fn screen_window_uses_one_year_prepared_history() {
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 23).unwrap();

    assert_eq!(
        screen_window(pick_date),
        (NaiveDate::from_ymd_opt(2025, 6, 23).unwrap(), pick_date)
    );
    assert_eq!(
        prepared_cache_start_date(pick_date),
        NaiveDate::from_ymd_opt(2025, 6, 23).unwrap()
    );
}

#[test]
fn screen_skips_prepared_cache_write_when_disabled() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 3).unwrap();
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: false,
        write_prepared_cache: false,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    let output_path = run_screen_with_loader(request, |_duckdb_path, _start, _end| {
        Ok(vec![
            market_row(1, 10.0, 100.0),
            market_row(2, 10.1, 90.0),
            market_row(3, 10.6, 120.0),
        ])
    })
    .unwrap();

    assert!(output_path.exists());
    assert!(!prepared_cache_data_path(temp.path(), pick_date).exists());
}

#[test]
fn screen_loads_market_rows_writes_prepared_cache_and_candidate_file() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 3).unwrap();
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: false,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    let output_path = run_screen_with_loader(request, |duckdb_path, start_date, end_date| {
        assert_eq!(duckdb_path, "fixture.duckdb");
        assert_eq!(start_date, prepared_cache_start_date(pick_date));
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
        prepared_cache_start_date(pick_date),
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
fn db_native_screen_writes_db_native_prepared_cache_metadata() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let requested_window_start = prepared_cache_start_date(pick_date);
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_db_native_screen_with_loader(request, |_duckdb_path, start_date, end_date| {
        assert_eq!(start_date, requested_window_start);
        assert_eq!(end_date, pick_date);
        Ok((0..365)
            .map(|offset| {
                market_row_at_date(
                    requested_window_start + Duration::days(offset),
                    10.0 + offset as f64 * 0.01,
                    100.0,
                )
            })
            .chain(std::iter::once(market_row_at_date(pick_date, 12.52, 100.0)))
            .collect())
    })
    .unwrap();

    let metadata: serde_json::Value = serde_json::from_slice(
        &std::fs::read(prepared_cache_meta_path(temp.path(), pick_date)).unwrap(),
    )
    .unwrap();

    assert_eq!(metadata["source_table"], "stock-cache-db-native");
    assert_eq!(metadata["source"], "stock-cache-db-native");
    assert_eq!(metadata["start_date"], requested_window_start.to_string());
    assert_eq!(metadata["end_date"], pick_date.to_string());
    assert_eq!(metadata["window_trading_days"], 366);
    assert_eq!(
        metadata["window_start_date"],
        requested_window_start.to_string()
    );
    assert_eq!(metadata["window_end_date"], pick_date.to_string());
    assert_eq!(metadata["calc_versions"]["macd"], "macd_qfq_12_26_9_v1");
}

#[test]
fn db_native_screen_propagates_table_gaps_to_cache_and_factor_manifest_only() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let requested_window_start = prepared_cache_start_date(pick_date);
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: true,
        environment_state: Some("neutral".to_string()),
    };

    let output_path =
        run_db_native_screen_with_dataset_loader(request, |_duckdb_path, start_date, end_date| {
            assert_eq!(start_date, requested_window_start);
            assert_eq!(end_date, pick_date);
            Ok(MarketDataset {
                rows: (0..365)
                    .map(|offset| {
                        market_row_at_date(
                            requested_window_start + Duration::days(offset),
                            10.0 + offset as f64 * 0.01,
                            100.0,
                        )
                    })
                    .chain(std::iter::once(market_row_at_date(pick_date, 12.52, 100.0)))
                    .collect(),
                db_data_gaps: std::collections::BTreeMap::from([(
                    "index_moneyflow_cnt_ths".to_string(),
                    DbDataGap::missing_rows(1, 0),
                )]),
            })
        })
        .unwrap();

    let candidate_payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    assert!(candidate_payload.get("db_data_gaps").is_none());

    let cache_metadata: serde_json::Value = serde_json::from_slice(
        &std::fs::read(prepared_cache_meta_path(temp.path(), pick_date)).unwrap(),
    )
    .unwrap();
    assert_eq!(
        cache_metadata["db_data_gaps"]["index_moneyflow_cnt_ths"],
        serde_json::json!({
            "reason": "missing_rows",
            "expected_rows": 1,
            "actual_rows": 0
        })
    );

    let factor_manifest: serde_json::Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("factors/2026-06-15.b2/manifest.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(
        factor_manifest["db_data_gaps"],
        cache_metadata["db_data_gaps"]
    );
}

#[test]
fn db_native_screen_rejects_joined_window_missing_requested_start_date() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let requested_start = prepared_cache_start_date(pick_date);
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    let err = run_db_native_screen_with_loader(request, |_duckdb_path, start_date, end_date| {
        assert_eq!(start_date, requested_start);
        assert_eq!(end_date, pick_date);
        Ok((1..750)
            .map(|offset| market_row_at_date(requested_start + Duration::days(offset), 10.0, 100.0))
            .chain(std::iter::once(market_row_at_date(pick_date, 12.51, 100.0)))
            .collect())
    })
    .expect_err("DB-native joined window missing requested start date should fail");

    assert!(err.to_string().contains("requested prepared window"));
    assert!(!prepared_cache_meta_path(temp.path(), pick_date).exists());
}

#[test]
fn db_native_screen_allows_window_start_on_next_trading_date() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 29).unwrap();
    let requested_start = prepared_cache_start_date(pick_date);
    let actual_start = NaiveDate::from_ymd_opt(2025, 6, 30).unwrap();
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_db_native_screen_with_loader(request, |_duckdb_path, start_date, end_date| {
        assert_eq!(start_date, requested_start);
        assert_eq!(end_date, pick_date);
        Ok((0..365)
            .map(|offset| market_row_at_date(actual_start + Duration::days(offset), 10.0, 100.0))
            .chain(std::iter::once(market_row_at_date(pick_date, 12.51, 100.0)))
            .collect())
    })
    .unwrap();

    let metadata: serde_json::Value = serde_json::from_slice(
        &std::fs::read(prepared_cache_meta_path(temp.path(), pick_date)).unwrap(),
    )
    .unwrap();
    assert_eq!(metadata["start_date"], actual_start.to_string());
    assert_eq!(metadata["window_start_date"], actual_start.to_string());
    assert_eq!(metadata["window_end_date"], pick_date.to_string());
}

#[test]
fn db_native_screen_allows_window_start_after_long_holiday_when_trading_days_are_sufficient() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 1, 28).unwrap();
    let requested_start = prepared_cache_start_date(pick_date);
    let actual_start = NaiveDate::from_ymd_opt(2025, 2, 5).unwrap();
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_db_native_screen_with_loader(request, |_duckdb_path, start_date, end_date| {
        assert_eq!(start_date, requested_start);
        assert_eq!(end_date, pick_date);
        Ok((0..235)
            .map(|offset| market_row_at_date(actual_start + Duration::days(offset), 10.0, 100.0))
            .chain(std::iter::once(market_row_at_date(pick_date, 12.51, 100.0)))
            .collect())
    })
    .unwrap();

    let metadata: serde_json::Value = serde_json::from_slice(
        &std::fs::read(prepared_cache_meta_path(temp.path(), pick_date)).unwrap(),
    )
    .unwrap();
    assert_eq!(metadata["start_date"], actual_start.to_string());
    assert_eq!(metadata["window_start_date"], actual_start.to_string());
    assert_eq!(metadata["window_end_date"], pick_date.to_string());
}

#[test]
fn db_native_screen_rejects_window_with_too_few_trading_days() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 1, 28).unwrap();
    let requested_start = prepared_cache_start_date(pick_date);
    let actual_start = NaiveDate::from_ymd_opt(2025, 2, 5).unwrap();
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    let err = run_db_native_screen_with_loader(request, |_duckdb_path, start_date, end_date| {
        assert_eq!(start_date, requested_start);
        assert_eq!(end_date, pick_date);
        Ok((0..200)
            .map(|offset| market_row_at_date(actual_start + Duration::days(offset), 10.0, 100.0))
            .chain(std::iter::once(market_row_at_date(pick_date, 12.51, 100.0)))
            .collect())
    })
    .expect_err("DB-native joined window with too few trading days should fail");

    assert!(err.to_string().contains("requested prepared window"));
    assert!(!prepared_cache_meta_path(temp.path(), pick_date).exists());
}

#[test]
fn screen_prepare_matches_old_indicator_basics() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 2).unwrap();
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: false,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_duckdb_path, _start_date, _end_date| {
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
        prepared_cache_start_date(pick_date),
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
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_duckdb_path, _start_date, _end_date| {
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
        prepared_cache_start_date(pick_date),
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
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_duckdb_path, _start_date, _end_date| {
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
        prepared_cache_start_date(pick_date),
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
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_duckdb_path, _start_date, _end_date| {
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
        prepared_cache_start_date(pick_date),
        pick_date,
    )
    .unwrap()
    .unwrap();

    assert_eq!(prepared.len(), 25);
    assert_eq!(prepared.last().unwrap().ma25, None);
}

#[test]
fn screen_prepare_aligns_db_qfq_prices_to_the_window_basis() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 1, 30).unwrap();
    let mut source = market_row_at_date(pick_date, 40.04, 100.0);
    source.adj_factor = Some(1.0146);
    source.db_factors.extend([
        ("_source_close_qfq".to_string(), 26.61289),
        ("_czsc_snapshot_available".to_string(), 1.0),
        ("_czsc_recent_peak_high".to_string(), 25.25699),
        ("_czsc_recent_peak_day".to_string(), 20452.0),
        ("_czsc_last_bi_high".to_string(), 25.25699),
        ("_czsc_latest_zs_zg".to_string(), 23.96987),
        ("_czsc_post_peak_first_bear_open".to_string(), 24.99113),
        ("rolling_ma25_qfq".to_string(), 25.0267564),
        ("macd_daily_dif".to_string(), 0.44374441884686533),
        ("macd_weekly_hist".to_string(), 0.25),
        ("macd_monthly_dea".to_string(), -0.5),
        ("macd_daily_dea_pctile".to_string(), 0.7),
        ("mtm_qfq".to_string(), 0.9),
        ("boll_upper_qfq".to_string(), 27.0),
        ("volume_ratio".to_string(), 1.5),
        ("ths_main_macd_daily_hist".to_string(), 0.3),
    ]);
    run_screen_with_loader(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: true,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_, _, _| Ok(vec![source]),
    )
    .unwrap();
    let prepared = load_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        prepared_cache_start_date(pick_date),
        pick_date,
    )
    .unwrap()
    .unwrap();
    let latest = prepared.last().unwrap();
    let multiplier = 40.04 / 26.61289;
    let distance = 100.0 * (latest.close / latest.db_factors["_czsc_recent_peak_high"] - 1.0);

    assert!((distance - 5.368414842782143).abs() < 1e-9);
    assert_eq!(latest.close, 40.04);
    assert!((latest.ma25.unwrap() - 25.0267564 * multiplier).abs() < 1e-9);
    assert!((latest.dif - 0.44374441884686533 * multiplier).abs() < 1e-9);
    for (key, value) in [
        ("_czsc_last_bi_high", 25.25699),
        ("_czsc_latest_zs_zg", 23.96987),
        ("_czsc_post_peak_first_bear_open", 24.99113),
        ("macd_weekly_hist", 0.25),
        ("macd_monthly_dea", -0.5),
        ("mtm_qfq", 0.9),
        ("boll_upper_qfq", 27.0),
    ] {
        assert!(
            (latest.db_factors[key] - value * multiplier).abs() < 1e-9,
            "{key}"
        );
    }
    assert_eq!(latest.db_factors["_czsc_recent_peak_day"], 20452.0);
    assert_eq!(latest.db_factors["macd_daily_dea_pctile"], 0.7);
    assert_eq!(latest.db_factors["volume_ratio"], 1.5);
    assert_eq!(latest.db_factors["ths_main_macd_daily_hist"], 0.3);
    assert!(!latest.db_factors.contains_key("_source_close_qfq"));
}

#[test]
fn screen_prepare_qfq_alignment_is_per_symbol_and_uses_one_basis_across_splits() {
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 29).unwrap();
    let pick_date = first_date + Duration::days(1);
    let specifications = [
        ("000001.SZ", first_date, 10.0, Some(1.0), 5.0, 5.0),
        ("000001.SZ", pick_date, 6.0, Some(2.0), f64::NAN, 5.0),
        ("000002.SZ", first_date, 20.0, Some(2.0), 5.0, 5.0),
        ("000002.SZ", pick_date, 12.0, Some(4.0), 6.0, 5.0),
        ("000003.SZ", first_date, 10.0, None, 2.5, 2.5),
        ("000003.SZ", pick_date, 6.0, None, 3.0, 2.5),
    ];
    let source = specifications
        .into_iter()
        .rev()
        .map(|(code, date, close, adj_factor, qfq_close, peak)| {
            let mut row = market_row_at_date(date, close, 100.0);
            row.ts_code = code.to_string();
            row.open = close;
            row.adj_factor = adj_factor;
            row.db_factors.extend([
                ("_source_close_qfq".to_string(), qfq_close),
                ("_czsc_recent_peak_high".to_string(), peak),
                ("chip_vwap".to_string(), close),
                ("amount".to_string(), close * 100.0),
            ]);
            row
        })
        .collect();
    let prepared = prepare_test_market_rows(source).unwrap();

    for (code, first_close, last_close, peak, turnover) in [
        ("000001.SZ", 5.0, 6.0, 5.0, 1600.0),
        ("000002.SZ", 10.0, 12.0, 10.0, 3200.0),
        ("000003.SZ", 5.0, 6.0, 5.0, 1600.0),
    ] {
        let rows = prepared
            .iter()
            .filter(|row| row.ts_code == code)
            .collect::<Vec<_>>();
        assert_eq!(rows.len(), 2);
        assert_eq!(rows[0].close, first_close, "{code}");
        assert_eq!(rows[1].close, last_close, "{code}");
        assert_eq!(rows[1].turnover_n, turnover, "{code}");
        for row in rows {
            assert_eq!(row.db_factors["_czsc_recent_peak_high"], peak, "{code}");
            assert_eq!(row.db_factors["chip_vwap"], row.close, "{code}");
            assert_eq!(row.volume, 100.0);
            assert!(!row.db_factors.contains_key("_source_close_qfq"));
        }
    }
}

#[test]
fn screen_prepare_rejects_unusable_qfq_reference_instead_of_caching_mixed_prices() {
    let pick_date = NaiveDate::from_ymd_opt(2026, 1, 30).unwrap();
    for reference in [f64::NAN, f64::INFINITY, 0.0, -1.0] {
        let mut row = market_row_at_date(pick_date, 40.04, 100.0);
        row.adj_factor = Some(1.0146);
        row.db_factors.extend([
            ("_source_close_qfq".to_string(), reference),
            ("_czsc_recent_peak_high".to_string(), 25.25699),
        ]);

        let error = prepare_test_market_rows(vec![row]).unwrap_err().to_string();
        assert!(error.contains("price basis"), "{error}");
        assert!(error.contains("000001.SZ"), "{error}");
    }
}

#[test]
fn screen_prepare_prefers_db_native_kdj_macd_and_rolling_values() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 5, 1).unwrap();
    let pick_date = first_date + Duration::days(1);
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_duckdb_path, _start_date, _end_date| {
        Ok((0..2)
            .map(|offset| {
                let mut row = market_row_at_date(
                    first_date + Duration::days(offset),
                    10.0 + offset as f64,
                    100.0,
                );
                row.db_factors
                    .insert("kdj_k_qfq".to_string(), 11.0 + offset as f64);
                row.db_factors
                    .insert("kdj_d_qfq".to_string(), 22.0 + offset as f64);
                row.db_factors
                    .insert("kdj_j_qfq".to_string(), 33.0 + offset as f64);
                row.db_factors
                    .insert("macd_daily_dif".to_string(), 0.7 + offset as f64);
                row.db_factors
                    .insert("macd_daily_dea".to_string(), 0.4 + offset as f64);
                row.db_factors
                    .insert("macd_daily_hist".to_string(), 0.3 + offset as f64);
                row.db_factors
                    .insert("rolling_ma25_qfq".to_string(), 9.5 + offset as f64);
                row.db_factors
                    .insert("rolling_ma144_qfq".to_string(), 8.8 + offset as f64);
                row
            })
            .collect())
    })
    .unwrap();

    let prepared = load_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        prepared_cache_start_date(pick_date),
        pick_date,
    )
    .unwrap()
    .unwrap();
    let latest = prepared.last().unwrap();

    assert_eq!(latest.k, 12.0);
    assert_eq!(latest.d, 23.0);
    assert_eq!(latest.j, 34.0);
    assert_eq!(latest.dif, 1.7);
    assert_eq!(latest.dea, 1.4);
    assert_eq!(latest.macd_hist, 1.3);
    assert_eq!(latest.ma25, Some(10.5));
    assert_eq!(latest.ma144, Some(9.8));
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
        duckdb_path: "fixture.duckdb".to_string(),
        recompute: true,
        write_prepared_cache: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_duckdb_path, _start_date, _end_date| {
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
        prepared_cache_start_date(pick_date),
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
    let start_date = prepared_cache_start_date(pick_date);
    write_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &[
            b2_positive_monthly_rows("000001.SZ", pick_date - Duration::days(89), 90, 10.0),
            b2_positive_monthly_rows("000002.SZ", pick_date - Duration::days(89), 90, 20.0),
        ]
        .concat(),
    )
    .unwrap();
    let pool_file = temp.path().join("pool.txt");
    std::fs::write(&pool_file, "000002 junk-000003 000002.SZ").unwrap();

    let output_path = run_screen_with_loader(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::Custom,
            pool_file: Some(pool_file.clone()),
            export_factors: false,
            environment_state: None,
        },
        |_duckdb_path, _start_date, _end_date| {
            panic!("custom pool test should reuse prepared cache")
        },
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
    let start_date = prepared_cache_start_date(pick_date);
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
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_duckdb_path, _start_date, _end_date| {
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
    assert!(message.contains("DB-native stock-cache daily prepared cache"));
    assert!(!message.contains("daily_market"));
    assert!(!prepared_cache_data_path(temp.path(), pick_date).exists());
}

#[test]
fn screen_scm_and_pbm_partition_candidates_by_recent_ma25_path() {
    let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(429);
    let start_date = prepared_cache_start_date(pick_date);

    for (method_name, signal) in [("scm", "SCM"), ("pbm", "PBM")] {
        let temp = tempfile::tempdir().unwrap();
        let method: Method = method_name.parse().unwrap();
        let mut rows = ma25_prepared_rows("000001.SZ", first_date, 430, true);
        let focus_week = (pick_date - Duration::days(28)).iso_week();
        for row in &mut rows {
            if row.trade_date.iso_week() == focus_week {
                row.volume = 10_000.0;
            }
        }
        let path_start = rows.len() - 20;
        for (offset, row) in rows[path_start..].iter_mut().enumerate() {
            let above_ma25 = if method_name == "scm" {
                offset != 18
            } else {
                matches!(offset, 0..=5 | 19)
            };
            if !above_ma25 {
                let ma25 = row.ma25.unwrap();
                row.close = ma25 - 0.1;
                row.open = row.close - 0.05;
                row.high = row.close + 0.1;
                row.low = row.close - 0.2;
            }
        }
        write_prepared_cache(temp.path(), method, pick_date, start_date, pick_date, &rows).unwrap();

        let output_path = run_screen_with_loader(
            ScreenRequest {
                method,
                pick_date,
                runtime_root: temp.path().to_path_buf(),
                duckdb_path: "fixture.duckdb".to_string(),
                recompute: false,
                write_prepared_cache: true,
                pool_source: PoolSource::TurnoverTop,
                pool_file: None,
                export_factors: false,
                environment_state: None,
            },
            |_duckdb_path, _start_date, _end_date| {
                panic!("{method_name} screen test should reuse prepared cache")
            },
        )
        .unwrap();

        let payload: serde_json::Value =
            serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
        assert_eq!(payload["method"], method_name);
        assert_eq!(payload["count"], 1, "payload={payload}");
        assert_eq!(payload["candidates"][0]["signal"], signal);
    }
}

#[test]
fn scm_requires_pick_date_volume_to_exceed_previous_day() {
    let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(429);

    let mut pick_day_volume_increased = ma25_prepared_rows("000001.SZ", first_date, 430, true);
    add_scm_period_histograms(&mut pick_day_volume_increased);
    let focus_week = (pick_date - Duration::days(28)).iso_week();
    for row in &mut pick_day_volume_increased {
        if row.trade_date.iso_week() == focus_week {
            row.volume = 10_000.0;
        }
    }
    let latest = pick_day_volume_increased.len() - 1;
    pick_day_volume_increased[latest - 2].volume = 1_100.0;
    pick_day_volume_increased[latest - 1].volume = 1_200.0;
    pick_day_volume_increased[latest].volume = 1_300.0;

    let payload = run_screen_with_prepared_rows("scm", pick_date, pick_day_volume_increased);
    assert_eq!(payload["count"], 1, "payload={payload}");

    let mut pick_day_volume_not_increased = ma25_prepared_rows("000001.SZ", first_date, 430, true);
    add_scm_period_histograms(&mut pick_day_volume_not_increased);
    for row in &mut pick_day_volume_not_increased {
        if row.trade_date.iso_week() == focus_week {
            row.volume = 10_000.0;
        }
    }
    let latest = pick_day_volume_not_increased.len() - 1;
    pick_day_volume_not_increased[latest - 2].volume = 1_200.0;
    pick_day_volume_not_increased[latest - 1].volume = 1_000.0;
    pick_day_volume_not_increased[latest].volume = 900.0;

    let payload = run_screen_with_prepared_rows("scm", pick_date, pick_day_volume_not_increased);
    assert_eq!(payload["count"], 0);
    assert_eq!(payload["stats"]["fail_daily_shape"], 1);
}

#[test]
fn scm_requires_increasing_monthly_and_positive_weekly_macd_histograms() {
    let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(429);

    let mut monthly_not_increasing = ma25_prepared_rows("000001.SZ", first_date, 430, true);
    add_scm_period_histograms(&mut monthly_not_increasing);
    let latest_date = monthly_not_increasing.last().unwrap().trade_date;
    let previous_month_key = i64::from((latest_date - Duration::days(31)).year()) * 12
        + i64::from((latest_date - Duration::days(31)).month());
    for row in monthly_not_increasing.iter_mut().filter(|row| {
        row.trade_date.year() == latest_date.year() && row.trade_date.month() == latest_date.month()
    }) {
        row.db_factors.insert(
            "macd_monthly_hist".to_string(),
            previous_month_key as f64 - 1.0,
        );
    }
    let payload = run_screen_with_prepared_rows("scm", pick_date, monthly_not_increasing);
    assert_eq!(payload["count"], 0);
    assert_eq!(payload["stats"]["fail_macd"], 1);

    let mut weekly_not_red = ma25_prepared_rows("000001.SZ", first_date, 430, true);
    add_scm_period_histograms(&mut weekly_not_red);
    let latest_week = weekly_not_red.last().unwrap().trade_date.iso_week();
    for row in weekly_not_red
        .iter_mut()
        .filter(|row| row.trade_date.iso_week() == latest_week)
    {
        row.db_factors.insert("macd_weekly_hist".to_string(), 0.0);
    }
    let payload = run_screen_with_prepared_rows("scm", pick_date, weekly_not_red);
    assert_eq!(payload["count"], 0);
    assert_eq!(payload["stats"]["fail_macd"], 1);
}

#[test]
fn scm_and_pbm_reject_mixed_database_monthly_histograms() {
    let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(429);

    for method in ["scm", "pbm"] {
        for missing_current in [false, true] {
            let mut rows = scm_pbm_macd_fixture(method, first_date);
            let latest = rows.len() - 1;
            let previous_month = rows
                .iter()
                .rposition(|row| row.trade_date.month() != pick_date.month())
                .unwrap();
            if missing_current {
                rows[previous_month]
                    .db_factors
                    .insert("macd_monthly_hist".to_string(), -100_000.0);
            } else {
                rows[latest]
                    .db_factors
                    .insert("macd_monthly_hist".to_string(), 100_000.0);
            }

            let payload = run_screen_with_prepared_rows(method, pick_date, rows);
            assert_eq!(payload["count"], 0, "method={method}, payload={payload}");
            assert_eq!(payload["stats"]["fail_macd"], 1);
        }
    }
}

#[test]
fn scm_and_pbm_compare_database_month_end_with_current_month_asof() {
    let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(429);

    for method in ["scm", "pbm"] {
        let mut rows = scm_pbm_macd_fixture(method, first_date);
        let latest = rows.len() - 1;
        let previous_month = rows
            .iter()
            .rposition(|row| row.trade_date.month() != pick_date.month())
            .unwrap();
        // 萤石网络审计值：本月仍为负柱，但较上一个完整月增加。
        for (index, histogram) in [
            (previous_month - 1, 0.5),
            (previous_month, -0.444_011),
            (latest - 1, -0.1),
            (latest, -0.324_087),
        ] {
            rows[index]
                .db_factors
                .insert("macd_monthly_hist".to_string(), histogram);
        }

        let payload = run_screen_with_prepared_rows(method, pick_date, rows);
        assert_eq!(payload["count"], 1, "method={method}, payload={payload}");
    }
}

fn scm_pbm_macd_fixture(method: &str, first_date: NaiveDate) -> Vec<PreparedRow> {
    let mut rows = ma25_prepared_rows("000001.SZ", first_date, 430, true);
    let path_start = rows.len() - 20;
    for (offset, row) in rows[path_start..].iter_mut().enumerate() {
        if method == "pbm" && !matches!(offset, 0..=5 | 19) {
            row.close = row.ma25.unwrap() - 0.1;
            row.open = row.close - 0.05;
            row.high = row.close + 0.1;
            row.low = row.close - 0.2;
        }
    }
    rows.last_mut()
        .unwrap()
        .db_factors
        .insert("macd_weekly_hist".to_string(), 0.2);
    rows
}

#[test]
fn scm_requires_recent_largest_volume_weekly_candle_to_be_red_and_reclaimed() {
    let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(429);
    let focus_week = (pick_date - Duration::days(28)).iso_week();

    let mut bearish_largest_week = ma25_prepared_rows("000001.SZ", first_date, 430, true);
    add_scm_period_histograms(&mut bearish_largest_week);
    for row in bearish_largest_week
        .iter_mut()
        .filter(|row| row.trade_date.iso_week() == focus_week)
    {
        row.volume = 10_000.0;
        row.open = row.close + 1.0;
    }
    let payload = run_screen_with_prepared_rows("scm", pick_date, bearish_largest_week);
    assert_eq!(payload["count"], 0);
    assert_eq!(payload["stats"]["fail_weekly_volume_candle"], 1);

    let mut unreclaimed_largest_week = ma25_prepared_rows("000001.SZ", first_date, 430, true);
    add_scm_period_histograms(&mut unreclaimed_largest_week);
    let current_price = unreclaimed_largest_week.last().unwrap().close;
    let mut focus_rows = unreclaimed_largest_week
        .iter_mut()
        .filter(|row| row.trade_date.iso_week() == focus_week)
        .collect::<Vec<_>>();
    for row in focus_rows.iter_mut() {
        row.volume = 10_000.0;
    }
    focus_rows.first_mut().unwrap().open = current_price + 1.0;
    focus_rows.last_mut().unwrap().close = current_price + 2.0;
    let payload = run_screen_with_prepared_rows("scm", pick_date, unreclaimed_largest_week);
    assert_eq!(payload["count"], 0);
    assert_eq!(payload["stats"]["fail_weekly_volume_candle"], 1);

    let mut live_price_reclaims_largest_week =
        ma25_prepared_rows("000001.SZ", first_date, 430, true);
    add_scm_period_histograms(&mut live_price_reclaims_largest_week);
    let selection_close = live_price_reclaims_largest_week.last().unwrap().close;
    {
        let mut focus_rows = live_price_reclaims_largest_week
            .iter_mut()
            .filter(|row| row.trade_date.iso_week() == focus_week)
            .collect::<Vec<_>>();
        for row in &mut focus_rows {
            row.volume = 10_000.0;
        }
        focus_rows.first_mut().unwrap().open = selection_close + 1.0;
        focus_rows.last_mut().unwrap().close = selection_close + 2.0;
    }
    live_price_reclaims_largest_week
        .last_mut()
        .unwrap()
        .db_factors
        .insert("intraday_price_live_qfq".to_string(), selection_close + 1.5);
    let payload = run_screen_with_prepared_rows("scm", pick_date, live_price_reclaims_largest_week);
    assert_eq!(payload["count"], 1);
    assert_eq!(payload["candidates"][0]["close"], selection_close + 1.5);
}

fn add_scm_period_histograms(rows: &mut [PreparedRow]) {
    for row in rows {
        let month_key = i64::from(row.trade_date.year()) * 12 + i64::from(row.trade_date.month());
        row.db_factors
            .insert("macd_monthly_hist".to_string(), month_key as f64);
        row.db_factors.insert("macd_weekly_hist".to_string(), 0.2);
    }
}

fn run_screen_with_prepared_rows(
    method_name: &str,
    pick_date: NaiveDate,
    rows: Vec<PreparedRow>,
) -> serde_json::Value {
    let temp = tempfile::tempdir().unwrap();
    let start_date = prepared_cache_start_date(pick_date);
    let method: Method = method_name.parse().unwrap();
    write_prepared_cache(temp.path(), method, pick_date, start_date, pick_date, &rows).unwrap();
    let output_path = run_screen_with_loader(
        ScreenRequest {
            method,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_duckdb_path, _start_date, _end_date| {
            panic!("{method_name} screen test should reuse prepared cache")
        },
    )
    .unwrap();
    serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap()
}

#[test]
fn screen_b2_does_not_repeat_signal_in_same_j_turn_up_cycle() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 5).unwrap();
    let start_date = prepared_cache_start_date(pick_date);
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
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_duckdb_path, _start_date, _end_date| panic!("b2 repeat test should reuse prepared cache"),
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
    let start_date = prepared_cache_start_date(pick_date);
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
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_duckdb_path, _start_date, _end_date| panic!("above_lt test should reuse prepared cache"),
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
    let start_date = prepared_cache_start_date(pick_date);
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
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_duckdb_path, _start_date, _end_date| panic!("golden fixture should reuse prepared cache"),
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
    let start_date = prepared_cache_start_date(pick_date);
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
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: true,
            environment_state: Some("strong".to_string()),
        },
        |_duckdb_path, _start_date, _end_date| {
            panic!("factor export test should reuse prepared cache")
        },
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
    let start_date = prepared_cache_start_date(pick_date);
    let mut rows = vec![
        prepared_row("000001.SZ", 1, 10.0, 1000.0, 30.0),
        prepared_row("000001.SZ", 2, 10.1, 900.0, 35.0),
        prepared_row("000001.SZ", 3, 10.3, 1200.0, 35.0),
        prepared_row("000001.SZ", 4, 10.7, 1300.0, 46.0),
        prepared_row("000002.SZ", 3, 20.0, 1000.0, 35.0),
        prepared_row("000002.SZ", 4, 21.0, 1000.0, 40.0),
        prepared_row("000003.SZ", 3, 30.0, 1000.0, 35.0),
        prepared_row("000003.SZ", 4, 31.5, 1000.0, 40.0),
    ];
    for row in rows.iter_mut().filter(|row| row.trade_date == pick_date) {
        row.chg_d = Some(5.0);
    }
    rows[3]
        .db_factors
        .insert("macd_monthly_dea".to_string(), 0.1);
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
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: true,
            environment_state: None,
        },
        |_duckdb_path, _start_date, _end_date| {
            panic!("environment export test should reuse prepared cache")
        },
    )
    .unwrap();

    let factors: serde_json::Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("factors/2026-05-04.b2/factors.json")).unwrap(),
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
    let start_date = prepared_cache_start_date(previous_trade_date);
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
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        &provider,
        "15:00:00",
        |duckdb_path, actual_start, actual_end| {
            assert_eq!(duckdb_path, "fixture.duckdb");
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
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 24).unwrap();
    let start_date = prepared_cache_start_date(previous_trade_date);
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
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::Custom,
            pool_file: Some(pool_file),
            export_factors: true,
            environment_state: Some("neutral".to_string()),
        },
        &provider,
        "15:00:00",
        |_duckdb_path, _trade_date| Ok(previous_trade_date),
        |duckdb_path, actual_start, actual_end| {
            assert_eq!(duckdb_path, "fixture.duckdb");
            assert_eq!(actual_start, start_date);
            assert_eq!(actual_end, previous_trade_date);
            Ok(intraday_b2_positive_monthly_market_rows(
                NaiveDate::from_ymd_opt(2026, 2, 1).unwrap(),
                previous_trade_date,
            ))
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
fn db_native_intraday_screen_uses_period_state_loader_for_live_macd() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 22).unwrap();
    let start_date = prepared_cache_start_date(previous_trade_date);
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

    run_db_native_intraday_screen_with_loaders(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: true,
            environment_state: Some("neutral".to_string()),
        },
        &provider,
        "15:00:00",
        |_duckdb_path, trade_date| {
            assert_eq!(trade_date, pick_date);
            Ok(previous_trade_date)
        },
        |_duckdb_path, actual_start, actual_end| {
            assert_eq!(actual_start, start_date);
            assert_eq!(actual_end, previous_trade_date);
            let mut row = MarketRow {
                ts_code: "000001.SZ".to_string(),
                trade_date: previous_trade_date,
                open: 10.0,
                high: 10.3,
                low: 9.9,
                close: 10.1,
                vol: 1000.0,
                turnover_rate: Some(1.0),
                adj_factor: Some(2.0),
                db_factors: Default::default(),
            };
            row.db_factors.insert("rolling_ma25_qfq".to_string(), 19.8);
            row.db_factors
                .insert("_czsc_snapshot_available".to_string(), 1.0);
            row.db_factors
                .insert("_czsc_latest_zs_zg".to_string(), 20.4);
            Ok(MarketDataset {
                rows: vec![row],
                db_data_gaps: std::collections::BTreeMap::from([(
                    "index_moneyflow_cnt_ths".to_string(),
                    DbDataGap::missing_rows(1, 0),
                )]),
            })
        },
        |_duckdb_path, symbols, trade_date| {
            assert_eq!(symbols, &["000001.SZ".to_string()]);
            assert_eq!(trade_date, pick_date);
            Ok(vec![
                MacdPeriodState {
                    ts_code: "000001.SZ".to_string(),
                    period_type: "daily".to_string(),
                    ema12: 18.0,
                    ema26: 17.0,
                    dea: 0.4,
                    period_count: 240,
                },
                MacdPeriodState {
                    ts_code: "000001.SZ".to_string(),
                    period_type: "weekly".to_string(),
                    ema12: 17.0,
                    ema26: 16.4,
                    dea: 0.2,
                    period_count: 80,
                },
                MacdPeriodState {
                    ts_code: "000001.SZ".to_string(),
                    period_type: "monthly".to_string(),
                    ema12: 16.0,
                    ema26: 15.8,
                    dea: 0.1,
                    period_count: 36,
                },
            ])
        },
    )
    .unwrap();

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
    let latest = prepared.last().unwrap();
    let live_ema12 = 18.0 * (11.0 / 13.0) + 21.2 * (2.0 / 13.0);
    let live_ema26 = 17.0 * (25.0 / 27.0) + 21.2 * (2.0 / 27.0);
    let live_dif = live_ema12 - live_ema26;
    let live_dea = 0.4 * 0.8 + live_dif * 0.2;

    assert_eq!(latest.trade_date, pick_date);
    assert!((latest.dif - live_dif).abs() < 1e-9);
    assert!((latest.dea - live_dea).abs() < 1e-9);
    assert!((latest.macd_hist - (live_dif - live_dea)).abs() < 1e-9);
    assert_eq!(latest.db_factors["macd_daily_period_count"], 241.0);
    assert!(latest.db_factors["macd_weekly_hist"].is_finite());
    assert!(latest.db_factors["macd_monthly_hist"].is_finite());
    assert_eq!(latest.db_factors["rolling_ma25_qfq"], 19.8);
    assert_eq!(latest.db_factors["_czsc_snapshot_available"], 1.0);
    assert_eq!(latest.db_factors["_czsc_latest_zs_zg"], 20.4);
    assert!(!latest.db_factors.contains_key("left_peak_valid"));
    assert_eq!(
        latest.db_factors["intraday_structure_source_previous_eod"],
        1.0
    );

    let dataset = load_prepared_dataset_for_mode(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
    )
    .unwrap()
    .unwrap();
    assert_eq!(
        dataset.db_data_gaps["index_moneyflow_cnt_ths"],
        DbDataGap::missing_rows(1, 0)
    );
    let manifest: serde_json::Value = serde_json::from_slice(
        &std::fs::read(
            temp.path()
                .join("factors/2026-05-25.intraday.b2/manifest.json"),
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(
        manifest["db_data_gaps"]["index_moneyflow_cnt_ths"],
        serde_json::json!({
            "reason": "missing_rows",
            "expected_rows": 1,
            "actual_rows": 0
        })
    );
}

#[test]
fn db_native_intraday_screen_skips_period_state_loader_when_table_is_unavailable() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 22).unwrap();
    let start_date = prepared_cache_start_date(previous_trade_date);
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

    let output_path = run_db_native_intraday_screen_with_loaders(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: true,
            environment_state: Some("neutral".to_string()),
        },
        &provider,
        "15:00:00",
        |_duckdb_path, _trade_date| Ok(previous_trade_date),
        |_duckdb_path, actual_start, actual_end| {
            assert_eq!(actual_start, start_date);
            assert_eq!(actual_end, previous_trade_date);
            Ok(MarketDataset {
                rows: vec![MarketRow {
                    ts_code: "000001.SZ".to_string(),
                    trade_date: previous_trade_date,
                    open: 10.0,
                    high: 10.3,
                    low: 9.9,
                    close: 10.1,
                    vol: 1000.0,
                    turnover_rate: Some(1.0),
                    adj_factor: Some(2.0),
                    db_factors: Default::default(),
                }],
                db_data_gaps: std::collections::BTreeMap::from([(
                    "calc_indicator_state".to_string(),
                    DbDataGap::missing_table(),
                )]),
            })
        },
        |_duckdb_path, _symbols, _trade_date| {
            panic!("unavailable period state table must not be queried")
        },
    )
    .unwrap();

    assert_eq!(
        output_path,
        temp.path().join("candidates/2026-05-25.intraday.b2.json")
    );
    let dataset = load_prepared_dataset_for_mode(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
    )
    .unwrap()
    .unwrap();
    let latest = dataset.rows.last().unwrap();
    assert_eq!(latest.trade_date, pick_date);
    assert!(!latest.db_factors.contains_key("macd_weekly_prev_hist"));
    assert_eq!(
        dataset.db_data_gaps["calc_indicator_state"],
        DbDataGap::missing_table()
    );
    let manifest: serde_json::Value = serde_json::from_slice(
        &std::fs::read(
            temp.path()
                .join("factors/2026-05-25.intraday.b2/manifest.json"),
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(
        manifest["db_data_gaps"]["calc_indicator_state"],
        serde_json::json!({"reason": "missing_table"})
    );
}

#[test]
fn db_native_intraday_screen_filters_snapshot_universe_and_skips_incomplete_period_state() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 22).unwrap();
    let start_date = prepared_cache_start_date(previous_trade_date);
    let provider = StaticRtKProvider::new([
        (
            "*.SH",
            vec![RawRtKRow::from_value(serde_json::json!({
                "ts_code": "510050.SH",
                "name": "ETF",
                "open": 3.0,
                "high": 3.1,
                "low": 2.9,
                "close": 3.05,
                "vol": 130000.0,
                "amount": 1390000.0
            }))],
        ),
        (
            "*.SZ",
            vec![
                RawRtKRow::from_value(serde_json::json!({
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "open": 10.2,
                    "high": 10.8,
                    "low": 10.1,
                    "close": 10.6,
                    "vol": 130000.0,
                    "amount": 1390000.0
                })),
                RawRtKRow::from_value(serde_json::json!({
                    "ts_code": "000002.SZ",
                    "name": "万科A",
                    "open": 8.2,
                    "high": 8.8,
                    "low": 8.1,
                    "close": 8.6,
                    "vol": 120000.0,
                    "amount": 1290000.0
                })),
                RawRtKRow::from_value(serde_json::json!({
                    "ts_code": "128001.SZ",
                    "name": "转债",
                    "open": 110.0,
                    "high": 111.0,
                    "low": 109.0,
                    "close": 110.5,
                    "vol": 1000.0,
                    "amount": 110500.0
                })),
            ],
        ),
        ("*.BJ", vec![]),
    ]);

    run_db_native_intraday_screen_with_loaders(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        &provider,
        "15:00:00",
        |_duckdb_path, _trade_date| Ok(previous_trade_date),
        |_duckdb_path, actual_start, actual_end| {
            assert_eq!(actual_start, start_date);
            assert_eq!(actual_end, previous_trade_date);
            Ok(vec![
                MarketRow {
                    ts_code: "000001.SZ".to_string(),
                    trade_date: previous_trade_date,
                    open: 10.0,
                    high: 10.3,
                    low: 9.9,
                    close: 10.1,
                    vol: 1000.0,
                    turnover_rate: Some(1.0),
                    adj_factor: Some(2.0),
                    db_factors: Default::default(),
                },
                MarketRow {
                    ts_code: "000002.SZ".to_string(),
                    trade_date: previous_trade_date,
                    open: 8.0,
                    high: 8.3,
                    low: 7.9,
                    close: 8.1,
                    vol: 1000.0,
                    turnover_rate: Some(1.0),
                    adj_factor: Some(1.5),
                    db_factors: Default::default(),
                },
            ])
        },
        |_duckdb_path, _symbols, _trade_date| {
            assert_eq!(
                _symbols,
                &["000001.SZ".to_string(), "000002.SZ".to_string()]
            );
            Ok(vec![
                MacdPeriodState {
                    ts_code: "000001.SZ".to_string(),
                    period_type: "daily".to_string(),
                    ema12: 18.0,
                    ema26: 17.0,
                    dea: 0.4,
                    period_count: 240,
                },
                MacdPeriodState {
                    ts_code: "000001.SZ".to_string(),
                    period_type: "weekly".to_string(),
                    ema12: 17.0,
                    ema26: 16.4,
                    dea: 0.2,
                    period_count: 80,
                },
                MacdPeriodState {
                    ts_code: "000001.SZ".to_string(),
                    period_type: "monthly".to_string(),
                    ema12: 16.0,
                    ema26: 15.8,
                    dea: 0.1,
                    period_count: 36,
                },
            ])
        },
    )
    .unwrap();

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
    assert!(prepared.iter().any(|row| {
        row.ts_code == "000001.SZ"
            && row.trade_date == pick_date
            && row.db_factors.contains_key("macd_daily_dif")
            && row.db_factors.contains_key("macd_weekly_dif")
            && row.db_factors.contains_key("macd_monthly_dif")
            && row.db_factors.contains_key("intraday_price_live_qfq")
    }));
    assert!(
        !prepared
            .iter()
            .any(|row| row.ts_code == "000002.SZ" && row.trade_date == pick_date)
    );
    assert!(
        !prepared
            .iter()
            .any(|row| row.ts_code == "510050.SH" || row.ts_code == "128001.SZ")
    );

    let result: serde_json::Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("candidates/2026-05-25.intraday.b2.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(result["stats"]["intraday_snapshot_skipped_non_universe"], 2);
    assert_eq!(
        result["stats"]["intraday_snapshot_skipped_missing_macd_state"],
        1
    );
}

#[test]
fn db_native_intraday_screen_skips_snapshot_rows_without_live_qfq_price() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 22).unwrap();
    let start_date = prepared_cache_start_date(previous_trade_date);
    let provider = StaticRtKProvider::new([
        ("*.SH", vec![]),
        (
            "*.SZ",
            vec![
                RawRtKRow::from_value(serde_json::json!({
                    "ts_code": "000001.SZ",
                    "name": "平安银行",
                    "open": 10.2,
                    "high": 10.8,
                    "low": 10.1,
                    "close": 10.6,
                    "vol": 130000.0,
                    "amount": 1390000.0
                })),
                RawRtKRow::from_value(serde_json::json!({
                    "ts_code": "000002.SZ",
                    "name": "万科A",
                    "open": 8.2,
                    "high": 8.8,
                    "low": 8.1,
                    "close": 8.6,
                    "vol": 120000.0,
                    "amount": 1290000.0
                })),
            ],
        ),
        ("*.BJ", vec![]),
    ]);

    run_db_native_intraday_screen_with_loaders(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: temp.path().to_path_buf(),
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        &provider,
        "15:00:00",
        |_duckdb_path, _trade_date| Ok(previous_trade_date),
        |_duckdb_path, actual_start, actual_end| {
            assert_eq!(actual_start, start_date);
            assert_eq!(actual_end, previous_trade_date);
            Ok(vec![
                MarketRow {
                    ts_code: "000001.SZ".to_string(),
                    trade_date: previous_trade_date,
                    open: 10.0,
                    high: 10.3,
                    low: 9.9,
                    close: 10.1,
                    vol: 1000.0,
                    turnover_rate: Some(1.0),
                    adj_factor: Some(2.0),
                    db_factors: Default::default(),
                },
                MarketRow {
                    ts_code: "000002.SZ".to_string(),
                    trade_date: previous_trade_date,
                    open: 8.0,
                    high: 8.3,
                    low: 7.9,
                    close: 8.1,
                    vol: 1000.0,
                    turnover_rate: Some(1.0),
                    adj_factor: None,
                    db_factors: Default::default(),
                },
            ])
        },
        |_duckdb_path, symbols, _trade_date| {
            assert_eq!(symbols, &["000001.SZ".to_string(), "000002.SZ".to_string()]);
            Ok(vec![
                macd_state("000001.SZ", "daily"),
                macd_state("000001.SZ", "weekly"),
                macd_state("000001.SZ", "monthly"),
                macd_state("000002.SZ", "daily"),
                macd_state("000002.SZ", "weekly"),
                macd_state("000002.SZ", "monthly"),
            ])
        },
    )
    .unwrap();

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
    assert!(prepared.iter().any(|row| {
        row.ts_code == "000001.SZ"
            && row.trade_date == pick_date
            && row.db_factors.contains_key("intraday_price_live_qfq")
            && row.db_factors.contains_key("macd_daily_dif")
    }));
    assert!(
        !prepared
            .iter()
            .any(|row| row.ts_code == "000002.SZ" && row.trade_date == pick_date)
    );

    let result: serde_json::Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("candidates/2026-05-25.intraday.b2.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(result["stats"]["intraday_snapshot_skipped_non_universe"], 0);
    assert_eq!(
        result["stats"]["intraday_snapshot_skipped_missing_macd_state"],
        0
    );
    assert_eq!(
        result["stats"]["intraday_snapshot_skipped_missing_live_qfq_price"],
        1
    );
}

fn intraday_b2_positive_monthly_market_rows(
    first_date: NaiveDate,
    previous_trade_date: NaiveDate,
) -> Vec<MarketRow> {
    let days = (previous_trade_date - first_date).num_days() + 1;
    (0..days)
        .map(|offset| {
            let trade_date = first_date + Duration::days(offset);
            let close = if trade_date.month() < 5 {
                20.0 + offset as f64 * 0.08
            } else if trade_date == previous_trade_date {
                27.3
            } else {
                30.0 - (trade_date.day() as f64 - 1.0) * 0.1
            };
            MarketRow {
                ts_code: "000001.SZ".to_string(),
                trade_date,
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
        .collect()
}

#[test]
fn intraday_screen_uses_previous_trade_date_loader_for_history_window() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 22).unwrap();
    let start_date = prepared_cache_start_date(previous_trade_date);
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
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        &provider,
        "15:00:00",
        |duckdb_path, trade_date| {
            assert_eq!(duckdb_path, "fixture.duckdb");
            assert_eq!(trade_date, pick_date);
            Ok(previous_trade_date)
        },
        |duckdb_path, actual_start, actual_end| {
            assert_eq!(duckdb_path, "fixture.duckdb");
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

fn prepare_test_market_rows(rows: Vec<MarketRow>) -> anyhow::Result<Vec<PreparedRow>> {
    let root = tempfile::tempdir()?;
    let pick_date = rows.iter().map(|row| row.trade_date).max().unwrap();
    run_screen_with_loader(
        ScreenRequest {
            method: Method::B2,
            pick_date,
            runtime_root: root.path().to_path_buf(),
            duckdb_path: "fixture.duckdb".to_string(),
            recompute: true,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        },
        |_, _, _| Ok(rows),
    )?;
    Ok(load_prepared_cache(
        root.path(),
        Method::B2,
        pick_date,
        prepared_cache_start_date(pick_date),
        pick_date,
    )?
    .unwrap())
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

fn macd_state(ts_code: &str, period_type: &str) -> MacdPeriodState {
    MacdPeriodState {
        ts_code: ts_code.to_string(),
        period_type: period_type.to_string(),
        ema12: 18.0,
        ema26: 17.0,
        dea: 0.4,
        period_count: 240,
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
        db_factors: Default::default(),
    }
}

fn b2_positive_monthly_rows(
    code: &str,
    first_date: NaiveDate,
    len: usize,
    base_close: f64,
) -> Vec<PreparedRow> {
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

fn ma25_prepared_rows(
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
                db_factors: Default::default(),
            }
        })
        .collect()
}

#[test]
fn selection_fallback_prepares_window_in_memory_when_cache_is_absent() {
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let window_start = prepared_cache_start_date(pick_date);

    let prepared = load_db_native_prepared_window_with_loader(
        "fixture.duckdb",
        pick_date,
        |_duckdb_path, start_date, end_date| {
            assert_eq!(start_date, window_start);
            assert_eq!(end_date, pick_date);
            Ok((0..365)
                .map(|offset| {
                    market_row_at_date(
                        window_start + Duration::days(offset),
                        10.0 + offset as f64 * 0.01,
                        100.0,
                    )
                })
                .chain(std::iter::once(market_row_at_date(pick_date, 12.52, 100.0)))
                .collect::<Vec<MarketRow>>())
        },
    )
    .unwrap();

    let prepared = prepared.expect("a complete window should be prepared in memory");
    assert!(prepared.rows.iter().any(|row| row.trade_date == pick_date));
}

#[test]
fn selection_fallback_returns_none_when_window_is_too_short() {
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();

    let prepared = load_db_native_prepared_window_with_loader(
        "fixture.duckdb",
        pick_date,
        |_duckdb_path, _start_date, _end_date| {
            Ok(vec![market_row_at_date(pick_date, 12.52, 100.0)])
        },
    )
    .unwrap();

    assert!(prepared.is_none());
}
