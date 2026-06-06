use assert_cmd::Command;
use chrono::NaiveDate;
use predicates::prelude::*;
use serde_json::{Value, json};
use stock_select::cache::{write_prepared_cache, write_prepared_cache_for_mode};
use stock_select::model::{Method, PreparedRow};

fn write_fake_chart_renderer(temp: &std::path::Path) -> std::path::PathBuf {
    let renderer = temp.join("fake-renderer.sh");
    std::fs::write(
        &renderer,
        r#"#!/usr/bin/env bash
set -euo pipefail
input=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --input) input="$2"; shift 2 ;;
    *) shift ;;
  esac
done
python3 - "$input" <<'PY'
import json, pathlib, sys
payload = json.loads(pathlib.Path(sys.argv[1]).read_text())
for chart in payload["charts"]:
    out = pathlib.Path(chart["out_path"])
    out.parent.mkdir(parents=True, exist_ok=True)
    latest = chart["rows"][-1]
    out.write_text(f"code={chart['code']} close={latest['close']} date={latest['date']}\n", encoding="utf-8")
PY
"#,
    )
    .unwrap();
    let mut perms = std::fs::metadata(&renderer).unwrap().permissions();
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        perms.set_mode(0o755);
    }
    std::fs::set_permissions(&renderer, perms).unwrap();
    renderer
}

fn write_display(runtime: &std::path::Path) -> std::path::PathBuf {
    let run_dir = runtime.join("select/2026-05-25.b2");
    std::fs::create_dir_all(&run_dir).unwrap();
    std::fs::write(
        run_dir.join("display.json"),
        serde_json::to_vec_pretty(&json!({
            "method": "b2",
            "artifact_key": "2026-05-25",
            "rows": [
                {"code": "000001.SZ", "name": "测试一", "industry": "银行", "model_rank": 1, "model_score": 0.7, "llm_action": null, "llm_risk_flags": []},
                {"code": "000002.SZ", "name": "测试二", "industry": "地产", "model_rank": 2, "model_score": 0.6, "llm_action": null, "llm_risk_flags": []}
            ]
        }))
        .unwrap(),
    )
    .unwrap();
    run_dir
}

fn write_chart_prepared_cache(runtime: &std::path::Path) {
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let start_date = pick_date - chrono::Duration::days(366);
    let rows = vec![
        prepared_row("000001.SZ", 23, 10.0),
        prepared_row("000001.SZ", 24, 11.5),
        prepared_row("000001.SZ", 25, 12.25),
        prepared_row("000002.SZ", 24, 20.0),
        prepared_row("000002.SZ", 25, 19.5),
    ];
    write_prepared_cache(runtime, Method::B2, pick_date, start_date, pick_date, &rows).unwrap();
}

fn write_intraday_display(runtime: &std::path::Path) -> std::path::PathBuf {
    let run_dir = runtime.join("select/2026-05-25.intraday.b2");
    std::fs::create_dir_all(&run_dir).unwrap();
    std::fs::write(
        run_dir.join("display.json"),
        serde_json::to_vec_pretty(&json!({
            "method": "b2",
            "artifact_key": "2026-05-25.intraday",
            "rows": [
                {"code": "000001.SZ", "name": "测试一", "industry": "银行", "model_rank": 1, "model_score": 0.7, "llm_action": null, "llm_risk_flags": []}
            ]
        }))
        .unwrap(),
    )
    .unwrap();
    run_dir
}

fn write_intraday_chart_prepared_cache(runtime: &std::path::Path) {
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 5, 22).unwrap();
    let start_date = previous_trade_date - chrono::Duration::days(366);
    let rows = vec![
        prepared_row("000001.SZ", 22, 10.0),
        prepared_row("000001.SZ", 25, 13.75),
    ];
    write_prepared_cache_for_mode(
        runtime,
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        true,
        &rows,
    )
    .unwrap();
}

fn prepared_row(code: &str, day: u32, close: f64) -> PreparedRow {
    PreparedRow {
        ts_code: code.to_string(),
        trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
        open: close - 0.2,
        high: close + 0.5,
        low: close - 0.5,
        close,
        volume: 1000.0 + close,
        turnover_n: 12.0,
        turnover_rate: Some(1.5),
        k: 50.0,
        d: 40.0,
        j: 60.0,
        zxdq: Some(close - 0.1),
        zxdkx: Some(close - 0.2),
        dif: 0.3,
        dea: 0.2,
        macd_hist: 0.1,
        ma25: Some(close - 0.3),
        ma60: None,
        ma144: None,
        chg_d: Some(1.2),
        weekly_ma_bull: true,
        max_vol_not_bearish: false,
        v_shrink: true,
        safe_mode: false,
        lt_filter: true,
        yellow_b1: false,
    }
}

#[test]
fn chart_generates_png_artifacts_and_cleans_payloads_from_display_rows() {
    let temp = tempfile::tempdir().unwrap();
    write_display(temp.path());
    write_chart_prepared_cache(temp.path());
    let renderer = write_fake_chart_renderer(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.env("STOCK_SELECT_CHART_RENDERER", &renderer)
        .args([
            "chart",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
            "--chart-workers",
            "2",
        ])
        .assert()
        .success()
        .stdout(predicate::str::contains(
            "chart complete: charts/2026-05-25.b2 rows=2",
        ));

    let chart_dir = temp.path().join("charts/2026-05-25.b2");
    assert!(chart_dir.join("000001.SZ_day.png").exists());
    let png = std::fs::read_to_string(chart_dir.join("000001.SZ_day.png")).unwrap();
    assert!(png.contains("close=12.25"));
    assert!(png.contains("2026-05-25"));
    assert!(
        !temp
            .path()
            .join("charts/2026-05-25.b2.payload.part-01-of-02.json")
            .exists()
    );
    assert!(
        !temp
            .path()
            .join("charts/2026-05-25.b2.payload.part-02-of-02.json")
            .exists()
    );
    assert!(
        !temp
            .path()
            .join("select/2026-05-25.b2/charts.json")
            .exists()
    );
}

#[test]
fn intraday_chart_reads_intraday_prepared_cache() {
    let temp = tempfile::tempdir().unwrap();
    write_intraday_display(temp.path());
    write_intraday_chart_prepared_cache(temp.path());
    let renderer = write_fake_chart_renderer(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.env("STOCK_SELECT_CHART_RENDERER", &renderer)
        .args([
            "chart",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
            "--intraday",
        ])
        .assert()
        .success()
        .stdout(predicate::str::contains(
            "chart complete: charts/2026-05-25.intraday.b2 rows=1",
        ));

    let png = std::fs::read_to_string(
        temp.path()
            .join("charts/2026-05-25.intraday.b2/000001.SZ_day.png"),
    )
    .unwrap();
    assert!(png.contains("close=13.75"));
}

#[test]
fn review_writes_llm_tasks_without_changing_display_rank() {
    let temp = tempfile::tempdir().unwrap();
    let run_dir = write_display(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "review",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--limit",
        "1",
    ])
    .assert()
    .success()
    .stdout(predicate::str::contains(
        "review tasks complete: select/2026-05-25.b2/llm_tasks.json rows=1",
    ));

    let tasks: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("llm_tasks.json")).unwrap()).unwrap();
    assert_eq!(tasks["rows"].as_array().unwrap().len(), 1);
    assert_eq!(tasks["rows"][0]["model_rank"], 1);
    assert_eq!(tasks["rows"][0]["code"], "000001.SZ");
    assert_eq!(
        tasks["rows"][0]["chart_path"],
        "charts/2026-05-25.b2/000001.SZ_day.png"
    );
}

#[test]
fn review_accepts_old_control_flags_as_task_metadata() {
    let temp = tempfile::tempdir().unwrap();
    let run_dir = write_display(temp.path());
    let model_path = temp.path().join("model.txt");
    let metadata_path = temp.path().join("model_metadata.json");
    std::fs::write(&model_path, "tree\n").unwrap();
    std::fs::write(&metadata_path, "{}\n").unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "review",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--environment-state",
        "neutral",
        "--environment-reason",
        "manual neutral",
        "--model-path",
        model_path.to_str().unwrap(),
        "--model-feature-metadata-path",
        metadata_path.to_str().unwrap(),
        "--record",
        "--record-window-trading-days",
        "9",
    ])
    .assert()
    .success();

    let tasks: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("llm_tasks.json")).unwrap()).unwrap();
    assert_eq!(tasks["environment"]["state"], "neutral");
    assert_eq!(tasks["environment"]["reason"], "manual neutral");
    assert_eq!(tasks["model_path"], model_path.to_string_lossy().as_ref());
    assert_eq!(
        tasks["model_feature_metadata_path"],
        metadata_path.to_string_lossy().as_ref()
    );
    assert_eq!(tasks["record"]["enabled"], true);
    assert_eq!(tasks["record"]["window_trading_days"], 9);
    assert_eq!(tasks["rows"][0]["model_rank"], 1);
}

#[test]
fn review_merge_applies_annotations_to_display_without_changing_rank() {
    let temp = tempfile::tempdir().unwrap();
    let run_dir = write_display(temp.path());
    std::fs::write(
        run_dir.join("llm_annotations.json"),
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000002.SZ", "llm_action": "CAUTION", "llm_confidence": 0.8, "llm_risk_flags": ["量能不足"], "llm_comment": "等待确认", "raw_response_path": null}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "review-merge",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
    ])
    .assert()
    .success()
    .stdout(predicate::str::contains(
        "review-merge complete: select/2026-05-25.b2/display.json rows=2 annotations=1",
    ));

    let display: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("display.json")).unwrap()).unwrap();
    assert_eq!(display["rows"][0]["model_rank"], 1);
    assert_eq!(display["rows"][1]["model_rank"], 2);
    assert_eq!(display["rows"][1]["llm_action"], "CAUTION");
    assert_eq!(display["rows"][1]["llm_risk_flags"][0], "量能不足");
}

#[test]
fn completions_generates_requested_shell_script() {
    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args(["completions", "--shell", "bash"])
        .assert()
        .success()
        .stdout(predicate::str::contains("_stock-select-rs"));
}
