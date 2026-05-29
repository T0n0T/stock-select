use std::fs;

use chrono::NaiveDate;
use serde_json::json;
use stock_select_rs::model::Method;
use stock_select_rs::watch_pool::{RecordWatchArgs, load_watch_pool, record_watch_from_summary};

fn date(value: &str) -> NaiveDate {
    NaiveDate::parse_from_str(value, "%Y-%m-%d").unwrap()
}

fn trade_dates() -> Vec<NaiveDate> {
    [
        "2026-04-01",
        "2026-04-02",
        "2026-04-03",
        "2026-04-07",
        "2026-04-08",
        "2026-04-09",
        "2026-04-10",
        "2026-04-13",
        "2026-04-14",
        "2026-04-15",
        "2026-04-16",
        "2026-04-17",
        "2026-04-20",
        "2026-04-21",
        "2026-04-22",
        "2026-04-23",
        "2026-04-24",
    ]
    .into_iter()
    .map(date)
    .collect()
}

#[test]
fn record_watch_imports_pass_and_watch_rows() {
    let temp = tempfile::tempdir().unwrap();
    let review_dir = temp.path().join("reviews/2026-04-24.b2");
    fs::create_dir_all(&review_dir).unwrap();
    fs::write(
        review_dir.join("summary.json"),
        serde_json::to_vec_pretty(&json!({
            "pick_date": "2026-04-24",
            "method": "b2",
            "recommendations": [
                {"code": "AAA.SZ", "verdict": "PASS", "total_score": 4.8, "signal_type": "trend_start", "comment": "go"}
            ],
            "excluded": [
                {"code": "BBB.SZ", "verdict": "WATCH", "total_score": 3.8, "signal_type": "rebound", "comment": "wait"},
                {"code": "CCC.SZ", "verdict": "FAIL", "total_score": 2.1, "signal_type": "risk", "comment": "skip"}
            ],
            "failures": []
        }))
        .unwrap(),
    )
    .unwrap();

    let result = record_watch_from_summary(RecordWatchArgs {
        method: Method::B2,
        pick_date: date("2026-04-24"),
        runtime_root: temp.path().to_path_buf(),
        summary_path: review_dir.join("summary.json"),
        trade_dates: trade_dates(),
        window_trading_days: 15,
        recorded_at: "2026-04-24T16:21:22+08:00".to_string(),
    })
    .unwrap();

    let rows = load_watch_pool(&result.path).unwrap();
    assert_eq!(result.imported, 2);
    assert_eq!(result.refreshed, 0);
    assert_eq!(result.trimmed, 0);
    assert_eq!(
        rows.iter().map(|row| row.code.as_str()).collect::<Vec<_>>(),
        vec!["AAA.SZ", "BBB.SZ"]
    );
    assert!(
        rows.iter()
            .all(|row| row.recorded_at == "2026-04-24T16:21:22+08:00")
    );
}

#[test]
fn record_watch_refreshes_existing_method_code_and_trims_old_rows() {
    let temp = tempfile::tempdir().unwrap();
    let review_dir = temp.path().join("reviews/2026-04-24.b2");
    fs::create_dir_all(&review_dir).unwrap();
    fs::write(
        review_dir.join("summary.json"),
        serde_json::to_vec_pretty(&json!({
            "pick_date": "2026-04-24",
            "method": "b2",
            "recommendations": [
                {"code": "AAA.SZ", "verdict": "PASS", "total_score": 4.9, "signal_type": "trend_start", "comment": "selected again"}
            ],
            "excluded": [],
            "failures": []
        }))
        .unwrap(),
    )
    .unwrap();
    fs::write(
        temp.path().join("watch_pool.csv"),
        "\
method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at\n\
b2,2026-04-10,AAA.SZ,WATCH,3.7,rebound,old selection,2026-04-10T16:00:00+08:00\n\
b2,2026-04-01,OLD.SZ,WATCH,3.1,rebound,old row,2026-04-01T16:00:00+08:00\n\
b1,2026-04-10,AAA.SZ,PASS,4.2,trend_start,other method,2026-04-10T16:00:00+08:00\n",
    )
    .unwrap();

    let result = record_watch_from_summary(RecordWatchArgs {
        method: Method::B2,
        pick_date: date("2026-04-24"),
        runtime_root: temp.path().to_path_buf(),
        summary_path: review_dir.join("summary.json"),
        trade_dates: trade_dates(),
        window_trading_days: 15,
        recorded_at: "2026-04-24T16:21:22+08:00".to_string(),
    })
    .unwrap();

    let rows = load_watch_pool(&result.path).unwrap();
    assert_eq!(result.imported, 1);
    assert_eq!(result.refreshed, 1);
    assert_eq!(result.trimmed, 1);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0].method, "b2");
    assert_eq!(rows[0].pick_date, date("2026-04-24"));
    assert_eq!(rows[0].code, "AAA.SZ");
    assert_eq!(rows[0].verdict, "PASS");
    assert_eq!(rows[0].comment, "selected again");
    assert_eq!(rows[1].method, "b1");
    assert_eq!(rows[1].code, "AAA.SZ");
}
