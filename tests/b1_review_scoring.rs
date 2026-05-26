use stock_select_rs::reviewers::b1_scoring::{
    B1EnvironmentGate, PreviousAbnormalMoveMode, PricePositionMode, b1_raw_total_score,
    compute_b1_environment_gate, compute_bbi, score_b1_previous_abnormal_move,
    score_b1_price_position, score_b1_trend_structure, score_b1_volume_behavior,
};

#[test]
fn bbi_matches_python_rolling_average_formula() {
    let close = (1..=24).map(|value| value as f64).collect::<Vec<_>>();
    let bbi = compute_bbi(&close);

    assert!(bbi[22].is_none());
    assert_eq!(bbi[23], Some(18.875));
}

#[test]
fn trend_structure_scores_support_preserving_setup_as_five() {
    let len = 35;
    let open = vec![97.0; len];
    let close = vec![99.0; len];
    let ma25 = vec![Some(100.0); len];
    let zxdkx = vec![Some(95.0); len];
    let bbi = vec![Some(101.0); len];

    assert_eq!(
        score_b1_trend_structure(&open, &close, &ma25, &zxdkx, &bbi),
        5.0
    );
}

#[test]
fn trend_structure_rejects_falling_ma_or_zxdkx() {
    let len = 35;
    let open = vec![97.0; len];
    let close = vec![99.0; len];
    let mut ma25 = vec![Some(100.0); len];
    let zxdkx = vec![Some(95.0); len];
    let bbi = vec![Some(101.0); len];
    ma25[len - 5] = Some(101.0);

    assert_eq!(
        score_b1_trend_structure(&open, &close, &ma25, &zxdkx, &bbi),
        1.0
    );
}

#[test]
fn price_position_honors_default_and_environment_modes() {
    let close = vec![50.0];
    let high = vec![100.0; 120];
    let low = vec![0.0; 120];
    let ma25 = vec![Some(90.0)];
    let zxdq = vec![Some(88.0)];

    assert_eq!(
        score_b1_price_position(
            &close,
            &high,
            &low,
            &ma25,
            &zxdq,
            PricePositionMode::Default
        ),
        4.0
    );
    assert_eq!(
        score_b1_price_position(
            &close,
            &high,
            &low,
            &ma25,
            &zxdq,
            PricePositionMode::LeftSideFavored
        ),
        4.0
    );
    assert_eq!(
        score_b1_price_position(
            &close,
            &high,
            &low,
            &ma25,
            &zxdq,
            PricePositionMode::LessLeftBias
        ),
        4.0
    );
}

#[test]
fn volume_behavior_matches_python_pullback_rules() {
    let open = vec![10.0, 11.0, 10.0, 9.0];
    let close = vec![11.0, 12.0, 9.5, 9.0];
    let volume = vec![300.0, 210.0, 100.0, 150.0];

    assert_eq!(score_b1_volume_behavior(&open, &close, &volume), 5.0);
}

#[test]
fn previous_abnormal_move_matches_python_default_mode() {
    let open = vec![10.0, 20.0, 16.0, 15.9];
    let close = vec![10.5, 22.0, 16.2, 16.1];
    let low = vec![9.8, 19.0, 15.6, 15.4];
    let volume = vec![100.0, 500.0, 120.0, 130.0];

    assert_eq!(
        score_b1_previous_abnormal_move(
            &open,
            &close,
            &low,
            &volume,
            PreviousAbnormalMoveMode::Default
        ),
        5.0
    );
}

#[test]
fn previous_abnormal_move_honors_strict_and_lenient_modes() {
    let open = vec![10.0, 20.0, 18.4, 18.2];
    let close = vec![10.5, 22.0, 18.3, 18.25];
    let low = vec![9.8, 19.0, 18.0, 17.9];
    let volume = vec![100.0, 500.0, 120.0, 130.0];

    assert_eq!(
        score_b1_previous_abnormal_move(
            &open,
            &close,
            &low,
            &volume,
            PreviousAbnormalMoveMode::Default
        ),
        5.0
    );
    assert_eq!(
        score_b1_previous_abnormal_move(
            &open,
            &close,
            &low,
            &volume,
            PreviousAbnormalMoveMode::Strict
        ),
        3.0
    );
    assert_eq!(
        score_b1_previous_abnormal_move(
            &open,
            &close,
            &low,
            &volume,
            PreviousAbnormalMoveMode::Lenient
        ),
        5.0
    );
}

#[test]
fn b1_raw_total_score_uses_python_b1_weights() {
    assert_eq!(b1_raw_total_score(2.0, 4.0, 4.0, 5.0, 4.16), 3.76);
}

#[test]
fn environment_gate_matches_python_daily_metrics() {
    let close = vec![
        10.0, 10.4, 10.8, 11.2, 11.6, 12.0, 12.4, 12.8, 13.2, 13.6, 14.0, 14.4, 14.8, 15.2, 15.6,
        16.0, 16.4, 16.8, 17.2, 17.6, 18.0, 18.4, 18.8, 19.2, 19.6, 20.0, 20.4, 20.8, 21.2, 21.6,
    ];
    let ma25 = vec![Some(22.0); close.len()];
    let dif = vec![1.0, 1.2, 0.8, 0.6];
    let dea = vec![0.8, 1.0, 0.9, 0.7];

    let gate = compute_b1_environment_gate(&close, &ma25, &dif, &dea, "weak");

    assert_eq!(
        gate,
        B1EnvironmentGate {
            cooldown_active: true,
            below_ma25: true,
            runup_pct: Some(116.0),
            sideways_amplitude_pct: Some(20.0),
            weekly_macd_cooldown_active: false,
            triggered_flags: vec![
                "cooldown_active".to_string(),
                "below_ma25".to_string(),
                "runup_over_limit".to_string(),
                "sideways_tight_range".to_string(),
            ],
            score_penalty: 0.5,
        }
    );
}
