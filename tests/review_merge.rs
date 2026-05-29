use std::fs;

use chrono::NaiveDate;
use serde_json::{Value, json};
use stock_select_rs::model::Method;
use stock_select_rs::native_review::{NativeReviewMergeArgs, run_native_review_merge};

fn baseline_review(code: &str, score: f64, verdict: &str) -> Value {
    json!({
        "code": code,
        "pick_date": "2026-05-25",
        "chart_path": format!("/tmp/{code}_day.png"),
        "review_mode": "baseline_local",
        "llm_review": null,
        "baseline_review": {
            "trend_structure": 4.0,
            "price_position": 4.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 5.0,
            "macd_phase": 3.0,
            "raw_total_score": score,
            "total_score": score,
            "signal_type": "trend_start",
            "verdict": verdict,
            "comment": "baseline"
        },
        "total_score": score,
        "signal_type": "trend_start",
        "verdict": verdict,
        "comment": "baseline"
    })
}

fn llm_review(score: f64, verdict: &str) -> Value {
    json!({
        "trend_reasoning": "trend ok",
        "position_reasoning": "position ok",
        "volume_reasoning": "volume ok",
        "abnormal_move_reasoning": "risk ok",
        "macd_reasoning": "macd ok",
        "signal_reasoning": "signal ok",
        "scores": {
            "trend_structure": 4.0,
            "price_position": 4.0,
            "volume_behavior": 3.0,
            "previous_abnormal_move": 5.0,
            "macd_phase": 3.0
        },
        "total_score": score,
        "signal_type": "rebound",
        "verdict": verdict,
        "comment": "llm merged"
    })
}

fn legacy_llm_review(score: f64, verdict: &str) -> Value {
    json!({
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
        "llm_total_score": score,
        "signal_type": "rebound",
        "llm_verdict": verdict,
        "comment": "legacy llm merged"
    })
}

#[test]
fn review_merge_merges_valid_llm_results_and_rewrites_summary() {
    let temp = tempfile::tempdir().unwrap();
    let review_dir = temp.path().join("reviews/2026-05-25.b2");
    let llm_dir = review_dir.join("llm_review_results");
    fs::create_dir_all(&llm_dir).unwrap();
    fs::write(
        review_dir.join("000001.SZ.json"),
        serde_json::to_vec_pretty(&baseline_review("000001.SZ", 3.59, "PASS")).unwrap(),
    )
    .unwrap();
    fs::write(
        review_dir.join("000002.SZ.json"),
        serde_json::to_vec_pretty(&baseline_review("000002.SZ", 2.5, "FAIL")).unwrap(),
    )
    .unwrap();
    fs::write(
        llm_dir.join("000001.SZ.json"),
        serde_json::to_vec_pretty(&llm_review(3.3, "WATCH")).unwrap(),
    )
    .unwrap();

    let summary_path = run_native_review_merge(NativeReviewMergeArgs {
        method: Method::B2,
        pick_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
        runtime_root: temp.path().to_path_buf(),
        codes: Some(vec!["000001.SZ".to_string()]),
    })
    .unwrap();

    assert_eq!(summary_path, review_dir.join("summary.json"));
    let merged: Value =
        serde_json::from_slice(&fs::read(review_dir.join("000001.SZ.json")).unwrap()).unwrap();
    assert_eq!(merged["review_mode"], "merged");
    assert_eq!(merged["llm_score"], 3.3);
    assert_eq!(merged["weighted_review_score"], 3.42);
    assert_eq!(merged["final_score"], 3.59);
    assert_eq!(merged["total_score"], 3.59);
    assert_eq!(merged["verdict"], "WATCH");
    assert_eq!(merged["signal_type"], "rebound");
    assert_eq!(merged["comment"], "llm merged");

    let untouched: Value =
        serde_json::from_slice(&fs::read(review_dir.join("000002.SZ.json")).unwrap()).unwrap();
    assert_eq!(untouched["review_mode"], "baseline_local");

    let summary: Value = serde_json::from_slice(&fs::read(summary_path).unwrap()).unwrap();
    assert_eq!(summary["reviewed_count"], 2);
    assert!(summary["recommendations"].as_array().unwrap().is_empty());
    assert_eq!(summary["excluded"].as_array().unwrap().len(), 2);
    assert!(summary["failures"].as_array().unwrap().is_empty());
}

#[test]
fn review_merge_accepts_legacy_llm_result_field_names() {
    let temp = tempfile::tempdir().unwrap();
    let review_dir = temp.path().join("reviews/2026-05-25.b2");
    let llm_dir = review_dir.join("llm_review_results");
    fs::create_dir_all(&llm_dir).unwrap();
    fs::write(
        review_dir.join("000001.SZ.json"),
        serde_json::to_vec_pretty(&baseline_review("000001.SZ", 3.59, "PASS")).unwrap(),
    )
    .unwrap();
    fs::write(
        llm_dir.join("000001.SZ.json"),
        serde_json::to_vec_pretty(&legacy_llm_review(3.3, "WATCH")).unwrap(),
    )
    .unwrap();

    run_native_review_merge(NativeReviewMergeArgs {
        method: Method::B2,
        pick_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
        runtime_root: temp.path().to_path_buf(),
        codes: Some(vec!["000001.SZ".to_string()]),
    })
    .unwrap();

    let merged: Value =
        serde_json::from_slice(&fs::read(review_dir.join("000001.SZ.json")).unwrap()).unwrap();
    assert_eq!(merged["review_mode"], "merged");
    assert_eq!(merged["llm_score"], 3.3);
    assert_eq!(merged["llm_review"]["scores"]["volume_behavior"], 3.0);
    assert_eq!(merged["llm_review"]["total_score"], 3.3);
    assert_eq!(merged["llm_review"]["verdict"], "WATCH");
    assert_eq!(merged["comment"], "legacy llm merged");
}

#[test]
fn review_merge_records_missing_or_invalid_llm_results_as_failures() {
    let temp = tempfile::tempdir().unwrap();
    let review_dir = temp.path().join("reviews/2026-05-25.b1");
    let llm_dir = review_dir.join("llm_review_results");
    fs::create_dir_all(&llm_dir).unwrap();
    fs::write(
        review_dir.join("000001.SZ.json"),
        serde_json::to_vec_pretty(&baseline_review("000001.SZ", 4.2, "PASS")).unwrap(),
    )
    .unwrap();
    fs::write(
        review_dir.join("000002.SZ.json"),
        serde_json::to_vec_pretty(&baseline_review("000002.SZ", 3.1, "FAIL")).unwrap(),
    )
    .unwrap();
    fs::write(
        llm_dir.join("000001.SZ.json"),
        serde_json::to_vec_pretty(&json!({"scores": {}})).unwrap(),
    )
    .unwrap();

    let summary_path = run_native_review_merge(NativeReviewMergeArgs {
        method: Method::B1,
        pick_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
        runtime_root: temp.path().to_path_buf(),
        codes: None,
    })
    .unwrap();

    let summary: Value = serde_json::from_slice(&fs::read(summary_path).unwrap()).unwrap();
    let failures = summary["failures"].as_array().unwrap();
    assert_eq!(failures.len(), 2);
    assert_eq!(failures[0]["code"], "000001.SZ");
    assert!(
        failures[0]["reason"]
            .as_str()
            .unwrap()
            .contains("missing or empty field")
    );
    assert_eq!(failures[1]["code"], "000002.SZ");
    assert!(
        failures[1]["reason"]
            .as_str()
            .unwrap()
            .contains("LLM review result not found")
    );

    let baseline: Value =
        serde_json::from_slice(&fs::read(review_dir.join("000001.SZ.json")).unwrap()).unwrap();
    assert_eq!(baseline["review_mode"], "baseline_local");
}
