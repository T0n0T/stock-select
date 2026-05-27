use stock_select_rs::environment_profiles::get_method_environment_profile;
use stock_select_rs::reviewers::b2_scoring::{
    B2PreviousAbnormalMoveMode, B2PricePositionMode, B2VerdictInput, B2WatchInput,
    infer_b2_elastic_watch, infer_b2_verdict, infer_b2_watch_tier, score_b2_previous_abnormal_move,
    score_b2_price_position, score_b2_volume_behavior, score_b2_watch,
};

#[test]
fn b2_watch_score_matches_python_formula() {
    let input = B2WatchInput {
        verdict: "WATCH",
        total_score: 4.0,
        trend_structure: 4.0,
        price_position: 4.0,
        volume_behavior: 3.0,
        previous_abnormal_move: 5.0,
        macd_phase: 4.3,
        elastic_watch_reason: Some("mid_macd_elastic_watch"),
        signal: Some("B3"),
        signal_type: "trend_start",
    };

    assert_eq!(score_b2_watch(input), Some(97.6));
}

#[test]
fn b2_elastic_watch_and_tier_follow_python_thresholds() {
    let input = B2WatchInput {
        verdict: "WATCH",
        total_score: 4.0,
        trend_structure: 4.0,
        price_position: 4.0,
        volume_behavior: 3.0,
        previous_abnormal_move: 5.0,
        macd_phase: 4.3,
        elastic_watch_reason: None,
        signal: Some("B3"),
        signal_type: "trend_start",
    };

    let (elastic_watch, reason) = infer_b2_elastic_watch(&input);
    assert!(elastic_watch);
    assert_eq!(reason, Some("mid_macd_elastic_watch"));
    assert_eq!(
        infer_b2_watch_tier("WATCH", Some(70.0), reason, Some("B3")),
        Some("WATCH-A")
    );
    assert_eq!(
        infer_b2_watch_tier("WATCH", Some(49.9), None, Some("B2")),
        Some("WATCH-C")
    );
    assert_eq!(
        infer_b2_watch_tier("WATCH", Some(99.0), None, Some("B5")),
        Some("WATCH-C")
    );
}

#[test]
fn b2_verdict_neutral_mid_macd_upgrade_matches_python_branch() {
    let profile = get_method_environment_profile("b2", "neutral").unwrap();
    let verdict = infer_b2_verdict(B2VerdictInput {
        total_score: 4.1,
        trend_structure: 4.0,
        price_position: 4.0,
        volume_behavior: 3.0,
        previous_abnormal_move: 5.0,
        macd_phase: 4.0,
        signal: Some("B2"),
        signal_type: "trend_start",
        close_above_ma25_pct: Some(2.0),
        ma25_above_zxdkx_pct: Some(3.0),
        zxdq_5d_slope_pct: Some(0.1),
        profile: Some(&profile),
        strong_negative_macd_guard: true,
    });

    assert_eq!(verdict, "PASS");
}

#[test]
fn b2_verdict_b5_watch_score_is_penalized() {
    let score = score_b2_watch(B2WatchInput {
        verdict: "WATCH",
        total_score: 3.5,
        trend_structure: 3.0,
        price_position: 3.0,
        volume_behavior: 2.0,
        previous_abnormal_move: 3.0,
        macd_phase: 3.0,
        elastic_watch_reason: None,
        signal: Some("B5"),
        signal_type: "rebound",
    });

    assert_eq!(score, Some(-24.4));
}

#[test]
fn b2_price_position_uses_mid_price_box_position() {
    let close = vec![10.0; 120];
    let mut high = vec![10.0; 120];
    let mut low = vec![8.0; 120];
    high[119] = 9.6;
    low[119] = 9.4;

    assert_eq!(
        score_b2_price_position(&close, &high, &low, B2PricePositionMode::Default),
        5.0
    );
    assert_eq!(
        score_b2_price_position(&close, &high, &low, B2PricePositionMode::LowRiskRequired),
        4.0
    );
}

#[test]
fn b2_volume_behavior_detects_high_close_with_supportive_volume() {
    let close = (1..=20).map(|value| value as f64).collect::<Vec<_>>();
    let volume = vec![100.0; 20];

    assert_eq!(score_b2_volume_behavior(&close, &volume), 5.0);
}

#[test]
fn b2_previous_abnormal_move_strict_mode_matches_thresholds() {
    let open = vec![10.0, 20.0, 15.0, 14.0];
    let close = vec![10.0, 22.0, 15.0, 14.0];
    let volume = vec![100.0, 1000.0, 200.0, 150.0];

    assert_eq!(
        score_b2_previous_abnormal_move(&open, &close, &volume, B2PreviousAbnormalMoveMode::Strict),
        5.0
    );
    assert_eq!(
        score_b2_previous_abnormal_move(
            &open,
            &close,
            &volume,
            B2PreviousAbnormalMoveMode::Lenient
        ),
        3.0
    );
}
