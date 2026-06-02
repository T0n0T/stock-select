use std::fs;

use chrono::NaiveDate;
use serde_json::{Value, json};
use stock_select_rs::cache::write_prepared_cache;
use stock_select_rs::model::{Method, PreparedRow};
use stock_select_rs::native_review::{NativeReviewArgs, run_native_review};

fn prepared_row(code: &str, day: u32) -> PreparedRow {
    PreparedRow {
        ts_code: code.to_string(),
        trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
        open: 10.0,
        high: 11.0,
        low: 9.0,
        close: 10.5,
        volume: 100.0,
        turnover_n: 1000.0,
        k: 50.0,
        d: 50.0,
        j: 50.0,
        zxdq: Some(10.0),
        zxdkx: Some(9.5),
        dif: 0.1,
        dea: 0.0,
        macd_hist: 0.1,
        ma25: Some(10.0),
        ma60: Some(9.0),
        ma144: Some(8.0),
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
fn native_review_overwrites_baseline_without_merging_existing_llm_results() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let code = "000001.SZ";
    let rows = (1..=25)
        .map(|day| prepared_row(code, day))
        .collect::<Vec<_>>();
    write_prepared_cache(
        temp.path(),
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();

    fs::create_dir_all(temp.path().join("candidates")).unwrap();
    fs::write(
        temp.path().join("candidates/2026-05-25.b2.json"),
        serde_json::to_vec_pretty(&json!({
            "method": "b2",
            "pick_date": "2026-05-25",
            "pool_source": "turnover-top",
            "candidates": [{
                "code": code,
                "pick_date": "2026-05-25",
                "close": 10.5,
                "turnover_n": 1000.0,
                "signal": "B2"
            }],
            "stats": {}
        }))
        .unwrap(),
    )
    .unwrap();

    let llm_dir = temp.path().join("reviews/2026-05-25.b2/llm_review_results");
    fs::create_dir_all(&llm_dir).unwrap();
    fs::write(
        llm_dir.join(format!("{code}.json")),
        serde_json::to_vec_pretty(&json!({
            "trend_reasoning": "trend ok",
            "position_reasoning": "position ok",
            "volume_reasoning": "volume ok",
            "abnormal_move_reasoning": "risk ok",
            "macd_reasoning": "macd ok",
            "signal_reasoning": "signal ok",
            "llm_scores": {
                "trend_structure": 4.0,
                "price_position": 4.0,
                "volume_behavior": 3.0,
                "previous_abnormal_move": 5.0,
                "macd_phase": 3.0
            },
            "llm_total_score": 3.3,
            "signal_type": "rebound",
            "llm_verdict": "WATCH",
            "comment": "stale llm result"
        }))
        .unwrap(),
    )
    .unwrap();

    run_native_review(NativeReviewArgs {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        environment_state: Some("weak".to_string()),
        environment_reason: Some("manual test".to_string()),
        llm_min_baseline_score: None,
        llm_review_limit: Some(5),
        require_chart_files: false,
        artifact_key: None,
        intraday: false,
    })
    .unwrap();

    let review: Value = serde_json::from_slice(
        &fs::read(temp.path().join("reviews/2026-05-25.b2/000001.SZ.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(review["review_mode"], "baseline_local");
    assert!(review.get("llm_review").is_none_or(Value::is_null));
    assert!(review.get("llm_score").is_none());
    assert_ne!(review["comment"], "stale llm result");
    let baseline = review["baseline_review"].as_object().unwrap();
    for key in [
        "daily_macd_phase_type",
        "daily_macd_wave_index",
        "daily_macd_wave_stage",
        "daily_macd_rising_or_falling",
        "daily_macd_bottom_divergence",
        "daily_macd_top_divergence",
        "weekly_macd_phase_type",
        "weekly_macd_wave_index",
        "weekly_macd_wave_stage",
        "weekly_macd_bottom_divergence",
        "weekly_macd_top_divergence",
        "weekly_daily_combo_type",
    ] {
        assert!(
            baseline.contains_key(key),
            "missing b2 MACD diagnostic field {key}"
        );
    }
}

#[test]
fn native_review_supports_dribull_without_environment_profile() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = NaiveDate::from_ymd_opt(2025, 5, 24).unwrap();
    let code = "000001.SZ";
    let rows = (1..=25)
        .map(|day| prepared_row(code, day))
        .collect::<Vec<_>>();
    write_prepared_cache(
        temp.path(),
        Method::Dribull,
        pick_date,
        start_date,
        pick_date,
        &rows,
    )
    .unwrap();

    fs::create_dir_all(temp.path().join("candidates")).unwrap();
    fs::write(
        temp.path().join("candidates/2026-05-25.dribull.json"),
        serde_json::to_vec_pretty(&json!({
            "method": "dribull",
            "pick_date": "2026-05-25",
            "pool_source": "turnover-top",
            "candidates": [{
                "code": code,
                "pick_date": "2026-05-25",
                "close": 10.5,
                "turnover_n": 1000.0
            }],
            "stats": {}
        }))
        .unwrap(),
    )
    .unwrap();

    let summary_path = run_native_review(NativeReviewArgs {
        method: Method::Dribull,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        environment_state: None,
        environment_reason: None,
        llm_min_baseline_score: None,
        llm_review_limit: Some(1),
        require_chart_files: false,
        artifact_key: None,
        intraday: false,
    })
    .unwrap();

    assert_eq!(
        summary_path,
        temp.path().join("reviews/2026-05-25.dribull/summary.json")
    );
    let review: Value = serde_json::from_slice(
        &fs::read(
            temp.path()
                .join("reviews/2026-05-25.dribull/000001.SZ.json"),
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(review["baseline_review"]["review_type"], "baseline");
    assert!(review["comment"].as_str().unwrap().contains("dribull"));
}
