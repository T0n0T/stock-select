use chrono::NaiveDate;
use std::sync::{Arc, Barrier};
use std::thread;
use stock_select::engine::types::DisplayRow;
use stock_select::model::Method;
use stock_select::record::update_run_record;

fn display_row(code: &str, rank: usize) -> DisplayRow {
    DisplayRow {
        code: code.to_string(),
        name: Some(format!("name-{rank}")),
        industry: None,
        model_rank: Some(rank),
        model_score: Some(1.0 / rank as f64),
        llm_action: None,
        llm_risk_flags: Vec::new(),
        llm_comment: None,
    }
}

fn read_record_csv(path: &std::path::Path) -> Vec<Vec<String>> {
    std::fs::read_to_string(path)
        .unwrap()
        .lines()
        .skip(1)
        .map(|line| line.split(',').map(str::to_string).collect())
        .collect()
}

#[test]
fn run_record_writes_top_thirty_and_replaces_same_code_records() {
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(
        temp.path().join("record.csv"),
        [
            "code,name,method,selected_date,model_rank,model_score",
            "000001.SZ,old-name,lsh,2026-06-04,12,0.2",
            "000002.SZ,same-run-old-name,b2,2026-06-05,12,0.2",
        ]
        .join("\n")
            + "\n",
    )
    .unwrap();
    let rows = (1..=31)
        .map(|rank| display_row(&format!("{rank:06}.SZ"), rank))
        .collect::<Vec<_>>();

    let count = update_run_record(
        temp.path(),
        Method::B2,
        NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
        &rows,
        10,
        30,
    )
    .unwrap();

    assert_eq!(count, 30);
    let records = read_record_csv(&temp.path().join("record.csv"));
    assert_eq!(records.len(), 30);
    assert!(records.iter().any(|row| {
        row[0] == "000001.SZ"
            && row[1] == "name-1"
            && row[2] == "b2"
            && row[3] == "2026-06-05"
            && row[4] == "1"
    }));
    assert!(records.iter().any(|row| {
        row[0] == "000002.SZ"
            && row[1] == "name-2"
            && row[2] == "b2"
            && row[3] == "2026-06-05"
            && row[4] == "2"
    }));
    assert_eq!(
        records.iter().filter(|row| row[0] == "000001.SZ").count(),
        1
    );
    assert!(!records.iter().any(|row| row[1] == "same-run-old-name"));
    assert!(!records.iter().any(|row| row[1] == "old-name"));
    assert!(!records.iter().any(|row| row[0] == "000031.SZ"));
}

#[test]
fn run_record_prunes_old_records_by_recent_selected_dates() {
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(
        temp.path().join("record.csv"),
        [
            "code,name,method,selected_date,model_rank,model_score",
            "000001.SZ,name-1,b2,2026-06-01,1,0.9",
            "000002.SZ,name-2,b2,2026-06-02,2,0.8",
            "000003.SZ,name-3,b2,2026-06-03,3,0.7",
            "000004.SZ,name-4,b2,2026-06-04,4,0.6",
        ]
        .join("\n")
            + "\n",
    )
    .unwrap();

    let count = update_run_record(
        temp.path(),
        Method::B2,
        NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
        &[display_row("000005.SZ", 1)],
        3,
        30,
    )
    .unwrap();

    assert_eq!(count, 3);
    let records = read_record_csv(&temp.path().join("record.csv"));
    let codes = records
        .iter()
        .map(|row| row[0].as_str())
        .collect::<Vec<_>>();
    assert_eq!(codes, vec!["000005.SZ", "000004.SZ", "000003.SZ"]);
}

#[test]
fn run_record_backfill_does_not_drop_newer_selected_dates() {
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(
        temp.path().join("record.csv"),
        [
            "code,name,method,selected_date,model_rank,model_score",
            "000010.SZ,name-10,b2,2026-06-10,1,0.9",
            "000011.SZ,name-11,b2,2026-06-11,1,0.8",
        ]
        .join("\n")
            + "\n",
    )
    .unwrap();

    let count = update_run_record(
        temp.path(),
        Method::B2,
        NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
        &[display_row("000005.SZ", 1)],
        3,
        30,
    )
    .unwrap();

    assert_eq!(count, 3);
    let records = read_record_csv(&temp.path().join("record.csv"));
    let codes = records
        .iter()
        .map(|row| row[0].as_str())
        .collect::<Vec<_>>();
    assert_eq!(codes, vec!["000011.SZ", "000010.SZ", "000005.SZ"]);
}

#[test]
fn run_record_backfill_still_respects_window_with_newer_dates() {
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(
        temp.path().join("record.csv"),
        [
            "code,name,method,selected_date,model_rank,model_score",
            "000009.SZ,name-9,b2,2026-06-09,1,0.9",
            "000010.SZ,name-10,b2,2026-06-10,1,0.8",
            "000011.SZ,name-11,b2,2026-06-11,1,0.7",
        ]
        .join("\n")
            + "\n",
    )
    .unwrap();

    let count = update_run_record(
        temp.path(),
        Method::B2,
        NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
        &[display_row("000005.SZ", 1)],
        3,
        30,
    )
    .unwrap();

    assert_eq!(count, 3);
    let records = read_record_csv(&temp.path().join("record.csv"));
    let codes = records
        .iter()
        .map(|row| row[0].as_str())
        .collect::<Vec<_>>();
    assert_eq!(codes, vec!["000011.SZ", "000010.SZ", "000009.SZ"]);
}

#[test]
fn run_record_keeps_one_row_per_code_and_replaces_with_newer_selection() {
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(
        temp.path().join("record.csv"),
        [
            "code,name,method,selected_date,model_rank,model_score",
            "000001.SZ,name-old,b2,2026-06-04,1,0.9",
            "000001.SZ,name-lsh,lsh,2026-06-04,1,0.8",
        ]
        .join("\n")
            + "\n",
    )
    .unwrap();

    let count = update_run_record(
        temp.path(),
        Method::B2,
        NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
        &[display_row("000001.SZ", 1)],
        10,
        30,
    )
    .unwrap();

    assert_eq!(count, 1);
    let records = read_record_csv(&temp.path().join("record.csv"));
    assert_eq!(records.len(), 1);
    assert_eq!(records[0][0], "000001.SZ");
    assert_eq!(records[0][1], "name-1");
    assert_eq!(records[0][2], "b2");
    assert_eq!(records[0][3], "2026-06-05");
    assert_eq!(records[0][4], "1");
}

#[test]
fn run_record_backfill_does_not_replace_newer_same_code_record() {
    let temp = tempfile::tempdir().unwrap();
    std::fs::write(
        temp.path().join("record.csv"),
        [
            "code,name,method,selected_date,model_rank,model_score",
            "000001.SZ,name-new,lsh,2026-06-16,8,0.8",
        ]
        .join("\n")
            + "\n",
    )
    .unwrap();

    let count = update_run_record(
        temp.path(),
        Method::B2,
        NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
        &[display_row("000001.SZ", 1)],
        10,
        30,
    )
    .unwrap();

    assert_eq!(count, 1);
    let records = read_record_csv(&temp.path().join("record.csv"));
    assert_eq!(records.len(), 1);
    assert_eq!(records[0][0], "000001.SZ");
    assert_eq!(records[0][1], "name-new");
    assert_eq!(records[0][2], "lsh");
    assert_eq!(records[0][3], "2026-06-16");
    assert_eq!(records[0][4], "8");
}

#[test]
fn run_record_serializes_concurrent_updates() {
    let temp = tempfile::tempdir().unwrap();
    let runtime_root = Arc::new(temp.path().to_path_buf());
    let barrier = Arc::new(Barrier::new(2));

    let handles = ["000101.SZ", "000102.SZ"]
        .into_iter()
        .map(|code| {
            let runtime_root = Arc::clone(&runtime_root);
            let barrier = Arc::clone(&barrier);
            thread::spawn(move || {
                barrier.wait();
                update_run_record(
                    &runtime_root,
                    Method::B2,
                    NaiveDate::from_ymd_opt(2026, 6, 12).unwrap(),
                    &[display_row(code, 1)],
                    10,
                    30,
                )
                .unwrap();
            })
        })
        .collect::<Vec<_>>();

    for handle in handles {
        handle.join().unwrap();
    }

    let records = read_record_csv(&temp.path().join("record.csv"));
    let codes = records
        .iter()
        .map(|row| row[0].as_str())
        .collect::<Vec<_>>();
    assert!(codes.contains(&"000101.SZ"));
    assert!(codes.contains(&"000102.SZ"));
}

#[test]
fn run_record_limit_controls_rows_written_per_run() {
    let temp = tempfile::tempdir().unwrap();
    let rows = (1..=5)
        .map(|rank| display_row(&format!("{rank:06}.SZ"), rank))
        .collect::<Vec<_>>();

    let count = update_run_record(
        temp.path(),
        Method::B2,
        NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
        &rows,
        10,
        2,
    )
    .unwrap();

    assert_eq!(count, 2);
    let records = read_record_csv(&temp.path().join("record.csv"));
    let codes = records
        .iter()
        .map(|row| row[0].as_str())
        .collect::<Vec<_>>();
    assert_eq!(codes, vec!["000001.SZ", "000002.SZ"]);
}
