use chrono::NaiveDate;
use serde_json::json;
use stock_select::engine::b2::{
    B2FactorProvider, CandidatePayloadFactorProvider, artifact_key_for_run,
    candidate_from_legacy_json,
};
use stock_select::engine::types::{FactorValue, SelectionCandidate};
use stock_select::model::Method;

#[test]
fn b2_candidate_adapter_preserves_screen_fields() {
    let value = json!({
        "code": "000001.SZ",
        "pick_date": "2026-05-25",
        "close": 10.5,
        "turnover_n": 1200.0,
        "signal": "B2"
    });
    let candidate =
        candidate_from_legacy_json(&value, NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()).unwrap();
    assert_eq!(candidate.method, Method::B2);
    assert_eq!(candidate.code, "000001.SZ");
    assert_eq!(candidate.close, Some(10.5));
    assert_eq!(candidate.signal.as_deref(), Some("B2"));
}

#[test]
fn b2_artifact_key_matches_intraday_and_eod_contract() {
    let date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    assert_eq!(artifact_key_for_run(date, false), "2026-05-25");
    assert_eq!(artifact_key_for_run(date, true), "2026-05-25.intraday");
}

#[test]
fn candidate_payload_factor_provider_extracts_screen_and_raw_factor_fields() {
    let value = json!({
        "code": "000001.SZ",
        "close": 10.5,
        "turnover_n": 1200.0,
        "signal": "B2",
        "env": "weak",
        "turnover_to_ma5_ratio": 1.8,
        "model_score": 99.0,
        "factors": {
            "close_to_zxdkx_pct": 1.25,
            "event_flag": true
        }
    });
    let candidate =
        candidate_from_legacy_json(&value, NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()).unwrap();

    let row = CandidatePayloadFactorProvider
        .factor_row(&candidate)
        .unwrap();

    assert_eq!(
        row.factors.get("close_to_zxdkx_pct"),
        Some(&FactorValue::Number(1.25))
    );
    assert_eq!(row.factors.get("close"), Some(&FactorValue::Number(10.5)));
    assert_eq!(
        row.factors.get("turnover_n"),
        Some(&FactorValue::Number(1200.0))
    );
    assert_eq!(
        row.factors.get("turnover_to_ma5_ratio"),
        Some(&FactorValue::Number(1.8))
    );
    assert_eq!(
        row.factors.get("signal"),
        Some(&FactorValue::Category("B2".to_string()))
    );
    assert_eq!(
        row.factors.get("env"),
        Some(&FactorValue::Category("weak".to_string()))
    );
    assert!(!row.factors.contains_key("model_score"));
    assert_eq!(row.diagnostics["factor_source"], "candidate_payload");
}

#[test]
fn candidate_payload_factor_provider_uses_candidate_method_factor_profile() {
    let candidate = SelectionCandidate {
        code: "000001.SZ".to_string(),
        name: None,
        method: Method::B3,
        pick_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
        close: Some(10.5),
        turnover_n: Some(1200.0),
        signal: Some("B3".to_string()),
        raw_payload: json!({"code": "000001.SZ", "signal": "B3"}),
    };

    let row = CandidatePayloadFactorProvider
        .factor_row(&candidate)
        .unwrap();

    assert_eq!(row.method, Method::B3);
    assert_eq!(row.diagnostics["factor_profile"], "b3");
    assert_eq!(
        row.diagnostics["factor_bundles"],
        serde_json::json!(["raw_common", "b3_semantic"])
    );
}

#[test]
fn candidate_payload_factor_provider_computes_history_raw_factors() {
    let value = json!({
        "code": "000001.SZ",
        "history": [
            {"open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0, "volume": 100.0, "turnover_n": 10.0, "turnover_rate": 1.0, "ma25": 96.0, "zxdkx": 90.0, "macd_hist": 0.5, "dif": 1.0, "dea": 0.5},
            {"open": 101.0, "high": 103.0, "low": 100.0, "close": 102.0, "volume": 110.0, "turnover_n": 11.0, "turnover_rate": 2.0, "ma25": 97.0, "zxdkx": 91.0, "macd_hist": 0.8, "dif": 1.2, "dea": 0.6},
            {"open": 103.0, "high": 105.0, "low": 102.0, "close": 104.0, "volume": 120.0, "turnover_n": 12.0, "turnover_rate": 3.0, "ma25": 98.0, "zxdkx": 92.0, "macd_hist": 1.0, "dif": 1.5, "dea": 0.7},
            {"open": 107.0, "high": 109.0, "low": 106.0, "close": 108.0, "volume": 130.0, "turnover_n": 13.0, "turnover_rate": 4.0, "ma25": 99.0, "zxdkx": 94.0, "macd_hist": 1.0, "dif": 2.0, "dea": 1.0},
            {"open": 109.0, "high": 115.0, "low": 105.0, "close": 110.0, "volume": 150.0, "turnover_n": 15.0, "turnover_rate": 10.0, "ma25": 100.0, "zxdkx": 95.0, "macd_hist": 2.0, "dif": 3.0, "dea": 1.0}
        ]
    });
    let candidate =
        candidate_from_legacy_json(&value, NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()).unwrap();

    let row = CandidatePayloadFactorProvider
        .factor_row(&candidate)
        .unwrap();

    assert_eq!(
        row.factors.get("close_to_ma25_pct"),
        Some(&FactorValue::Number(10.0))
    );
    assert_eq!(
        row.factors.get("close_to_zxdkx_pct"),
        Some(&FactorValue::Number(15.7895))
    );
    assert_eq!(
        row.factors.get("volume_to_ma5_ratio"),
        Some(&FactorValue::Number(1.2295))
    );
    assert_eq!(
        row.factors.get("turnover_to_ma5_ratio"),
        Some(&FactorValue::Number(2.5))
    );
    assert_eq!(
        row.factors.get("latest_bar_position_pct"),
        Some(&FactorValue::Number(50.0))
    );
    assert_eq!(
        row.factors.get("pct_chg_1d"),
        Some(&FactorValue::Number(1.8519))
    );
    assert_eq!(
        row.factors.get("macd_hist_to_close_pct"),
        Some(&FactorValue::Number(1.8182))
    );
    assert_eq!(
        row.factors.get("macd_hist_slope_3d_to_close_pct"),
        Some(&FactorValue::Number(1.0909))
    );
    assert_eq!(
        row.diagnostics
            .get("history_factor_count")
            .and_then(|value| value.as_u64()),
        Some(72)
    );
}

#[test]
fn candidate_payload_factor_provider_includes_legacy_semantic_factors() {
    let history = (0..130)
        .map(|offset| {
            let close = 100.0 + offset as f64 * 0.3;
            let trade_date =
                NaiveDate::from_ymd_opt(2026, 1, 1).unwrap() + chrono::Duration::days(offset);
            json!({
                "trade_date": trade_date.format("%Y-%m-%d").to_string(),
                "open": close - 0.2,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 1000.0 + offset as f64 * 5.0,
                "turnover_n": 2.0
            })
        })
        .collect::<Vec<_>>();
    let value = json!({"code": "000001.SZ", "env": "strong", "signal": "B2", "history": history});
    let candidate =
        candidate_from_legacy_json(&value, NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()).unwrap();

    let row = CandidatePayloadFactorProvider
        .factor_row(&candidate)
        .unwrap();

    assert_eq!(
        row.factors.get("signal_type"),
        Some(&FactorValue::Category("trend_start".to_string()))
    );
    assert_eq!(
        row.factors.get("daily_macd_phase_type"),
        Some(&FactorValue::Category("rising".to_string()))
    );
    assert_eq!(
        row.factors.get("weekly_macd_phase_type"),
        Some(&FactorValue::Category("rising".to_string()))
    );
    assert_eq!(
        row.factors.get("midline_state"),
        Some(&FactorValue::Category("above_hold".to_string()))
    );
    assert!(matches!(
        row.factors.get("daily_macd_wave_index"),
        Some(FactorValue::Number(value)) if *value >= 0.0
    ));
    assert!(matches!(
        row.factors.get("daily_macd_wave_stage"),
        Some(FactorValue::Category(value)) if !value.is_empty()
    ));
    assert!(matches!(
        row.factors.get("weekly_macd_wave_index"),
        Some(FactorValue::Number(value)) if *value >= 0.0
    ));
    assert!(matches!(
        row.factors.get("weekly_macd_wave_stage"),
        Some(FactorValue::Category(value)) if !value.is_empty()
    ));
    assert!(matches!(
        row.factors.get("weekly_daily_combo_type"),
        Some(FactorValue::Category(value)) if value.contains('|')
    ));
    assert!(matches!(
        row.factors.get("daily_rising_initial_flag"),
        Some(FactorValue::Bool(_)) | Some(FactorValue::Number(_))
    ));
    assert!(matches!(
        row.factors.get("macd_top_divergence_flag"),
        Some(FactorValue::Bool(_)) | Some(FactorValue::Number(_))
    ));
    assert!(matches!(
        row.factors.get("trend_structure"),
        Some(FactorValue::Number(value)) if *value >= 1.0
    ));
    assert!(matches!(
        row.factors.get("price_position"),
        Some(FactorValue::Number(value)) if *value >= 1.0
    ));
    assert!(matches!(
        row.factors.get("volume_behavior"),
        Some(FactorValue::Number(value)) if *value >= 1.0
    ));
    assert!(matches!(
        row.factors.get("previous_abnormal_move"),
        Some(FactorValue::Number(value)) if *value >= 1.0
    ));
    assert!(matches!(
        row.factors.get("macd_phase"),
        Some(FactorValue::Number(value)) if *value >= 1.0
    ));
    assert!(matches!(
        row.factors.get("price_vs_90d_mid"),
        Some(FactorValue::Number(_))
    ));
}

#[test]
fn candidate_payload_factor_provider_computes_120d_range_factors() {
    let history = (1..=120)
        .map(|day| {
            let close = 100.0 + day as f64;
            json!({
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 2.0,
                "close": close,
                "volume": 1000.0 + day as f64,
                "turnover_n": 2.0 + day as f64 / 100.0,
                "ma25": close - 10.0,
                "zxdkx": close - 20.0,
                "macd_hist": 1.0,
                "dif": 2.0,
                "dea": 1.0
            })
        })
        .collect::<Vec<_>>();
    let value = json!({"code": "000001.SZ", "history": history});
    let candidate =
        candidate_from_legacy_json(&value, NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()).unwrap();

    let row = CandidatePayloadFactorProvider
        .factor_row(&candidate)
        .unwrap();

    assert_eq!(
        row.factors.get("box_position_120d_pct"),
        Some(&FactorValue::Number(99.1803))
    );
    assert_eq!(
        row.factors.get("close_to_120d_max_pct"),
        Some(&FactorValue::Number(-0.4525))
    );
    assert_eq!(
        row.factors.get("close_to_120d_min_pct"),
        Some(&FactorValue::Number(122.2222))
    );
    assert_eq!(
        row.factors.get("close_to_120d_range_center_pct"),
        Some(&FactorValue::Number(37.5))
    );
    assert_eq!(
        row.factors.get("range_width_120d_pct"),
        Some(&FactorValue::Number(55.4545))
    );
    assert_eq!(
        row.factors.get("close_to_20d_max_close_pct"),
        Some(&FactorValue::Number(0.0))
    );
}

#[test]
fn candidate_payload_factor_provider_computes_b2_rdagent_rank_factors() {
    let history = (1..=150)
        .map(|day| {
            let close = 100.0 + day as f64;
            let open = if day == 149 {
                close + 1.0
            } else if day == 150 {
                close - 5.0
            } else {
                close - 0.5
            };
            let volume = if day == 150 { 2600.0 } else { 1000.0 + day as f64 };
            json!({
                "trade_date": (NaiveDate::from_ymd_opt(2026, 1, 1).unwrap() + chrono::Duration::days(day - 1)).format("%Y-%m-%d").to_string(),
                "open": open,
                "high": close + 10.0,
                "low": close - 5.0,
                "close": close,
                "volume": volume,
                "turnover_n": 2.0 + day as f64 / 100.0,
                "turnover_rate": 1.0 + day as f64 / 100.0,
                "ma25": close - 10.0,
                "dif": 2.0,
                "dea": day as f64,
                "macd_hist": day as f64 / 10.0,
                "d": 45.0,
                "j": 30.0 + day as f64 / 10.0
            })
        })
        .collect::<Vec<_>>();
    let value = json!({"code": "000001.SZ", "signal": "B2", "history": history});
    let candidate =
        candidate_from_legacy_json(&value, NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()).unwrap();

    let row = CandidatePayloadFactorProvider
        .factor_row(&candidate)
        .unwrap();

    for key in [
        "D",
        "close_to_lt_r_pct",
        "lt_r_to_ma60_pct",
        "hl90_position",
        "hl90_range_pct",
        "close_to_hl90_mid_pct",
        "bar_close_position",
        "upper_shadow_pct",
        "weekly_dea_pctile",
        "weekly_macd_hist",
        "monthly_dea_pctile",
        "monthly_macd_hist",
        "b2_bullish_engulf_prev_bearish_flag",
        "b2_volume_bullish_engulf_prev_bearish_flag",
        "b2_bullish_engulf_volume_ratio",
    ] {
        assert!(row.factors.contains_key(key), "missing {key}");
    }
    assert_eq!(row.factors.get("D"), Some(&FactorValue::Number(45.0)));
    assert_eq!(
        row.factors.get("hl90_position"),
        Some(&FactorValue::Number(0.9038))
    );
    assert_eq!(
        row.factors.get("hl90_range_pct"),
        Some(&FactorValue::Number(50.0))
    );
    assert_eq!(
        row.factors.get("bar_close_position"),
        Some(&FactorValue::Number(0.3333))
    );
    assert_eq!(
        row.factors.get("upper_shadow_pct"),
        Some(&FactorValue::Number(4.0))
    );
    assert_eq!(
        row.factors.get("b2_bullish_engulf_prev_bearish_flag"),
        Some(&FactorValue::Bool(true))
    );
    assert_eq!(
        row.factors
            .get("b2_volume_bullish_engulf_prev_bearish_flag"),
        Some(&FactorValue::Bool(true))
    );
    assert!(matches!(
        row.factors.get("b2_bullish_engulf_volume_ratio"),
        Some(FactorValue::Number(value)) if *value > 2.0
    ));
}

#[test]
fn candidate_payload_factor_provider_derives_ma_and_zx_lines_from_history_close() {
    let history = (1..=130)
        .map(|day| {
            let close = 100.0 + day as f64;
            json!({
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 2.0,
                "close": close,
                "volume": 1000.0 + day as f64 * 10.0,
                "turnover_n": 2.0 + day as f64 / 100.0
            })
        })
        .collect::<Vec<_>>();
    let value = json!({"code": "000001.SZ", "history": history});
    let candidate =
        candidate_from_legacy_json(&value, NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()).unwrap();

    let row = CandidatePayloadFactorProvider
        .factor_row(&candidate)
        .unwrap();

    assert_eq!(
        row.factors.get("close_to_ma25_pct"),
        Some(&FactorValue::Number(5.5046))
    );
    assert_eq!(
        row.factors.get("close_to_zxdkx_pct"),
        Some(&FactorValue::Number(12.8142))
    );
    assert_eq!(
        row.factors.get("ma25_to_zxdkx_pct"),
        Some(&FactorValue::Number(6.9283))
    );
    assert_eq!(
        row.factors.get("ma25_slope_5d_pct"),
        Some(&FactorValue::Number(2.3474))
    );
    assert_eq!(
        row.factors.get("zxdkx_slope_5d_pct"),
        Some(&FactorValue::Number(2.5141))
    );
    assert_eq!(
        row.factors.get("zxdq_slope_5d_pct"),
        Some(&FactorValue::Number(2.3148))
    );
    assert_eq!(
        row.factors.get("low_to_ma25_pct"),
        Some(&FactorValue::Number(4.5872))
    );
    assert_eq!(
        row.factors.get("volume_to_ma5_ratio"),
        Some(&FactorValue::Number(1.0088))
    );
    assert_eq!(
        row.factors.get("volume_ma5_to_ma20_ratio"),
        Some(&FactorValue::Number(1.034))
    );
    assert_eq!(
        row.factors.get("range_width_120d_pct"),
        Some(&FactorValue::Number(53.0435))
    );
    assert_eq!(
        row.factors.get("macd_dif_to_close_pct"),
        Some(&FactorValue::Number(3.0432))
    );
    assert_eq!(
        row.factors.get("macd_dea_to_close_pct"),
        Some(&FactorValue::Number(3.0431))
    );
    assert_eq!(
        row.factors.get("macd_hist_to_close_pct"),
        Some(&FactorValue::Number(0.0001))
    );
    assert_eq!(
        row.factors.get("macd_hist_positive_flag"),
        Some(&FactorValue::Bool(true))
    );
}

#[test]
fn candidate_payload_factor_provider_computes_range_compression_factors() {
    let history = (1..=40)
        .map(|day| {
            let close = 100.0 + day as f64;
            json!({
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 2.0,
                "close": close,
                "volume": 1000.0,
                "turnover_n": 2.0
            })
        })
        .collect::<Vec<_>>();
    let value = json!({"code": "000001.SZ", "history": history});
    let candidate =
        candidate_from_legacy_json(&value, NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()).unwrap();

    let row = CandidatePayloadFactorProvider
        .factor_row(&candidate)
        .unwrap();

    assert_eq!(
        row.factors.get("range_compression_20d"),
        Some(&FactorValue::Number(15.7143))
    );
    assert_eq!(
        row.factors.get("range_compression_40d"),
        Some(&FactorValue::Number(30.0))
    );
}

#[test]
fn candidate_payload_factor_provider_computes_abnormal_volume_event_factors() {
    let history = (1..=25)
        .map(|day| {
            let close = 100.0 + day as f64;
            let volume = if day == 20 { 500.0 } else { 100.0 };
            json!({
                "open": close - 1.0,
                "high": close + 1.0,
                "low": close - 2.0,
                "close": close,
                "volume": volume,
                "turnover_n": 2.0
            })
        })
        .collect::<Vec<_>>();
    let value = json!({"code": "000001.SZ", "history": history});
    let candidate =
        candidate_from_legacy_json(&value, NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()).unwrap();

    let row = CandidatePayloadFactorProvider
        .factor_row(&candidate)
        .unwrap();

    assert_eq!(
        row.factors.get("abnormal_volume_event_days_ago"),
        Some(&FactorValue::Number(5.0))
    );
    assert_eq!(
        row.factors.get("abnormal_volume_to_ma20_ratio"),
        Some(&FactorValue::Number(4.1667))
    );
    assert_eq!(
        row.factors.get("abnormal_event_body_pct"),
        Some(&FactorValue::Number(0.8403))
    );
    assert_eq!(
        row.factors.get("abnormal_event_price_to_current_pct"),
        Some(&FactorValue::Number(-4.0))
    );
    assert_eq!(
        row.factors.get("post_abnormal_min_body_to_event_price_pct"),
        Some(&FactorValue::Number(0.0))
    );
    assert_eq!(
        row.factors.get("post_abnormal_drawdown_pct"),
        Some(&FactorValue::Number(0.0))
    );
    assert_eq!(
        row.factors.get("abnormal_redundant_position_pct"),
        Some(&FactorValue::Number(11.1111))
    );
}
