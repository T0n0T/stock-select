use assert_cmd::Command;
use chrono::{Datelike, NaiveDate};
use predicates::prelude::*;
use serde_json::{Value, json};

const B2_MODEL_FIXTURE_DIR: &str = "tests/fixtures/b2_model";

fn copy_fixture_b2_model_artifacts(root: &std::path::Path) {
    let model_dir = root.join("models/b2");
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::copy(
        std::path::Path::new(B2_MODEL_FIXTURE_DIR).join("model.txt"),
        model_dir.join("model.txt"),
    )
    .unwrap();
    std::fs::copy(
        std::path::Path::new(B2_MODEL_FIXTURE_DIR).join("model_metadata.json"),
        model_dir.join("model_metadata.json"),
    )
    .unwrap();
}

fn write_default_b2_model(root: &std::path::Path) {
    copy_fixture_b2_model_artifacts(root);
}

fn write_candidates(root: &std::path::Path) -> std::path::PathBuf {
    let path = root.join("candidates.json");
    std::fs::write(
        &path,
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000001.SZ", "name": "测试一", "close": 10.0, "turnover_n": 1000.0, "signal": "B2", "model_score": 0.40},
                {"code": "000002.SZ", "name": "测试二", "close": 11.0, "turnover_n": 1100.0, "signal": "B2", "model_score": 0.90}
            ]
        }))
        .unwrap(),
    )
    .unwrap();
    path
}

fn write_lightgbm_model_artifacts(root: &std::path::Path) {
    copy_fixture_b2_model_artifacts(root);
}

fn write_close_to_ma25_model(root: &std::path::Path) {
    copy_fixture_b2_model_artifacts(root);
}

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
    out.write_text(chart["code"], encoding="utf-8")
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

fn write_prepared_cache_fixture(root: &std::path::Path, pick_date: NaiveDate) {
    let prepared_dir = root.join("prepared");
    std::fs::create_dir_all(&prepared_dir).unwrap();
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"SSPRBIN1");
    write_u64(&mut bytes, 25);
    for day in 1..=25 {
        let trade_date = NaiveDate::from_ymd_opt(2026, 5, day).unwrap();
        let close = 100.0 + day as f64;
        write_prepared_row(&mut bytes, "000001.SZ", trade_date, close, Some(100.0));
    }
    std::fs::write(
        prepared_dir.join(format!("{}.bin", pick_date.format("%Y-%m-%d"))),
        bytes,
    )
    .unwrap();
}

fn write_prepared_cache_metadata(root: &std::path::Path, pick_date: NaiveDate) {
    let prepared_dir = root.join("prepared");
    std::fs::create_dir_all(&prepared_dir).unwrap();
    std::fs::write(
        prepared_dir.join(format!("{}.meta.json", pick_date.format("%Y-%m-%d"))),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b1", "b2", "dribull"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": 2,
            "row_count": 25,
            "symbol_count": 1,
            "source_table": "daily_market"
        }))
        .unwrap(),
    )
    .unwrap();
}

fn write_intraday_prepared_cache_fixture(root: &std::path::Path, pick_date: NaiveDate) {
    let prepared_dir = root.join("prepared");
    std::fs::create_dir_all(&prepared_dir).unwrap();
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"SSPRBIN1");
    write_u64(&mut bytes, 25);
    for day in 1..=25 {
        let trade_date = NaiveDate::from_ymd_opt(2026, 5, day).unwrap();
        let close = 200.0 + day as f64;
        write_prepared_row(&mut bytes, "000001.SZ", trade_date, close, Some(200.0));
    }
    std::fs::write(
        prepared_dir.join(format!("{}.intraday.bin", pick_date.format("%Y-%m-%d"))),
        bytes,
    )
    .unwrap();
}

fn write_intraday_prepared_cache_metadata(root: &std::path::Path, pick_date: NaiveDate) {
    let prepared_dir = root.join("prepared");
    std::fs::create_dir_all(&prepared_dir).unwrap();
    std::fs::write(
        prepared_dir.join(format!(
            "{}.intraday.meta.json",
            pick_date.format("%Y-%m-%d")
        )),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b1", "b2", "dribull"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": 2,
            "row_count": 25,
            "symbol_count": 1,
            "source_table": "daily_market",
            "mode": "intraday_snapshot",
            "source": "tushare_rt_k"
        }))
        .unwrap(),
    )
    .unwrap();
}

fn write_selecting_prepared_cache(root: &std::path::Path, pick_date: NaiveDate) {
    let prepared_dir = root.join("prepared");
    std::fs::create_dir_all(&prepared_dir).unwrap();
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"SSPRBIN1");
    write_u64(&mut bytes, 3);
    let rows = [
        (
            NaiveDate::from_ymd_opt(2026, 5, 23).unwrap(),
            10.0,
            1000.0,
            45.0,
        ),
        (
            NaiveDate::from_ymd_opt(2026, 5, 24).unwrap(),
            10.2,
            1000.0,
            30.0,
        ),
        (pick_date, 10.6, 1300.0, 42.0),
    ];
    for (trade_date, close, volume, j) in rows {
        write_selecting_prepared_row(&mut bytes, "000001.SZ", trade_date, close, volume, j);
    }
    std::fs::write(
        prepared_dir.join(format!("{}.bin", pick_date.format("%Y-%m-%d"))),
        bytes,
    )
    .unwrap();
    std::fs::write(
        prepared_dir.join(format!("{}.meta.json", pick_date.format("%Y-%m-%d"))),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b1", "b2", "dribull"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": 2,
            "row_count": 3,
            "symbol_count": 1,
            "source_table": "daily_market"
        }))
        .unwrap(),
    )
    .unwrap();
}

fn write_two_code_selecting_prepared_cache(root: &std::path::Path, pick_date: NaiveDate) {
    let prepared_dir = root.join("prepared");
    std::fs::create_dir_all(&prepared_dir).unwrap();
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"SSPRBIN1");
    write_u64(&mut bytes, 6);
    for (code, base) in [("000001.SZ", 10.0), ("000002.SZ", 20.0)] {
        let rows = [
            (
                NaiveDate::from_ymd_opt(2026, 5, 23).unwrap(),
                base,
                1000.0,
                45.0,
            ),
            (
                NaiveDate::from_ymd_opt(2026, 5, 24).unwrap(),
                base + 0.2,
                1000.0,
                30.0,
            ),
            (pick_date, base + 1.0, 1300.0, 42.0),
        ];
        for (trade_date, close, volume, j) in rows {
            write_selecting_prepared_row(&mut bytes, code, trade_date, close, volume, j);
        }
    }
    std::fs::write(
        prepared_dir.join(format!("{}.bin", pick_date.format("%Y-%m-%d"))),
        bytes,
    )
    .unwrap();
    std::fs::write(
        prepared_dir.join(format!("{}.meta.json", pick_date.format("%Y-%m-%d"))),
        serde_json::to_vec_pretty(&json!({
            "artifact_version": 1,
            "method": "b2",
            "shared_methods": ["b1", "b2", "dribull"],
            "pick_date": "2026-05-25",
            "start_date": "2025-05-24",
            "end_date": "2026-05-25",
            "schema_version": 2,
            "row_count": 6,
            "symbol_count": 2,
            "source_table": "daily_market"
        }))
        .unwrap(),
    )
    .unwrap();
}

fn write_selecting_prepared_row(
    bytes: &mut Vec<u8>,
    code: &str,
    trade_date: NaiveDate,
    close: f64,
    volume: f64,
    j: f64,
) {
    write_string(bytes, code);
    write_i32(bytes, trade_date.num_days_from_ce());
    for value in [
        close - 0.2,
        close + 0.1,
        close - 0.3,
        close,
        volume,
        volume * close,
        50.0,
        40.0,
        j,
    ] {
        write_f64(bytes, value);
    }
    write_option_f64(bytes, Some(close));
    write_option_f64(bytes, Some(close - 0.5));
    for value in [0.3, 0.2, 0.1] {
        write_f64(bytes, value);
    }
    write_option_f64(bytes, Some(close));
    write_option_f64(bytes, Some(close - 1.0));
    write_option_f64(bytes, None);
    write_option_f64(bytes, None);
    for value in [false, true, false, true, true, false] {
        write_bool(bytes, value);
    }
}

fn write_prepared_row(
    bytes: &mut Vec<u8>,
    code: &str,
    trade_date: NaiveDate,
    close: f64,
    ma25: Option<f64>,
) {
    write_string(bytes, code);
    write_i32(bytes, trade_date.num_days_from_ce());
    for value in [
        close - 0.5,
        close + 1.0,
        close - 1.0,
        close,
        1000.0,
        12.0,
        50.0,
        40.0,
        60.0,
    ] {
        write_f64(bytes, value);
    }
    write_option_f64(bytes, Some(close - 1.0));
    write_option_f64(bytes, Some(close - 2.0));
    for value in [0.3, 0.2, 0.1] {
        write_f64(bytes, value);
    }
    write_option_f64(bytes, ma25);
    write_option_f64(bytes, None);
    write_option_f64(bytes, None);
    write_option_f64(bytes, None);
    for value in [true, false, true, false, true, false] {
        write_bool(bytes, value);
    }
}

fn write_string(out: &mut Vec<u8>, value: &str) {
    out.extend_from_slice(&(value.len() as u16).to_le_bytes());
    out.extend_from_slice(value.as_bytes());
}

fn write_bool(out: &mut Vec<u8>, value: bool) {
    out.push(u8::from(value));
}

fn write_option_f64(out: &mut Vec<u8>, value: Option<f64>) {
    match value {
        Some(value) => {
            write_bool(out, true);
            write_f64(out, value);
        }
        None => write_bool(out, false),
    }
}

fn write_u64(out: &mut Vec<u8>, value: u64) {
    out.extend_from_slice(&value.to_le_bytes());
}

fn write_i32(out: &mut Vec<u8>, value: i32) {
    out.extend_from_slice(&value.to_le_bytes());
}

fn write_f64(out: &mut Vec<u8>, value: f64) {
    out.extend_from_slice(&value.to_le_bytes());
}

#[test]
fn b2_run_writes_model_first_selection_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    write_lightgbm_model_artifacts(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success()
    .stdout(predicate::str::contains(
        "selection run complete: select/2026-05-25.b2",
    ))
    .stderr(
        predicate::str::contains("[run] start method=b2 pick_date=2026-05-25")
            .and(predicate::str::contains("[run] candidates explicit"))
            .and(predicate::str::contains(
                "[selection] loaded candidates rows=2",
            ))
            .and(predicate::str::contains(
                "[selection] computed factors rows=2",
            ))
            .and(predicate::str::contains("[selection] wrote artifacts")),
    );

    let run_dir = temp.path().join("select/2026-05-25.b2");
    assert!(run_dir.join("run.json").exists());
    assert!(run_dir.join("candidates.json").exists());
    assert!(run_dir.join("factors.json").exists());
    assert!(run_dir.join("ranked.json").exists());
    assert!(run_dir.join("display.json").exists());

    let ranked: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("ranked.json")).unwrap()).unwrap();
    assert_eq!(ranked["method"], "b2");
    assert_eq!(ranked["artifact_key"], "2026-05-25");
    assert_eq!(ranked["rows"][0]["code"], "000001.SZ");
    assert_eq!(ranked["rows"][0]["model_rank"], 1);

    let factors: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("factors.json")).unwrap()).unwrap();
    assert_eq!(factors["rows"][0]["factors"]["close"], 10.0);
    assert_eq!(factors["rows"][0]["factors"]["turnover_n"], 1000.0);
    assert!(factors["rows"][0]["factors"].get("model_score").is_none());
    assert_eq!(
        factors["rows"][0]["diagnostics"]["factor_source"],
        "candidate_payload"
    );
}

#[test]
fn b2_run_auto_screens_candidates_when_candidates_path_is_omitted() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_lightgbm_model_artifacts(temp.path());
    write_selecting_prepared_cache(temp.path(), pick_date);
    let renderer = write_fake_chart_renderer(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.env("STOCK_SELECT_CHART_RENDERER", &renderer)
        .args([
            "run",
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
            "selection run complete: select/2026-05-25.b2",
        ));

    let generated_candidates = temp.path().join("candidates/2026-05-25.b2.json");
    assert!(generated_candidates.exists());
    let candidates: Value =
        serde_json::from_slice(&std::fs::read(generated_candidates).unwrap()).unwrap();
    assert_eq!(candidates["candidates"][0]["code"], "000001.SZ");

    let run_dir = temp.path().join("select/2026-05-25.b2");
    let run: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("run.json")).unwrap()).unwrap();
    assert_eq!(run["candidate_source"], "candidates/2026-05-25.b2.json");
    assert!(run_dir.join("display.json").exists());
    assert!(!temp.path().join("charts/2026-05-25.b2").exists());
    assert!(!run_dir.join("charts.json").exists());
    assert!(run_dir.join("llm_tasks.json").exists());
    let tasks: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("llm_tasks.json")).unwrap()).unwrap();
    assert_eq!(tasks["rows"].as_array().unwrap().len(), 0);
}

#[test]
fn b2_run_recompute_forces_auto_screen_to_reload_data_source() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_lightgbm_model_artifacts(temp.path());
    write_selecting_prepared_cache(temp.path(), pick_date);

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.current_dir(temp.path())
        .env_remove("POSTGRES_DSN")
        .args([
            "run",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
            "--recompute",
        ])
        .assert()
        .failure()
        .stderr(predicate::str::contains("A database DSN is required."));
}

#[test]
fn b2_run_accepts_old_review_control_flags_as_model_first_metadata() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    let override_dir = temp.path().join("override-model");
    write_lightgbm_model_artifacts(&override_dir);
    let model_path = override_dir.join("models/b2/model.txt");
    let metadata_path = override_dir.join("models/b2/model_metadata.json");

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
        "--environment-state",
        "strong",
        "--environment-reason",
        "manual strong",
        "--model-path",
        model_path.to_str().unwrap(),
        "--model-feature-metadata-path",
        metadata_path.to_str().unwrap(),
        "--record",
        "--record-window-trading-days",
        "7",
    ])
    .assert()
    .success();

    let run: Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("select/2026-05-25.b2/run.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(run["model_path"], model_path.to_string_lossy().as_ref());
    assert_eq!(
        run["metadata_path"],
        metadata_path.to_string_lossy().as_ref()
    );
    assert_eq!(run["environment"]["state"], "strong");
    assert_eq!(run["environment"]["reason"], "manual strong");
    assert_eq!(run["record"]["enabled"], true);
    assert_eq!(run["record"]["window_trading_days"], 7);
}

#[test]
fn b2_run_persists_environment_and_injects_env_factor() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    write_lightgbm_model_artifacts(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
        "--environment-state",
        "weak",
        "--environment-reason",
        "manual weak market",
    ])
    .assert()
    .success();

    assert!(temp.path().join("environment/history.jsonl").exists());
    assert!(
        temp.path()
            .join("environment/daily/2026-05-25.weak.json")
            .exists()
    );

    let run: Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("select/2026-05-25.b2/run.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(run["environment"]["state"], "weak");
    assert_eq!(run["environment"]["reason"], "manual weak market");
    assert_eq!(run["environment"]["source"], "manual_override");

    let factors: Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("select/2026-05-25.b2/factors.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(factors["rows"][0]["factors"]["env"], "weak");
    assert_eq!(factors["rows"][1]["factors"]["env"], "weak");
}

#[test]
fn b2_eod_run_without_manual_environment_or_dsn_fails_clearly() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    write_lightgbm_model_artifacts(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.current_dir(temp.path())
        .env_remove("POSTGRES_DSN")
        .args([
            "run",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
            "--candidates-path",
            candidates_path.to_str().unwrap(),
        ])
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "A database DSN is required for market environment evaluation.",
        ));
}

#[test]
fn b2_run_llm_review_limit_charts_only_top_ranked_rows() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_lightgbm_model_artifacts(temp.path());
    write_two_code_selecting_prepared_cache(temp.path(), pick_date);
    let renderer = write_fake_chart_renderer(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.env("STOCK_SELECT_CHART_RENDERER", &renderer)
        .args([
            "run",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
            "--llm-review-limit",
            "1",
        ])
        .assert()
        .success();

    let chart_dir = temp.path().join("charts/2026-05-25.b2");
    let chart_count = std::fs::read_dir(&chart_dir)
        .unwrap()
        .filter(|entry| {
            entry
                .as_ref()
                .unwrap()
                .path()
                .file_name()
                .unwrap()
                .to_string_lossy()
                .ends_with("_day.png")
        })
        .count();
    assert_eq!(chart_count, 1);

    let run_dir = temp.path().join("select/2026-05-25.b2");
    let tasks: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("llm_tasks.json")).unwrap()).unwrap();
    assert_eq!(tasks["rows"].as_array().unwrap().len(), 1);
    assert_eq!(
        tasks["rows"][0]["chart_path"],
        format!(
            "charts/2026-05-25.b2/{}_day.png",
            tasks["rows"][0]["code"].as_str().unwrap()
        )
    );
}

#[test]
fn b2_run_passes_pool_file_to_auto_screen() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_lightgbm_model_artifacts(temp.path());
    write_two_code_selecting_prepared_cache(temp.path(), pick_date);
    let pool_file = temp.path().join("pool.txt");
    std::fs::write(&pool_file, "000002").unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--pool-file",
        pool_file.to_str().unwrap(),
    ])
    .assert()
    .success();

    let generated_candidates: Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("candidates/2026-05-25.b2.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(generated_candidates["pool_source"], "custom");
    assert_eq!(
        generated_candidates["candidates"].as_array().unwrap().len(),
        1
    );
    assert_eq!(generated_candidates["candidates"][0]["code"], "000002.SZ");

    let ranked: Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("select/2026-05-25.b2/ranked.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(ranked["rows"].as_array().unwrap().len(), 1);
    assert_eq!(ranked["rows"][0]["code"], "000002.SZ");
}

#[test]
fn b2_run_uses_default_lightgbm_model_instead_of_input_model_score() {
    let temp = tempfile::tempdir().unwrap();
    write_default_b2_model(temp.path());
    let candidates_path = temp.path().join("candidates.json");
    std::fs::write(
        &candidates_path,
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000001.SZ", "name": "测试一", "model_score": 0.99, "factors": {"signal_strength": 1.0}},
                {"code": "000002.SZ", "name": "测试二", "model_score": 0.01, "factors": {"signal_strength": 2.0}}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success();

    let ranked: Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("select/2026-05-25.b2/ranked.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(ranked["rows"].as_array().unwrap().len(), 2);
    assert!(
        ranked["rows"][0]["model_score"]
            .as_f64()
            .unwrap()
            .is_finite()
    );
    assert_eq!(
        ranked["rows"][0]["feature_vector_path"],
        "feature_vectors.json"
    );
    assert_ne!(ranked["rows"][0]["model_score"], 0.99);
    assert_ne!(ranked["rows"][1]["model_score"], 0.01);

    let feature_vectors: Value = serde_json::from_slice(
        &std::fs::read(
            temp.path()
                .join("select/2026-05-25.b2/feature_vectors.json"),
        )
        .unwrap(),
    )
    .unwrap();
    assert_eq!(feature_vectors["rows"].as_array().unwrap().len(), 2);
    assert_eq!(
        feature_vectors["rows"][0]["feature_names"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
    assert_eq!(
        feature_vectors["rows"][0]["values"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}

#[test]
fn b2_run_uses_lightgbm_score_instead_of_candidate_model_score() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    write_lightgbm_model_artifacts(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success();

    let ranked: Value = serde_json::from_slice(
        &std::fs::read(temp.path().join("select/2026-05-25.b2/ranked.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(ranked["rows"][0]["model_rank"], 1);
    assert!(
        ranked["rows"][0]["model_score"]
            .as_f64()
            .unwrap()
            .is_finite()
    );
}

#[test]
fn b2_intraday_run_writes_intraday_scoped_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    write_lightgbm_model_artifacts(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--intraday",
        "--environment-state",
        "neutral",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success()
    .stdout(predicate::str::contains(
        "selection run complete: select/2026-05-25.intraday.b2",
    ));

    assert!(
        temp.path()
            .join("select/2026-05-25.intraday.b2/display.json")
            .exists()
    );
}

#[test]
fn b2_intraday_run_infers_pick_date_when_omitted() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    write_lightgbm_model_artifacts(temp.path());
    let today = chrono::Local::now().date_naive();
    let artifact_key = format!("{}.intraday.b2", today.format("%Y-%m-%d"));

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--method",
        "b2",
        "--intraday",
        "--environment-state",
        "neutral",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success()
    .stdout(predicate::str::contains(format!(
        "selection run complete: select/{artifact_key}"
    )));

    assert!(temp.path().join("select").join(artifact_key).exists());
}

#[test]
fn b2_intraday_run_without_manual_or_previous_environment_fails_clearly() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    write_lightgbm_model_artifacts(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--intraday",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .failure()
    .stderr(predicate::str::contains(
        "intraday requires --environment-state",
    ));
}

#[test]
fn b2_intraday_run_manual_environment_does_not_persist_daily_environment() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    write_lightgbm_model_artifacts(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--intraday",
        "--environment-state",
        "neutral",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success();

    assert!(
        !temp
            .path()
            .join("environment/daily/2026-05-25.neutral.json")
            .exists()
    );
}

#[test]
fn b2_intraday_run_without_candidates_requires_tushare_token() {
    let temp = tempfile::tempdir().unwrap();
    write_lightgbm_model_artifacts(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.current_dir(temp.path())
        .env_remove("TUSHARE_TOKEN")
        .args([
            "run",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
            "--intraday",
        ])
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "A Tushare token is required for intraday mode.",
        ));
}

#[test]
fn review_list_reads_display_after_intraday_run() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());
    write_lightgbm_model_artifacts(temp.path());

    let mut run = Command::cargo_bin("stock-select-rs").unwrap();
    run.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--intraday",
        "--environment-state",
        "neutral",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success();

    let mut review_list = Command::cargo_bin("stock-select-rs").unwrap();
    review_list
        .args([
            "review-list",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
            "--intraday",
            "--limit",
            "1",
        ])
        .assert()
        .success()
        .stdout(predicate::str::contains("1\t"));
}

#[test]
fn b1_run_still_rejects_without_model_support() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b1",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .failure()
    .stderr(predicate::str::contains("b1 model review is not available"));
}

#[test]
fn b2_run_rejects_missing_default_model_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let candidates_path = write_candidates(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .failure()
    .stderr(predicate::str::contains(
        "missing default b2 model artifacts",
    ));
}

#[test]
fn b2_run_uses_old_default_runtime_root_when_omitted() {
    let temp = tempfile::tempdir().unwrap();
    let home = temp.path().join("home");
    let runtime = home.join(".agents/skills/stock-select/runtime");
    std::fs::create_dir_all(&runtime).unwrap();
    write_lightgbm_model_artifacts(&runtime);
    let candidates_path = write_candidates(temp.path());

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.env("HOME", &home)
        .current_dir(temp.path())
        .args([
            "run",
            "--pick-date",
            "2026-05-25",
            "--method",
            "b2",
            "--environment-state",
            "neutral",
            "--candidates-path",
            candidates_path.to_str().unwrap(),
        ])
        .assert()
        .success()
        .stdout(predicate::str::contains(
            "selection run complete: select/2026-05-25.b2",
        ));

    assert!(runtime.join("select/2026-05-25.b2/run.json").exists());
}

#[test]
fn b2_run_injects_history_from_prepared_cache_when_candidate_has_no_history() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_close_to_ma25_model(temp.path());
    write_prepared_cache_fixture(temp.path(), pick_date);
    write_prepared_cache_metadata(temp.path(), pick_date);
    let candidates_path = temp.path().join("candidates.json");
    std::fs::write(
        &candidates_path,
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000001.SZ", "name": "测试一"},
                {"code": "000002.SZ", "name": "测试二"}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success();

    let run_dir = temp.path().join("select/2026-05-25.b2");
    let factors: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("factors.json")).unwrap()).unwrap();
    assert_eq!(factors["rows"][0]["code"], "000001.SZ");
    assert_eq!(factors["rows"][0]["factors"]["close_to_ma25_pct"], 25.0);
    assert_eq!(
        factors["rows"][0]["diagnostics"]["history_source"],
        "prepared_cache"
    );
    let ranked: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("ranked.json")).unwrap()).unwrap();
    assert_eq!(ranked["rows"].as_array().unwrap().len(), 2);
    assert!(
        ranked["rows"][0]["model_score"]
            .as_f64()
            .unwrap()
            .is_finite()
    );
}

#[test]
fn b2_intraday_run_injects_history_from_intraday_prepared_cache() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_close_to_ma25_model(temp.path());
    write_intraday_prepared_cache_fixture(temp.path(), pick_date);
    write_intraday_prepared_cache_metadata(temp.path(), pick_date);
    let candidates_path = temp.path().join("candidates.json");
    std::fs::write(
        &candidates_path,
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000001.SZ", "name": "测试一"}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--intraday",
        "--environment-state",
        "neutral",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success();

    let run_dir = temp.path().join("select/2026-05-25.intraday.b2");
    let factors: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("factors.json")).unwrap()).unwrap();
    assert_eq!(factors["rows"][0]["code"], "000001.SZ");
    assert_eq!(factors["rows"][0]["factors"]["close_to_ma25_pct"], 12.5);
    assert_eq!(
        factors["rows"][0]["diagnostics"]["history_source"],
        "prepared_cache"
    );
}

#[test]
fn b2_run_skips_prepared_cache_when_metadata_is_missing() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    write_close_to_ma25_model(temp.path());
    write_prepared_cache_fixture(temp.path(), pick_date);
    let candidates_path = temp.path().join("candidates.json");
    std::fs::write(
        &candidates_path,
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000001.SZ", "name": "测试一"}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "run",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-25",
        "--method",
        "b2",
        "--candidates-path",
        candidates_path.to_str().unwrap(),
    ])
    .assert()
    .success();

    let run_dir = temp.path().join("select/2026-05-25.b2");
    let factors: Value =
        serde_json::from_slice(&std::fs::read(run_dir.join("factors.json")).unwrap()).unwrap();
    assert_eq!(factors["rows"][0]["code"], "000001.SZ");
    assert!(
        factors["rows"][0]["factors"]
            .get("close_to_ma25_pct")
            .is_none()
    );
    assert!(
        factors["rows"][0]["diagnostics"]
            .get("history_source")
            .is_none()
    );
}
