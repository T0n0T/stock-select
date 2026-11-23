use stock_select::engine::entry::{
    EntryAction, ScoreEntryGate, ScoreEntryPolicy, load_score_entry_policy,
};

fn gate() -> ScoreEntryGate {
    serde_json::from_value(serde_json::json!({
        "open_min_score": 0.0, "discard_below_score": -0.2,
        "top_n": 2, "blocked_environments": ["weak"]
    }))
    .unwrap()
}

#[test]
fn raw_score_boundaries_environment_and_rank_produce_three_actions() {
    let gate = gate();
    assert_eq!(
        gate.decide(Some(-0.21), Some(1), Some("strong")).action,
        EntryAction::Discard
    );
    assert_eq!(
        gate.decide(Some(-0.2), Some(1), Some("strong")).action,
        EntryAction::Observe
    );
    assert_eq!(
        gate.decide(Some(0.0), Some(2), Some("strong")).action,
        EntryAction::Open
    );
    assert_eq!(
        gate.decide(Some(0.2), Some(3), Some("strong")).action,
        EntryAction::Observe
    );
    assert_eq!(
        gate.decide(Some(0.2), Some(1), Some("weak")).action,
        EntryAction::Observe
    );
    assert_eq!(
        gate.decide(Some(0.2), Some(1), None).action,
        EntryAction::Observe
    );
    assert_eq!(
        gate.decide(Some(f64::NAN), Some(1), Some("strong")).action,
        EntryAction::Observe
    );
}

#[test]
fn invalid_thresholds_and_unknown_fields_are_rejected() {
    let mut value = serde_json::to_value(gate()).unwrap();
    value["open_min_score"] = serde_json::json!(-0.3);
    assert!(
        serde_json::from_value::<ScoreEntryGate>(value)
            .unwrap()
            .validate()
            .is_err()
    );
    let mut value = serde_json::to_value(gate()).unwrap();
    value["typo"] = serde_json::json!(1);
    assert!(serde_json::from_value::<ScoreEntryGate>(value).is_err());
}

#[test]
fn policy_is_bound_to_model_date_and_eod_mode() {
    let policy: ScoreEntryPolicy = serde_json::from_value(serde_json::json!({
        "schema_version": 1, "method": "scm", "model_sha256": "a".repeat(64),
        "calibration_end_date": "2026-11-16", "status": "research", "gate": gate()
    }))
    .unwrap();
    let day = chrono::NaiveDate::from_ymd_opt(2026, 11, 20).unwrap();
    assert!(policy.applicability(&"a".repeat(64), day, false).is_none());
    assert!(
        policy
            .applicability(&"b".repeat(64), day, false)
            .unwrap()
            .contains("不匹配")
    );
    assert!(
        policy
            .applicability(&"a".repeat(64), day, true)
            .unwrap()
            .contains("盘后")
    );
    assert!(
        policy
            .applicability(&"a".repeat(64), day.with_day(1).unwrap(), false)
            .unwrap()
            .contains("校准")
    );
}

#[test]
fn metadata_policy_checks_actual_model_file_before_applying_thresholds() {
    let temp = tempfile::tempdir().unwrap();
    let model = temp.path().join("model.txt");
    let metadata = temp.path().join("model_metadata.json");
    std::fs::write(&model, b"abc").unwrap();
    std::fs::write(
        &metadata,
        serde_json::to_vec(&serde_json::json!({
            "score_entry_policy": {
                "schema_version": 1, "method": "scm",
                "model_sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
                "calibration_end_date": "2026-11-16", "status": "research", "gate": gate()
            }
        }))
        .unwrap(),
    )
    .unwrap();
    let loaded = load_score_entry_policy(Some(&model), Some(&metadata))
        .unwrap()
        .unwrap();
    assert!(loaded.1);
    std::fs::write(&model, b"different model").unwrap();
    assert!(
        !load_score_entry_policy(Some(&model), Some(&metadata))
            .unwrap()
            .unwrap()
            .1
    );
}

use chrono::Datelike;
