use chrono::{Duration, NaiveDate};
use stock_select::cache::load_prepared_cache;
use stock_select::factors::registry::{build_candidate_factor_rows, factor_profile_for_method};
use stock_select::factors::types::FactorValue;
use stock_select::model::{Candidate, MarketRow, Method, PreparedRow};
use stock_select::screening::{
    prepared_cache_start_date, run_screen_with_loader, PoolSource, ScreenRequest,
};

#[test]
fn screen_prepared_cache_feeds_real_ma_and_zx_values_into_factor_export() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(129);
    let start_date = prepared_cache_start_date(pick_date);
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
        Ok((1..=130)
            .map(|day| {
                let close = 100.0 + day as f64;
                MarketRow {
                    ts_code: "000001.SZ".to_string(),
                    trade_date: first_date + Duration::days(day as i64 - 1),
                    open: close - 0.5,
                    high: close + 1.0,
                    low: close - 2.0,
                    close,
                    vol: 1000.0 + day as f64 * 10.0,
                    turnover_rate: Some(1.0 + day as f64 / 100.0),
                    adj_factor: None,
                    db_factors: Default::default(),
                }
            })
            .collect())
    })
    .unwrap();

    let prepared = load_prepared_cache(temp.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();
    let latest = prepared
        .iter()
        .find(|row| row.ts_code == "000001.SZ" && row.trade_date == pick_date)
        .unwrap();

    assert_eq!(latest.close, 230.0);
    assert_eq!(latest.ma25, Some(218.0));
    assert_eq!(latest.ma60, Some(200.5));
    assert!(latest.zxdkx.is_some());
    assert_ne!(latest.zxdq, Some(latest.close));

    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: latest.close,
        turnover_n: latest.turnover_n,
        signal: Some("B2".to_string()),
        yellow_b1: None,
    };
    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B2, None);
    let factors = &rows[0].factors;

    assert_eq!(
        factors.get("close_to_ma25_pct"),
        Some(&FactorValue::Number(5.5046))
    );
    assert_eq!(
        factors.get("ma25_slope_5d_pct"),
        Some(&FactorValue::Number(2.3474))
    );
    assert_eq!(
        factors.get("close_to_zxdkx_pct"),
        Some(&FactorValue::Number(12.8142))
    );
    assert_eq!(
        factors.get("ma25_to_zxdkx_pct"),
        Some(&FactorValue::Number(6.9283))
    );
    assert_eq!(
        factors.get("zxdkx_slope_5d_pct"),
        Some(&FactorValue::Number(2.5141))
    );
    assert_eq!(
        factors.get("zxdq_slope_5d_pct"),
        Some(&FactorValue::Number(2.3148))
    );
}

#[test]
fn db_factor_extras_flow_from_screen_loader_into_candidate_factors() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(129);
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
        Ok((1..=130)
            .map(|day| {
                let close = 100.0 + day as f64;
                let mut row = MarketRow {
                    ts_code: "000001.SZ".to_string(),
                    trade_date: first_date + Duration::days(day as i64 - 1),
                    open: close - 0.5,
                    high: close + 1.0,
                    low: close - 2.0,
                    close,
                    vol: 1000.0 + day as f64 * 10.0,
                    turnover_rate: Some(1.0 + day as f64 / 100.0),
                    adj_factor: None,
                    db_factors: Default::default(),
                };
                if row.trade_date == pick_date {
                    row.db_factors.insert("boll_width_pct".to_string(), 8.25);
                    row.db_factors.insert("dmi_adx_qfq".to_string(), 24.0);
                    row.db_factors.insert("dmi_pdi_qfq".to_string(), 31.0);
                    row.db_factors.insert("dmi_mdi_qfq".to_string(), 19.0);
                    row.db_factors
                        .insert("dmi_pdi_mdi_spread_qfq".to_string(), 12.0);
                    row.db_factors
                        .insert("dmi_adx_adxr_gap_qfq".to_string(), 9.0);
                    row.db_factors.insert("wr_qfq".to_string(), -12.5);
                    row.db_factors.insert("mtm_qfq".to_string(), 1.8);
                    row.db_factors.insert("roc_qfq".to_string(), 4.2);
                    row.db_factors.insert("trix_qfq".to_string(), 0.35);
                    row.db_factors.insert("obv_qfq".to_string(), 123456.0);
                    row.db_factors.insert("vr_qfq".to_string(), 135.0);
                    row.db_factors.insert("psy_qfq".to_string(), 66.7);
                    row.db_factors.insert("bias1_qfq".to_string(), 2.4);
                    row.db_factors.insert("turnover_rate_f".to_string(), 3.75);
                    row.db_factors.insert("cyq_winner_rate".to_string(), 64.5);
                    row.db_factors
                        .insert("cyq_cost_50_to_close_pct".to_string(), -3.2);
                    row.db_factors
                        .insert("cyq_cost_85_to_close_pct".to_string(), 4.8);
                    row.db_factors
                        .insert("cyq_weight_avg_to_close_pct".to_string(), -1.5);
                    row.db_factors
                        .insert("cyq_cost_70_width_pct".to_string(), 12.4);
                    row.db_factors
                        .insert("cyq_cost_90_width_pct".to_string(), 20.6);
                }
                row
            })
            .collect())
    })
    .unwrap();

    let start_date = prepared_cache_start_date(pick_date);
    let prepared = load_prepared_cache(temp.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();
    let latest = prepared
        .iter()
        .find(|row| row.ts_code == "000001.SZ" && row.trade_date == pick_date)
        .unwrap();
    assert_eq!(latest.db_factors["boll_width_pct"], 8.25);

    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: latest.close,
        turnover_n: latest.turnover_n,
        signal: Some("B2".to_string()),
        yellow_b1: None,
    };
    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B2, None);
    let factors = &rows[0].factors;

    assert_eq!(
        factors.get("boll_width_pct"),
        Some(&FactorValue::Number(8.25))
    );
    assert_eq!(factors.get("wr_qfq"), Some(&FactorValue::Number(-12.5)));
    assert_eq!(factors.get("dmi_adx_qfq"), Some(&FactorValue::Number(24.0)));
    assert_eq!(factors.get("dmi_pdi_qfq"), Some(&FactorValue::Number(31.0)));
    assert_eq!(factors.get("dmi_mdi_qfq"), Some(&FactorValue::Number(19.0)));
    assert_eq!(
        factors.get("dmi_pdi_mdi_spread_qfq"),
        Some(&FactorValue::Number(12.0))
    );
    assert_eq!(
        factors.get("dmi_adx_adxr_gap_qfq"),
        Some(&FactorValue::Number(9.0))
    );
    assert_eq!(factors.get("mtm_qfq"), Some(&FactorValue::Number(1.8)));
    assert_eq!(factors.get("roc_qfq"), Some(&FactorValue::Number(4.2)));
    assert_eq!(factors.get("trix_qfq"), Some(&FactorValue::Number(0.35)));
    assert_eq!(factors.get("obv_qfq"), Some(&FactorValue::Number(123456.0)));
    assert_eq!(factors.get("vr_qfq"), Some(&FactorValue::Number(135.0)));
    assert_eq!(factors.get("psy_qfq"), Some(&FactorValue::Number(66.7)));
    assert_eq!(factors.get("bias1_qfq"), Some(&FactorValue::Number(2.4)));
    assert_eq!(
        factors.get("turnover_rate_f"),
        Some(&FactorValue::Number(3.75))
    );
    assert_eq!(
        factors.get("cyq_winner_rate"),
        Some(&FactorValue::Number(64.5))
    );
    assert_eq!(
        factors.get("cyq_cost_50_to_close_pct"),
        Some(&FactorValue::Number(-3.2))
    );
    assert_eq!(
        factors.get("cyq_cost_85_to_close_pct"),
        Some(&FactorValue::Number(4.8))
    );
    assert_eq!(
        factors.get("cyq_weight_avg_to_close_pct"),
        Some(&FactorValue::Number(-1.5))
    );
    assert_eq!(
        factors.get("cyq_cost_70_width_pct"),
        Some(&FactorValue::Number(12.4))
    );
    assert_eq!(
        factors.get("cyq_cost_90_width_pct"),
        Some(&FactorValue::Number(20.6))
    );
}

#[test]
fn factor_artifact_no_longer_exports_legacy_sw_l2_relative_factors() {
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(24);
    let prepared = (0..25)
        .map(|offset| {
            let close = 100.0 + offset as f64;
            let mut row = prepared_row(
                "000001.SZ",
                first_date + Duration::days(offset),
                close,
                1000.0,
            );
            if offset == 24 {
                row.db_factors.insert("sw_l2_ret5_pct".to_string(), 4.0);
                row.db_factors.insert("sw_l2_ret20_pct".to_string(), 10.0);
            }
            row
        })
        .collect::<Vec<_>>();
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: prepared.last().unwrap().close,
        turnover_n: prepared.last().unwrap().turnover_n,
        signal: Some("B2".to_string()),
        yellow_b1: None,
    };

    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B2, None);
    let factors = &rows[0].factors;

    assert!(!factors.contains_key("stock_vs_sw_l2_ret5_pct"));
    assert!(!factors.contains_key("stock_vs_sw_l2_ret20_pct"));
}

#[test]
fn factor_artifact_exports_db_native_special_structure_factor_family_names() {
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(129);
    let prepared = (0..=129)
        .map(|offset| {
            let mut row = prepared_row(
                "000001.SZ",
                first_date + Duration::days(offset),
                10.0 + offset as f64 * 0.1,
                if offset == 119 {
                    10_000.0
                } else {
                    1000.0 + offset as f64
                },
            );
            if offset == 129 {
                row.db_factors.insert("left_peak_valid".to_string(), 1.0);
                row.db_factors.insert("left_peak_b_div_a".to_string(), 1.03);
                row.db_factors
                    .insert("left_peak_days_since_peak".to_string(), 17.0);
            }
            row
        })
        .collect::<Vec<_>>();
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: prepared.last().unwrap().close,
        turnover_n: prepared.last().unwrap().turnover_n,
        signal: Some("B2".to_string()),
        yellow_b1: None,
    };

    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B2, Some("neutral"));
    let factors = &rows[0].factors;

    for key in [
        "structure_box_position_120d_pct",
        "structure_box_mid_position_120d_pct",
        "structure_close_to_120d_max_pct",
        "structure_close_to_120d_min_pct",
        "structure_close_to_120d_range_center_pct",
        "structure_range_width_120d_pct",
        "structure_hl90_position",
        "structure_hl90_range_pct",
        "structure_range_compression_20d",
        "structure_range_compression_40d",
        "structure_close_to_ma25_pct",
        "structure_low_to_ma25_pct",
        "structure_near_ma25_support_flag",
        "structure_ma25_slope_5d_pct",
        "structure_ma_aligned_flag",
        "structure_zxdkx",
        "structure_close_to_zxdkx_pct",
        "structure_zxdq_slope_5d_pct",
        "structure_zxdkx_slope_5d_pct",
        "macd_state_phase_score",
        "macd_state_daily_phase_type",
        "macd_state_daily_wave_index",
        "macd_state_daily_wave_stage",
        "macd_state_weekly_phase_type",
        "macd_state_weekly_wave_index",
        "macd_state_weekly_wave_stage",
        "macd_state_weekly_daily_combo_type",
        "macd_state_daily_rising_initial_flag",
        "macd_state_top_divergence_flag",
        "macd_daily_dif_to_close_pct",
        "macd_daily_dea_to_close_pct",
        "macd_daily_hist_to_close_pct",
        "macd_daily_hist_delta_to_close_pct",
        "macd_daily_hist_slope_3d_to_close_pct",
        "macd_daily_hist_positive_flag",
        "macd_weekly_dea_pctile",
        "macd_weekly_hist",
        "macd_monthly_dea_pctile",
        "macd_monthly_hist",
        "volume_event_abnormal_days_ago",
        "volume_event_abnormal_to_ma20_ratio",
        "volume_event_body_pct",
        "volume_event_price_to_current_pct",
        "volume_event_post_drawdown_pct",
        "volume_event_redundant_position_pct",
        "bar_close_position_pct",
        "bar_upper_shadow_pct",
        "bar_amplitude_pct",
        "bar_body_pct",
        "signal_bullish_engulf_prev_bearish_flag",
        "signal_bullish_engulf_volume_ratio",
        "signal_yang_engulf_ma25_flag",
        "signal_prev_b2_flag",
        "signal_b3_plus_flag",
        "left_peak_valid",
        "left_peak_b_div_a",
        "left_peak_days_since_peak",
    ] {
        assert!(
            factors.contains_key(key),
            "missing DB-native factor family key {key}"
        );
    }
}

#[test]
fn candidate_factor_rows_include_market_state_from_prepared_cross_section() {
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_date = pick_date - Duration::days(1);
    let mut prepared = vec![
        prepared_row("000001.SZ", previous_date, 10.0, 1000.0),
        prepared_row("000002.SZ", previous_date, 20.0, 1000.0),
        prepared_row("000003.SZ", previous_date, 30.0, 1000.0),
        prepared_row("000001.SZ", pick_date, 11.0, 1100.0),
        prepared_row("000002.SZ", pick_date, 21.0, 1200.0),
        prepared_row("000003.SZ", pick_date, 27.0, 1300.0),
    ];
    prepared[3].chg_d = Some(10.0);
    prepared[4].chg_d = Some(5.0);
    prepared[5].chg_d = Some(-10.0);
    prepared[3]
        .db_factors
        .insert("dist_to_up_limit_pct".to_string(), 0.0);
    prepared[5]
        .db_factors
        .insert("dist_to_down_limit_pct".to_string(), 0.0);
    for row in prepared
        .iter_mut()
        .filter(|row| row.trade_date == pick_date)
    {
        row.db_factors
            .insert("net_mf_amount_to_amount_pct".to_string(), 3.0);
    }
    let candidates = vec![
        Candidate {
            code: "000001.SZ".to_string(),
            pick_date,
            close: 11.0,
            turnover_n: 1.0,
            signal: Some("B2".to_string()),
            yellow_b1: None,
        },
        Candidate {
            code: "000002.SZ".to_string(),
            pick_date,
            close: 21.0,
            turnover_n: 1.0,
            signal: Some("B2".to_string()),
            yellow_b1: None,
        },
    ];

    let rows = build_candidate_factor_rows(&candidates, &prepared, Method::B2, None);

    for row in &rows {
        assert_eq!(
            row.factors.get("market_up_ratio"),
            Some(&FactorValue::Number(0.6667))
        );
        assert_eq!(
            row.factors.get("market_ge5_ratio"),
            Some(&FactorValue::Number(0.6667))
        );
        assert_eq!(
            row.factors.get("market_le_minus5_ratio"),
            Some(&FactorValue::Number(0.3333))
        );
        assert_eq!(
            row.factors.get("market_median_pct_chg"),
            Some(&FactorValue::Number(5.0))
        );
        assert_eq!(
            row.factors.get("market_net_mf_to_amount_pct"),
            Some(&FactorValue::Number(3.0))
        );
        assert_eq!(
            row.factors.get("market_approx_limit_up_count"),
            Some(&FactorValue::Number(1.0))
        );
        assert_eq!(
            row.factors.get("market_approx_limit_down_count"),
            Some(&FactorValue::Number(1.0))
        );
        assert!(matches!(
            row.factors.get("market_amount_ma5_ratio"),
            Some(FactorValue::Number(value)) if *value > 1.0
        ));
    }
}

#[test]
fn market_amount_ma5_ratio_uses_raw_price_basis_after_qfq_prepare() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 5, 1).unwrap();
    let pick_date = first_date + Duration::days(4);
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
        Ok((0..5)
            .map(|offset| {
                let trade_date = first_date + Duration::days(offset);
                let mut row = market_row("000001.SZ", trade_date, 10.0, 100.0);
                row.open = 10.0;
                row.high = 10.0;
                row.low = 10.0;
                row.adj_factor = Some(if offset < 4 { 0.5 } else { 1.0 });
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
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: latest.close,
        turnover_n: latest.turnover_n,
        signal: Some("B2".to_string()),
        yellow_b1: None,
    };

    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B2, None);

    assert_eq!(
        rows[0].factors.get("market_amount_ma5_ratio"),
        Some(&FactorValue::Number(1.0))
    );
}

#[test]
fn b2_factor_profile_does_not_add_chip_age_summary_even_when_chip_inputs_are_available() {
    let trade_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let prepared = (0..3)
        .map(|offset| {
            let mut row = prepared_row(
                "000001.SZ",
                trade_date - Duration::days(2 - offset),
                10.0 + offset as f64,
                1000.0 + offset as f64,
            );
            row.db_factors
                .insert("chip_vwap".to_string(), 10.0 + offset as f64);
            row.db_factors.insert("chip_turnover".to_string(), 0.20);
            row
        })
        .collect::<Vec<_>>();
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date: trade_date,
        close: prepared.last().unwrap().close,
        turnover_n: prepared.last().unwrap().turnover_n,
        signal: Some("B2".to_string()),
        yellow_b1: None,
    };

    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B2, None);
    let factors = &rows[0].factors;

    assert!(!factors.contains_key("total_mass"));
    assert!(!factors.contains_key("chip_age_layer_sum"));
    assert!(!factors.contains_key("chip_age_ultrashort_ratio"));
    assert!(!factors.contains_key("chip_age_mid_ratio"));
    assert!(!factors.contains_key("profit_ratio"));
    assert!(!factors.contains_key("avg_cost_close_ratio"));
    assert!(!factors.contains_key("peak_price_close_ratio"));
    assert!(!factors.contains_key("chip_entropy"));
    assert!(!factors.contains_key("chip_age_l0_b00"));
    assert!(!factors.contains_key("chip_age_l3_b31"));
    assert_eq!(
        factors
            .keys()
            .filter(|key| key.starts_with("chip_age_l") && key.contains("_b"))
            .count(),
        0
    );
    assert_eq!(rows[0].diagnostics["factor_profile"], "b2");
    assert_eq!(
        rows[0].diagnostics["factor_bundles"],
        serde_json::json!(["raw_common", "b2_semantic"])
    );
}

#[test]
fn b3_uses_method_registered_factor_profile_matching_b2_for_now() {
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let prepared = (0..3)
        .map(|offset| {
            let mut row = prepared_row(
                "000001.SZ",
                pick_date - Duration::days(2 - offset),
                10.0 + offset as f64,
                1000.0 + offset as f64,
            );
            row.db_factors
                .insert("chip_vwap".to_string(), 10.0 + offset as f64);
            row.db_factors.insert("chip_turnover".to_string(), 0.20);
            row
        })
        .collect::<Vec<_>>();
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: prepared.last().unwrap().close,
        turnover_n: prepared.last().unwrap().turnover_n,
        signal: Some("B3".to_string()),
        yellow_b1: None,
    };

    let b2_profile = factor_profile_for_method(Method::B2);
    let b3_profile = factor_profile_for_method(Method::B3);
    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B3, None);

    assert_ne!(b2_profile.bundles, b3_profile.bundles);
    assert_eq!(rows[0].method, Method::B3);
    assert_eq!(rows[0].diagnostics["factor_profile"], "b3");
    assert_eq!(
        rows[0].diagnostics["factor_bundles"],
        serde_json::json!(["raw_common", "b3_semantic"])
    );
    assert!(!rows[0].factors.contains_key("chip_age_ultrashort_ratio"));
    assert!(!rows[0].factors.contains_key("chip_entropy"));
    assert!(!rows[0].factors.contains_key("trend_structure"));
    assert_eq!(
        rows[0].factors.get("signal"),
        Some(&FactorValue::Category("B3".to_string()))
    );
}

#[test]
fn b3_factor_profile_adds_b3_specific_raw_factors_only_for_b3() {
    let first_date = NaiveDate::from_ymd_opt(2026, 5, 22).unwrap();
    let pick_date = first_date + Duration::days(3);
    let prepared = vec![
        PreparedRow {
            high: 10.0,
            low: 9.5,
            open: 10.0,
            j: 30.0,
            ..prepared_row("000001.SZ", first_date, 10.0, 1000.0)
        },
        PreparedRow {
            high: 10.1,
            low: 9.6,
            open: 9.8,
            j: 35.0,
            ..prepared_row("000001.SZ", first_date + Duration::days(1), 10.1, 900.0)
        },
        PreparedRow {
            high: 10.6,
            low: 10.0,
            open: 9.8,
            j: 45.0,
            ..prepared_row("000001.SZ", first_date + Duration::days(2), 10.6, 1200.0)
        },
        PreparedRow {
            high: 10.9,
            low: 10.1,
            open: 10.2,
            j: 46.0,
            ..prepared_row("000001.SZ", pick_date, 10.7, 600.0)
        },
    ];
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: 10.7,
        turnover_n: prepared[3].turnover_n,
        signal: Some("B3+".to_string()),
        yellow_b1: None,
    };

    let b3_rows = build_candidate_factor_rows(&[candidate.clone()], &prepared, Method::B3, None);
    let b2_rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B2, None);
    let b3_factors = &b3_rows[0].factors;
    let b2_factors = &b2_rows[0].factors;

    assert_eq!(
        b3_factors.get("b3_volume_shrink_ratio"),
        Some(&FactorValue::Number(0.5))
    );
    assert_eq!(
        b3_factors.get("b3_amplitude_pct"),
        Some(&FactorValue::Number(7.5472))
    );
    assert_eq!(
        b3_factors.get("b3_body_pct"),
        Some(&FactorValue::Number(4.717))
    );
    assert_eq!(
        b3_factors.get("b3_upper_shadow_pct"),
        Some(&FactorValue::Number(1.8868))
    );
    assert_eq!(
        b3_factors.get("b3_lower_shadow_pct"),
        Some(&FactorValue::Number(0.9434))
    );
    assert_eq!(
        b3_factors.get("b3_j_delta"),
        Some(&FactorValue::Number(1.0))
    );
    assert_eq!(
        b3_factors.get("b3_prev_b2_flag"),
        Some(&FactorValue::Bool(true))
    );
    assert_eq!(
        b3_factors.get("b3_plus_flag"),
        Some(&FactorValue::Bool(true))
    );
    assert_eq!(
        b3_factors.get("structure_hl90_position"),
        Some(&FactorValue::Number(1.0))
    );
    assert_eq!(
        b3_factors.get("structure_hl90_range_pct"),
        Some(&FactorValue::Number(10.9453))
    );
    assert_eq!(
        b3_factors.get("bar_upper_shadow_pct"),
        Some(&FactorValue::Number(0.0))
    );
    assert_eq!(
        b3_factors.get("signal_bullish_engulf_prev_bearish_flag"),
        Some(&FactorValue::Bool(false))
    );
    assert_eq!(
        b3_factors.get("signal_bullish_engulf_volume_ratio"),
        Some(&FactorValue::Number(1.3333))
    );
    assert_eq!(
        b3_factors.get("signal_yang_engulf_ma25_flag"),
        Some(&FactorValue::Bool(false))
    );
    assert!(!b2_factors.contains_key("b3_volume_shrink_ratio"));
    assert!(!b2_factors.contains_key("b3_prev_b2_flag"));
}

#[test]
fn b3_factor_artifact_excludes_review_scores_but_keeps_training_context() {
    let first_date = NaiveDate::from_ymd_opt(2026, 5, 1).unwrap();
    let pick_date = first_date + Duration::days(130);
    let prepared = (0..=130)
        .map(|offset| PreparedRow {
            open: 10.0 + offset as f64 * 0.03,
            high: 10.4 + offset as f64 * 0.03,
            low: 9.8 + offset as f64 * 0.03,
            close: 10.2 + offset as f64 * 0.03,
            volume: if offset == 130 { 600.0 } else { 1000.0 },
            j: 30.0 + offset as f64 * 0.1,
            ..prepared_row(
                "000001.SZ",
                first_date + Duration::days(offset),
                10.2 + offset as f64 * 0.03,
                if offset == 130 { 600.0 } else { 1000.0 },
            )
        })
        .collect::<Vec<_>>();
    let latest = prepared.last().unwrap();
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: latest.close,
        turnover_n: latest.turnover_n,
        signal: Some("B3+".to_string()),
        yellow_b1: None,
    };

    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B3, Some("neutral"));
    let factors = &rows[0].factors;

    for key in [
        "trend_structure",
        "price_position",
        "volume_behavior",
        "previous_abnormal_move",
        "weekly_daily_combo_score",
        "total_score",
        "verdict",
    ] {
        assert!(
            !factors.contains_key(key),
            "review-only key leaked into factors: {key}"
        );
    }

    for key in [
        "signal_type",
        "daily_macd_phase_type",
        "daily_macd_wave_stage",
        "weekly_macd_phase_type",
        "weekly_macd_wave_stage",
        "weekly_daily_combo_type",
        "macd_phase",
        "daily_macd_wave_index",
        "weekly_macd_wave_index",
        "near_ma25_support_flag",
        "ma_aligned_flag",
        "zxdkx_up_1d_flag",
        "breakout_distance_120d_pct",
        "range_floor_distance_120d_pct",
        "price_up_1d_flag",
        "volume_up_1d_flag",
        "b3_volume_shrink_ratio",
        "b3_prev_b2_flag",
        "b3_plus_flag",
        "env",
    ] {
        assert!(
            factors.contains_key(key),
            "training key missing from factors: {key}"
        );
    }

    assert!(matches!(
        factors.get("box_mid_position_120d_pct"),
        Some(FactorValue::Number(value)) if value.is_finite()
    ));
}
#[test]
fn lsh_factor_profile_adds_macd_state_machine_and_bullish_engulfing_factors_only_for_lsh() {
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(120);
    let mut prepared = Vec::new();
    for offset in 0..119 {
        prepared.push(PreparedRow {
            open: 10.0 + offset as f64 * 0.03,
            high: 10.4 + offset as f64 * 0.03,
            low: 9.8 + offset as f64 * 0.03,
            close: 10.2 + offset as f64 * 0.03,
            volume: 1000.0,
            ..prepared_row(
                "000001.SZ",
                first_date + Duration::days(offset),
                10.2 + offset as f64 * 0.03,
                1000.0,
            )
        });
    }
    prepared.push(PreparedRow {
        open: 16.0,
        high: 16.2,
        low: 14.8,
        close: 15.0,
        volume: 1000.0,
        ..prepared_row("000001.SZ", first_date + Duration::days(119), 15.0, 1000.0)
    });
    prepared.push(PreparedRow {
        open: 14.9,
        high: 16.8,
        low: 14.7,
        close: 16.2,
        volume: 1500.0,
        ..prepared_row("000001.SZ", pick_date, 16.2, 1500.0)
    });
    for row in &mut prepared {
        row.db_factors.insert("chip_vwap".to_string(), row.close);
        row.db_factors.insert("chip_turnover".to_string(), 0.20);
    }
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: 16.2,
        turnover_n: prepared.last().unwrap().turnover_n,
        signal: Some("LSH".to_string()),
        yellow_b1: None,
    };

    let lsh_profile = factor_profile_for_method(Method::Lsh);
    let lsh_rows = build_candidate_factor_rows(&[candidate.clone()], &prepared, Method::Lsh, None);
    let b2_rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B2, None);
    let lsh_factors = &lsh_rows[0].factors;
    let b2_factors = &b2_rows[0].factors;

    assert_eq!(lsh_profile.name, "lsh");
    assert_eq!(
        lsh_profile.bundle_names(),
        vec!["raw_common", "lsh_semantic"]
    );
    assert_eq!(
        lsh_rows[0].diagnostics["factor_bundles"],
        serde_json::json!(["raw_common", "lsh_semantic"])
    );
    assert!(!lsh_factors.contains_key("chip_age_long_ratio"));
    assert!(!lsh_factors.contains_key("chip_entropy"));
    assert!(lsh_factors.contains_key("lsh_daily_macd_wave_index"));
    assert!(lsh_factors.contains_key("lsh_weekly_macd_wave_index"));
    assert!(lsh_factors.contains_key("lsh_weekly_daily_constructive_combo_flag"));
    for key in [
        "price_vs_90d_high",
        "price_vs_90d_low",
        "price_vs_90d_mid",
        "near_ma25_support_flag",
        "ma_aligned_flag",
        "zxdkx_up_1d_flag",
        "daily_rising_initial_flag",
        "macd_top_divergence_flag",
        "breakout_distance_120d_pct",
        "range_floor_distance_120d_pct",
        "price_up_1d_flag",
        "volume_up_1d_flag",
        "turnover_to_ma5_ratio",
    ] {
        assert!(
            lsh_factors.contains_key(key),
            "missing LSH runtime factor {key}"
        );
    }
    assert_eq!(
        lsh_factors.get("lsh_bullish_engulf_prev_bearish_flag"),
        Some(&FactorValue::Bool(true))
    );
    assert_eq!(
        lsh_factors.get("lsh_volume_bullish_engulf_prev_bearish_flag"),
        Some(&FactorValue::Bool(true))
    );
    assert_eq!(
        lsh_factors.get("lsh_bullish_engulf_volume_ratio"),
        Some(&FactorValue::Number(1.5))
    );
    assert!(!b2_factors.contains_key("lsh_daily_macd_wave_index"));
    assert!(!b2_factors.contains_key("lsh_volume_bullish_engulf_prev_bearish_flag"));
}

#[test]
fn lsh_factor_profile_uses_neutral_model_feature_fallbacks_for_short_history() {
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(29);
    let prepared = (0..30)
        .map(|offset| {
            let close = 10.0 + offset as f64 * 0.1;
            let mut row = prepared_row(
                "920011.BJ",
                first_date + Duration::days(offset),
                close,
                1000.0 + offset as f64,
            );
            row.zxdkx = None;
            row.zxdq = None;
            row
        })
        .collect::<Vec<_>>();
    let candidate = Candidate {
        code: "920011.BJ".to_string(),
        pick_date,
        close: prepared.last().unwrap().close,
        turnover_n: prepared.last().unwrap().turnover_n,
        signal: Some("LSH".to_string()),
        yellow_b1: None,
    };

    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::Lsh, None);
    let factors = &rows[0].factors;

    for key in [
        "close_to_zxdkx_pct",
        "ma25_to_zxdkx_pct",
        "zxdkx_slope_5d_pct",
        "ma_aligned_flag",
        "zxdkx_up_1d_flag",
        "range_compression_40d",
        "abnormal_volume_to_ma20_ratio",
    ] {
        assert!(
            matches!(
                factors.get(key),
                Some(FactorValue::Number(_)) | Some(FactorValue::Bool(_))
            ),
            "LSH short-history factor {key} must be explicit, got {:?}",
            factors.get(key)
        );
    }
}

#[test]
fn turnover_top_pool_uses_real_ma25_ma60_trend_filter() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(129);
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

    let output_path = run_screen_with_loader(request, |_dsn, _start_date, _end_date| {
        let mut rows = Vec::new();
        for offset in 0..130 {
            let trade_date = first_date + Duration::days(offset);
            let weak_close = if offset < 70 { 200.0 } else { 100.0 };
            let strong_close = 100.0 + offset as f64 * 0.3;
            rows.push(market_row("000001.SZ", trade_date, weak_close, 5000.0));
            rows.push(market_row("000002.SZ", trade_date, strong_close, 1000.0));
        }
        Ok(rows)
    })
    .unwrap();

    let payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    let candidates = payload["candidates"].as_array().unwrap();

    assert!(
        candidates.iter().all(|row| row["code"] != "000001.SZ"),
        "weak MA structure must not pass turnover-top pool only because turnover is high"
    );
    assert_eq!(payload["stats"]["total_symbols"], 1);
    assert_eq!(payload["stats"]["eligible"], 1);
}

fn market_row(ts_code: &str, trade_date: NaiveDate, close: f64, vol: f64) -> MarketRow {
    MarketRow {
        ts_code: ts_code.to_string(),
        trade_date,
        open: close - 0.5,
        high: close + 1.0,
        low: close - 2.0,
        close,
        vol,
        turnover_rate: Some(vol / 100.0),
        adj_factor: None,
        db_factors: Default::default(),
    }
}

fn prepared_row(ts_code: &str, trade_date: NaiveDate, close: f64, volume: f64) -> PreparedRow {
    PreparedRow {
        ts_code: ts_code.to_string(),
        trade_date,
        open: close - 0.5,
        high: close + 1.0,
        low: close - 2.0,
        close,
        volume,
        turnover_n: 12.0,
        turnover_rate: Some(volume / 100.0),
        k: 50.0,
        d: 40.0,
        j: 60.0,
        zxdq: Some(close - 1.0),
        zxdkx: Some(close - 1.5),
        dif: 0.3,
        dea: 0.2,
        macd_hist: 0.1,
        ma25: Some(close - 2.0),
        ma60: Some(close - 3.0),
        ma144: Some(close - 4.0),
        chg_d: Some(1.0),
        weekly_ma_bull: true,
        max_vol_not_bearish: true,
        v_shrink: true,
        safe_mode: true,
        lt_filter: true,
        yellow_b1: false,
        db_factors: Default::default(),
    }
}
