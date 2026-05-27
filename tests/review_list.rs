use std::collections::BTreeMap;
use std::fs;

use chrono::NaiveDate;
use serde_json::{Value, json};
use stock_select_rs::cli::{ReviewListArgs, build_review_list_lines_for_test, run_review_list};
use stock_select_rs::model::Method;

fn review(code: &str, score: f64, verdict: &str, signal: Option<&str>, signal_type: &str) -> Value {
    let mut value = json!({
        "code": code,
        "total_score": score,
        "verdict": verdict,
        "signal_type": signal_type,
    });
    if let Some(signal) = signal {
        value
            .as_object_mut()
            .unwrap()
            .insert("signal".to_string(), json!(signal));
    }
    value
}

#[test]
fn review_list_lines_keep_summary_order_and_include_display_fields() {
    let reviews = vec![
        review("300221.SZ", 4.04, "WATCH", Some("B3"), "trend_start"),
        review("603308.SH", 3.59, "WATCH", None, "rebound"),
    ];
    let mut names = BTreeMap::new();
    names.insert("300221.SZ".to_string(), "银禧科技".to_string());
    names.insert("603308.SH".to_string(), "应流股份".to_string());

    let lines = build_review_list_lines_for_test(&reviews, &names);

    assert_eq!(
        lines,
        vec![
            "300221.SZ\t银禧科技\tB3\ttrend_start",
            "603308.SH\t应流股份\t-\trebound",
        ]
    );
}

#[test]
fn review_list_reads_requested_verdict_section_from_summary() {
    let temp = tempfile::tempdir().unwrap();
    let review_dir = temp.path().join("reviews/2026-05-25.b2");
    fs::create_dir_all(&review_dir).unwrap();
    fs::write(
        review_dir.join("summary.json"),
        serde_json::to_vec_pretty(&json!({
            "pick_date": "2026-05-25",
            "method": "b2",
            "recommendations": [
                review("000001.SZ", 4.2, "PASS", Some("B2"), "trend_start")
            ],
            "excluded": [
                review("300221.SZ", 4.04, "WATCH", Some("B3"), "trend_start"),
                review("603308.SH", 3.59, "WATCH", None, "rebound"),
                review("000002.SZ", 2.1, "FAIL", Some("B5"), "distribution_risk")
            ],
            "failures": []
        }))
        .unwrap(),
    )
    .unwrap();

    let output = run_review_list(
        ReviewListArgs {
            method: Method::B2,
            pick_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
            intraday: false,
            runtime_root: Some(temp.path().to_path_buf()),
            dsn: None,
            verdict: "WATCH".to_string(),
        },
        |_codes| Ok(BTreeMap::new()),
    )
    .unwrap();

    assert_eq!(
        output,
        "300221.SZ\t-\tB3\ttrend_start\n603308.SH\t-\t-\trebound"
    );
}

#[test]
fn review_list_reads_intraday_date_scoped_summary_when_requested() {
    let temp = tempfile::tempdir().unwrap();
    let review_dir = temp.path().join("reviews/2026-05-25.intraday.b2");
    fs::create_dir_all(&review_dir).unwrap();
    fs::write(
        review_dir.join("summary.json"),
        serde_json::to_vec_pretty(&json!({
            "pick_date": "2026-05-25",
            "method": "b2",
            "recommendations": [
                review("300221.SZ", 4.04, "WATCH", Some("B3"), "trend_start")
            ],
            "excluded": [],
            "failures": []
        }))
        .unwrap(),
    )
    .unwrap();

    let output = run_review_list(
        ReviewListArgs {
            method: Method::B2,
            pick_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
            intraday: true,
            runtime_root: Some(temp.path().to_path_buf()),
            dsn: None,
            verdict: "WATCH".to_string(),
        },
        |_codes| Ok(BTreeMap::new()),
    )
    .unwrap();

    assert_eq!(output, "300221.SZ\t-\tB3\ttrend_start");
}
