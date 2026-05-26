use stock_select_rs::environment_profiles::get_method_environment_profile;
use stock_select_rs::review_protocol::{
    b2_signal_score, compute_b1_weighted_total, compute_b2_weighted_total, compute_weighted_total,
    compute_weighted_total_for_profile, infer_signal_type, infer_verdict,
    infer_verdict_for_profile, validate_score_field,
};

fn b1_score_fixture() -> [(&'static str, f64); 5] {
    [
        ("trend_structure", 2.0),
        ("price_position", 4.0),
        ("volume_behavior", 4.0),
        ("previous_abnormal_move", 5.0),
        ("macd_phase", 4.16),
    ]
}

#[test]
fn b1_weak_environment_profile_matches_python_constants() {
    let profile = get_method_environment_profile(" B1 ", " Weak ").unwrap();

    assert_eq!(profile.method, "b1");
    assert_eq!(profile.state, "weak");
    assert_eq!(profile.signal_weight, None);
    assert_eq!(profile.pass_threshold, 4.25);
    assert_eq!(profile.watch_threshold, 3.3);
    assert_eq!(profile.weights["trend_structure"], 0.23);
    assert_eq!(profile.weights["price_position"], 0.22);
    assert_eq!(profile.weights["volume_behavior"], 0.22);
    assert_eq!(profile.weights["previous_abnormal_move"], 0.20);
    assert_eq!(profile.weights["macd_phase"], 0.13);
    assert_eq!(profile.subscore_mode["price_position"], "left_side_favored");
    assert_eq!(
        profile.subscore_mode["trend_structure"],
        "support_preserving"
    );
    assert_eq!(
        profile.llm_focus,
        "优先高分给回调充分、支撑有效、赔率优先的结构，弱环境下更严格压制高位和追高样本。"
    );
}

#[test]
fn b2_strong_environment_profile_matches_python_constants() {
    let profile = get_method_environment_profile("b2", "strong").unwrap();

    assert_eq!(profile.method, "b2");
    assert_eq!(profile.state, "strong");
    assert_eq!(profile.signal_weight, Some(0.15));
    assert_eq!(profile.pass_threshold, 3.95);
    assert_eq!(profile.watch_threshold, 3.3);
    assert_eq!(profile.weights["trend_structure"], 0.10);
    assert_eq!(profile.weights["price_position"], 0.20);
    assert_eq!(profile.weights["volume_behavior"], 0.00);
    assert_eq!(profile.weights["previous_abnormal_move"], 0.20);
    assert_eq!(profile.weights["macd_phase"], 0.35);
    assert_eq!(profile.subscore_mode["macd_phase"], "aggressive");
}

#[test]
fn unknown_environment_profile_is_rejected() {
    let err = get_method_environment_profile("dribull", "weak").unwrap_err();
    assert!(err.to_string().contains("dribull weak"));
}

#[test]
fn review_weighted_totals_match_python_fixtures() {
    let scores = b1_score_fixture();
    let weak_b1 = get_method_environment_profile("b1", "weak").unwrap();

    assert_eq!(compute_weighted_total(&scores), 3.87);
    assert_eq!(compute_b1_weighted_total(&scores), 3.76);
    assert_eq!(
        compute_weighted_total_for_profile(&scores, &weak_b1, None),
        3.76
    );

    let b2_scores = [
        ("trend_structure", 4.0),
        ("price_position", 3.0),
        ("volume_behavior", 2.0),
        ("previous_abnormal_move", 5.0),
        ("macd_phase", 4.0),
    ];
    assert_eq!(b2_signal_score(Some("B3+")), 5.0);
    assert_eq!(b2_signal_score(Some("unknown")), 3.0);
    assert_eq!(compute_b2_weighted_total(&b2_scores, Some("B2")), 3.92);
}

#[test]
fn signal_and_verdict_rules_match_python_protocol() {
    assert_eq!(
        infer_signal_type(10.5, 10.0, 4.0, 4.0, 3.0, false),
        "trend_start"
    );
    assert_eq!(
        infer_signal_type(9.5, 10.0, 3.0, 4.0, 2.0, false),
        "rebound"
    );
    assert_eq!(
        infer_signal_type(10.5, 10.0, 2.0, 4.0, 4.0, false),
        "distribution_risk"
    );

    assert_eq!(infer_verdict(4.1, 4.0, "trend_start", ""), "PASS");
    assert_eq!(infer_verdict(3.3, 4.0, "rebound", ""), "WATCH");
    assert_eq!(infer_verdict(4.8, 4.0, "distribution_risk", ""), "FAIL");
    assert_eq!(infer_verdict(3.6, 4.0, "trend_start", "hcr"), "PASS");

    let weak_b1 = get_method_environment_profile("b1", "weak").unwrap();
    assert_eq!(
        infer_verdict_for_profile(4.2, 4.0, "rebound", &weak_b1),
        "WATCH"
    );
    assert_eq!(
        infer_verdict_for_profile(4.3, 4.0, "rebound", &weak_b1),
        "PASS"
    );
}

#[test]
fn score_validation_rejects_out_of_range_or_non_finite_values() {
    assert_eq!(validate_score_field("trend_structure", 5.0).unwrap(), 5.0);
    assert!(validate_score_field("trend_structure", -0.1).is_err());
    assert!(validate_score_field("trend_structure", 5.1).is_err());
    assert!(validate_score_field("trend_structure", f64::NAN).is_err());
}

#[test]
fn weighted_total_rounding_matches_python_float_rounding() {
    let scores = [
        ("trend_structure", 14.86111111111111),
        ("price_position", 0.0),
        ("volume_behavior", 0.0),
        ("previous_abnormal_move", 0.0),
        ("macd_phase", 0.0),
    ];

    assert_eq!(compute_weighted_total(&scores), 2.67);
}
