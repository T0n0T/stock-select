use std::{fs, path::PathBuf};

use serde_json::Value;
use stock_select_rs::reviewers::b1::{B1DecisionInput, decide_b1_review};

#[test]
fn b1_decision_matches_python_golden_for_all_2026_05_25_reviews() {
    let root = python_b1_review_root();
    let mut checked = 0usize;
    let mut mismatches = Vec::new();

    if !root.exists() {
        eprintln!("skip b1 Python golden comparison; directory not found: {root:?}");
        return;
    }

    let mut files = fs::read_dir(&root)
        .unwrap_or_else(|err| panic!("读取 Python b1 review golden 目录失败 {root:?}: {err}"))
        .map(|entry| entry.expect("读取目录项失败").path())
        .filter(|path| {
            path.extension().and_then(|ext| ext.to_str()) == Some("json")
                && path
                    .file_name()
                    .and_then(|name| name.to_str())
                    .is_some_and(|name| {
                        name.ends_with(".SZ.json")
                            || name.ends_with(".SH.json")
                            || name.ends_with(".BJ.json")
                    })
        })
        .collect::<Vec<_>>();
    files.sort();

    for path in files {
        let text = fs::read_to_string(&path)
            .unwrap_or_else(|err| panic!("读取 Python b1 review golden 文件失败 {path:?}: {err}"));
        let data: Value = serde_json::from_str(&text)
            .unwrap_or_else(|err| panic!("解析 Python b1 review golden JSON 失败 {path:?}: {err}"));
        let baseline = data
            .get("baseline_review")
            .unwrap_or_else(|| panic!("缺少 baseline_review: {path:?}"));
        let code = string_field(&data, "code");
        let gate_flags = baseline
            .get("gate_flags")
            .and_then(Value::as_array)
            .unwrap_or_else(|| panic!("{code} 缺少 gate_flags"))
            .iter()
            .map(|item| {
                item.as_str()
                    .unwrap_or_else(|| panic!("{code} gate_flags 非字符串"))
            })
            .collect::<Vec<_>>();

        let decision = decide_b1_review(B1DecisionInput {
            signal_type: string_field(baseline, "signal_type"),
            trend_structure: number_field(baseline, "trend_structure"),
            price_position: number_field(baseline, "price_position"),
            volume_behavior: number_field(baseline, "volume_behavior"),
            previous_abnormal_move: number_field(baseline, "previous_abnormal_move"),
            macd_phase: number_field(baseline, "macd_phase"),
            raw_total_score: number_field(baseline, "raw_total_score"),
            environment_state: "weak",
            gate_flags,
        });

        assert_string(
            &mut mismatches,
            code,
            "score_combo_key",
            &decision.score_combo_key,
            string_field(baseline, "score_combo_key"),
        );
        assert_string(
            &mut mismatches,
            code,
            "high_return_combo_match",
            &decision.high_return_combo_match,
            string_field(baseline, "high_return_combo_match"),
        );
        assert_optional_string(
            &mut mismatches,
            code,
            "pass_family",
            decision.pass_family.as_deref(),
            optional_string_field(baseline, "pass_family"),
        );
        assert_string(
            &mut mismatches,
            code,
            "pass_family_tier",
            &decision.pass_family_tier,
            string_field(baseline, "pass_family_tier"),
        );
        assert_string(
            &mut mismatches,
            code,
            "verdict",
            &decision.verdict,
            string_field(baseline, "verdict"),
        );
        assert_number(
            &mut mismatches,
            code,
            "total_score",
            decision.total_score,
            number_field(baseline, "total_score"),
        );
        assert_optional_string(
            &mut mismatches,
            code,
            "score_layer",
            decision.score_layer.as_deref(),
            optional_string_field(baseline, "score_layer"),
        );
        assert_optional_number(
            &mut mismatches,
            code,
            "score_layer_score",
            decision.score_layer_score,
            optional_number_field(baseline, "score_layer_score"),
        );

        checked += 1;
    }

    assert_eq!(checked, 104, "Python b1 golden review 文件数量不符合预期");
    assert!(
        mismatches.is_empty(),
        "b1 decision golden mismatch count={}:\n{}",
        mismatches.len(),
        mismatches.join("\n")
    );
}

fn python_b1_review_root() -> PathBuf {
    let home = std::env::var("HOME").expect("缺少 HOME 环境变量");
    PathBuf::from(home).join(".agents/skills/stock-select/runtime/reviews/2026-05-25.b1")
}

fn string_field<'a>(value: &'a Value, field: &str) -> &'a str {
    value
        .get(field)
        .and_then(Value::as_str)
        .unwrap_or_else(|| panic!("字段 {field} 缺失或不是字符串"))
}

fn optional_string_field<'a>(value: &'a Value, field: &str) -> Option<&'a str> {
    value.get(field).and_then(Value::as_str)
}

fn number_field(value: &Value, field: &str) -> f64 {
    value
        .get(field)
        .and_then(Value::as_f64)
        .unwrap_or_else(|| panic!("字段 {field} 缺失或不是数字"))
}

fn optional_number_field(value: &Value, field: &str) -> Option<f64> {
    value.get(field).and_then(Value::as_f64)
}

fn assert_string(
    mismatches: &mut Vec<String>,
    code: &str,
    field: &str,
    actual: &str,
    expected: &str,
) {
    if actual != expected {
        mismatches.push(format!(
            "{code} {field}: actual={actual:?} expected={expected:?}"
        ));
    }
}

fn assert_optional_string(
    mismatches: &mut Vec<String>,
    code: &str,
    field: &str,
    actual: Option<&str>,
    expected: Option<&str>,
) {
    if actual != expected {
        mismatches.push(format!(
            "{code} {field}: actual={actual:?} expected={expected:?}"
        ));
    }
}

fn assert_number(
    mismatches: &mut Vec<String>,
    code: &str,
    field: &str,
    actual: f64,
    expected: f64,
) {
    if (actual - expected).abs() > 0.000_001 {
        mismatches.push(format!(
            "{code} {field}: actual={actual} expected={expected}"
        ));
    }
}

fn assert_optional_number(
    mismatches: &mut Vec<String>,
    code: &str,
    field: &str,
    actual: Option<f64>,
    expected: Option<f64>,
) {
    match (actual, expected) {
        (Some(actual), Some(expected)) if (actual - expected).abs() <= 0.000_001 => {}
        (None, None) => {}
        _ => mismatches.push(format!(
            "{code} {field}: actual={actual:?} expected={expected:?}"
        )),
    }
}
