use assert_cmd::Command;
use predicates::prelude::*;
use serde_json::json;

#[test]
fn review_list_rejects_zero_limit() {
    let temp = tempfile::tempdir().unwrap();
    let display_dir = temp.path().join("select/2026-05-26.b2");
    std::fs::create_dir_all(&display_dir).unwrap();
    std::fs::write(
        display_dir.join("display.json"),
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000001.SZ", "name": "测试一", "model_rank": 1, "model_score": 0.8, "llm_action": null, "llm_risk_flags": []}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "review-list",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-26",
        "--limit",
        "0",
    ])
    .assert()
    .failure()
    .stderr(predicate::str::contains(
        "review-list limit must be greater than 0",
    ));
}

#[test]
fn review_list_accepts_positive_limit_with_artifact() {
    let temp = tempfile::tempdir().unwrap();
    let display_dir = temp.path().join("select/2026-05-26.b2");
    std::fs::create_dir_all(&display_dir).unwrap();
    std::fs::write(
        display_dir.join("display.json"),
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000001.SZ", "name": "测试一", "model_rank": 1, "model_score": 0.8, "llm_action": null, "llm_risk_flags": []}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "review-list",
        "--runtime-root",
        temp.path().to_str().unwrap(),
        "--pick-date",
        "2026-05-26",
        "--method",
        "b2",
        "--limit",
        "1",
    ])
    .assert()
    .success()
    .stdout(predicate::str::contains("000001.SZ"));
}

#[test]
fn review_list_prefers_selection_display_artifact() {
    let temp = tempfile::tempdir().unwrap();
    let display_dir = temp.path().join("select/2026-05-25.b2");
    std::fs::create_dir_all(&display_dir).unwrap();
    std::fs::write(
        display_dir.join("display.json"),
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000002.SZ", "name": "测试二", "model_rank": 1, "model_score": 0.7, "llm_action": "KEEP", "llm_risk_flags": []},
                {"code": "000001.SZ", "name": "测试一", "model_rank": 2, "model_score": 0.6, "llm_action": "CAUTION", "llm_risk_flags": ["高位"]}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "review-list",
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
    .stdout("1\t000002.SZ\t测试二\t-\t0.700000\t↑\n");
}

#[test]
fn review_list_uses_old_default_runtime_root_when_omitted() {
    let temp = tempfile::tempdir().unwrap();
    let home = temp.path().join("home");
    let runtime = home.join(".agents/skills/stock-select/runtime");
    let display_dir = runtime.join("select/2026-05-25.b2");
    std::fs::create_dir_all(&display_dir).unwrap();
    std::fs::write(
        display_dir.join("display.json"),
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000002.SZ", "name": "测试二", "model_rank": 1, "model_score": 0.7, "llm_action": null, "llm_risk_flags": []}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.env("HOME", &home)
        .current_dir(temp.path())
        .args(["review-list", "--pick-date", "2026-05-25", "--method", "b2"])
        .assert()
        .success()
        .stdout("1\t000002.SZ\t测试二\t-\t0.700000\t-\n");
}
