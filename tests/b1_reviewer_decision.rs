use stock_select_rs::reviewers::b1::{B1DecisionInput, B1ReviewDecision, decide_b1_review};

#[test]
fn weak_exact_distribution_sample_matches_python_pass_b() {
    let decision = decide_b1_review(B1DecisionInput {
        signal_type: "distribution_risk",
        trend_structure: 2.0,
        price_position: 4.0,
        volume_behavior: 4.0,
        previous_abnormal_move: 5.0,
        macd_phase: 4.16,
        raw_total_score: 3.76,
        environment_state: "weak",
        gate_flags: vec![],
    });

    assert_eq!(
        decision,
        B1ReviewDecision {
            score_combo_key: "distribution_risk|T2|P4|V4|A5|M4.0".to_string(),
            high_return_combo_match: "exact".to_string(),
            pass_family: Some("distribution".to_string()),
            pass_family_tier: "core".to_string(),
            verdict: "PASS".to_string(),
            total_score: 4.78,
            score_layer: Some("PASS-B".to_string()),
            score_layer_score: Some(84.0),
        }
    );
}

#[test]
fn weak_exact_distribution_runup_gate_downgrades_to_watch() {
    let decision = decide_b1_review(B1DecisionInput {
        signal_type: "distribution_risk",
        trend_structure: 2.0,
        price_position: 4.0,
        volume_behavior: 4.0,
        previous_abnormal_move: 5.0,
        macd_phase: 4.16,
        raw_total_score: 3.76,
        environment_state: "weak",
        gate_flags: vec!["runup_over_limit"],
    });

    assert_eq!(decision.verdict, "WATCH");
    assert_eq!(decision.score_layer.as_deref(), Some("WATCH-A"));
    assert_eq!(decision.score_layer_score, Some(74.0));
    assert_eq!(decision.total_score, 4.32);
}

#[test]
fn weak_rebound_near_sample_matches_python_watch_c() {
    let decision = decide_b1_review(B1DecisionInput {
        signal_type: "rebound",
        trend_structure: 3.0,
        price_position: 2.0,
        volume_behavior: 4.0,
        previous_abnormal_move: 5.0,
        macd_phase: 3.17,
        raw_total_score: 3.49,
        environment_state: "weak",
        gate_flags: vec!["cooldown_active", "sideways_tight_range"],
    });

    assert_eq!(decision.score_combo_key, "rebound|T3|P2|V4|A5|M3.0");
    assert_eq!(decision.high_return_combo_match, "none");
    assert_eq!(decision.pass_family.as_deref(), Some("rebound"));
    assert_eq!(decision.pass_family_tier, "near");
    assert_eq!(decision.verdict, "WATCH");
    assert_eq!(decision.score_layer.as_deref(), Some("WATCH-C"));
    assert_eq!(decision.score_layer_score, Some(50.0));
    assert_eq!(decision.total_score, 3.54);
}

#[test]
fn non_family_rebound_sample_matches_python_fail() {
    let decision = decide_b1_review(B1DecisionInput {
        signal_type: "rebound",
        trend_structure: 3.0,
        price_position: 1.0,
        volume_behavior: 4.0,
        previous_abnormal_move: 5.0,
        macd_phase: 2.9,
        raw_total_score: 3.17,
        environment_state: "weak",
        gate_flags: vec!["cooldown_active", "runup_over_limit"],
    });

    assert_eq!(decision.score_combo_key, "rebound|T3|P1|V4|A5|M3.0");
    assert_eq!(decision.high_return_combo_match, "none");
    assert_eq!(decision.pass_family, None);
    assert_eq!(decision.pass_family_tier, "none");
    assert_eq!(decision.verdict, "FAIL");
    assert_eq!(decision.score_layer, None);
    assert_eq!(decision.score_layer_score, None);
    assert_eq!(decision.total_score, 2.91);
}
