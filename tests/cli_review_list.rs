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
    cmd.current_dir(temp.path()).env_remove("DUCKDB_PATH");
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
    cmd.current_dir(temp.path()).env_remove("DUCKDB_PATH");
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
fn review_list_uses_cached_display_without_connecting_to_duckdb() {
    let temp = tempfile::tempdir().unwrap();
    let display_dir = temp.path().join("select/2026-05-26.b2");
    std::fs::create_dir_all(&display_dir).unwrap();
    std::fs::write(
        display_dir.join("display.json"),
        serde_json::to_vec(&json!({
            "rows": [{"code":"000001.SZ", "model_rank":1, "model_score":0.8,
                "llm_action":null, "llm_risk_flags":[]}]
        }))
        .unwrap(),
    )
    .unwrap();

    Command::cargo_bin("stock-select-rs")
        .unwrap()
        .current_dir(temp.path())
        .env("DUCKDB_PATH", "/unavailable/duckdb.db")
        .args([
            "review-list",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-05-26",
            "--method",
            "b2",
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
                {"code": "000002.SZ", "name": "测试二", "industry": "全国地产", "model_rank": 1, "model_score": 0.7, "llm_action": "KEEP", "llm_risk_flags": []},
                {"code": "000001.SZ", "name": "测试一", "model_rank": 2, "model_score": 0.6, "llm_action": "CAUTION", "llm_risk_flags": ["高位"]}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.current_dir(temp.path()).env_remove("DUCKDB_PATH");
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
    .stdout("1\t000002.SZ\t测试二\t全国地产\t0.700000\t↑\n");
}

#[test]
fn review_list_recompute_ignores_existing_display_artifact() {
    let temp = tempfile::tempdir().unwrap();
    let display_dir = temp.path().join("select/2026-05-25.b2");
    std::fs::create_dir_all(&display_dir).unwrap();
    std::fs::write(
        display_dir.join("display.json"),
        serde_json::to_vec_pretty(&json!({
            "rows": [
                {"code": "000099.SZ", "name": "旧缓存", "model_rank": 1, "model_score": 0.7, "llm_action": null, "llm_risk_flags": []}
            ]
        }))
        .unwrap(),
    )
    .unwrap();

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.current_dir(temp.path())
        .env_remove("DUCKDB_PATH")
        .args([
            "review-list",
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
        .stdout(predicate::str::is_empty())
        .stderr(predicate::str::contains(
            "DUCKDB_PATH is required; set it in .env or pass --duckdb-path.",
        ));
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

#[test]
fn scm_review_list_fifth_column_keeps_entry_tier_separate_from_llm_and_marks_old_cache() {
    let temp = tempfile::tempdir().unwrap();
    let dir = temp.path().join("select/2026-11-20.scm");
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("display.json"),
        serde_json::to_vec(&json!({"rows": [
            {"code":"000001.SZ","name":"测试一","industry":"银行","model_rank":1,"model_score":1.0,
             "raw_model_score":0.1,"llm_action":"REJECT","llm_risk_flags":[],
             "entry_assessment":{"action":"open","reason":"分数与环境通过","research":true,
               "gate":{"open_min_score":0.0,"discard_below_score":-0.2,"top_n":3}}},
            {"code":"000002.SZ","name":"旧缓存","industry":"地产","model_rank":2,"model_score":0.9,
             "llm_action":null,"llm_risk_flags":[]},
            {"code":"000003.SZ","name":"历史日期","industry":"地产","model_rank":3,"model_score":0.8,
             "raw_model_score":0.228483,"llm_action":"CAUTION","llm_risk_flags":[],
             "entry_assessment":{"action":"observe","reason":"日期早于校准完成","research":false}}
        ]}))
        .unwrap(),
    )
    .unwrap();
    let output = Command::cargo_bin("stock-select-rs")
        .unwrap()
        .current_dir(temp.path())
        .env_remove("DUCKDB_PATH")
        .args([
            "review-list",
            "--runtime-root",
            temp.path().to_str().unwrap(),
            "--pick-date",
            "2026-11-20",
            "--method",
            "scm",
        ])
        .assert()
        .success()
        .get_output()
        .stdout
        .clone();
    let text = String::from_utf8(output).unwrap();
    let lines = text.lines().collect::<Vec<_>>();
    assert_eq!(lines[0].split('\t').nth(4).unwrap(), "开仓 | +0.100000");
    assert!(lines[0].ends_with("\t↓"));
    assert_eq!(lines[1].split('\t').nth(4).unwrap(), "观察 | 缺失");
    assert_eq!(lines[2].split('\t').nth(4).unwrap(), "观察 | +0.228483");
    assert!(lines[2].ends_with("\t→"));
}

#[test]
fn review_list_can_select_aligned_table_or_tsv_from_cached_display() {
    let temp = tempfile::tempdir().unwrap();
    let dir = temp.path().join("select/2026-11-20.scm");
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("display.json"), serde_json::to_vec(&json!({"rows":[{
        "code":"688775.SH", "name":"影石创新", "industry":"消费电子", "model_rank":1,
        "raw_model_score":0.228483, "entry_assessment":{"action":"observe", "reason":"日期早于校准完成"},
        "llm_action":"KEEP", "llm_risk_flags":[]
    }]})).unwrap()).unwrap();
    let output = |format: &str| {
        let bytes = Command::cargo_bin("stock-select-rs")
            .unwrap()
            .current_dir(temp.path())
            .env_remove("DUCKDB_PATH")
            .args([
                "review-list",
                "--method",
                "scm",
                "--pick-date",
                "2026-11-20",
                "--runtime-root",
                temp.path().to_str().unwrap(),
                "--format",
                format,
            ])
            .assert()
            .success()
            .get_output()
            .stdout
            .clone();
        String::from_utf8(bytes).unwrap()
    };
    let table = output("table");
    assert!(table.starts_with("排名  代码"));
    assert!(table.contains("观察 | +0.228483"));
    assert!(!table.contains('\t'));
    let tsv = output("tsv");
    assert_eq!(
        tsv,
        "1\t688775.SH\t影石创新\t消费电子\t观察 | +0.228483\t↑\n"
    );
    assert_eq!(output("auto"), tsv);
}
