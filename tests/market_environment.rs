use chrono::NaiveDate;
use stock_select_rs::cli::resolve_review_environment_args_for_test;
use stock_select_rs::market_environment::{
    EnvironmentEvaluation, ensure_market_environment_for_test, resolve_market_environment_for_test,
};

#[test]
fn manual_environment_writes_history_and_resolves_snapshot() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let resolved = ensure_market_environment_for_test(
        temp.path(),
        pick_date,
        Some("weak".to_string()),
        Some("manual weak reason".to_string()),
        || panic!("manual override must not call evaluator"),
    )
    .unwrap();

    assert_eq!(resolved.state, "weak");
    assert_eq!(resolved.source, "manual_override");
    assert_eq!(resolved.reason.as_deref(), Some("manual weak reason"));
    assert!(temp.path().join("environment/history.jsonl").exists());
    assert!(temp.path().join("environment/latest.json").exists());
}

#[test]
fn missing_environment_uses_evaluator_and_persists_daily_record() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let resolved = ensure_market_environment_for_test(temp.path(), pick_date, None, None, || {
        Ok(EnvironmentEvaluation {
            state: "neutral".to_string(),
            score_based_state: "neutral".to_string(),
            rule_based_state: "weak".to_string(),
            vote_based_state: "neutral".to_string(),
            evaluate_date: pick_date,
            source: "scheduled".to_string(),
            reason: "SSE neutral; CN2000 neutral; 修复或分化，环境中立".to_string(),
            total_score: 1.25,
            score_based_total: 1.25,
        })
    })
    .unwrap();

    assert_eq!(resolved.state, "neutral");
    let reread = resolve_market_environment_for_test(temp.path(), pick_date).unwrap();
    assert_eq!(reread.state, "neutral");
    assert_eq!(reread.interval_start, Some(pick_date));
    assert!(
        temp.path()
            .join("environment/daily/2026-05-25.neutral.json")
            .exists()
    );
}

#[test]
fn cli_environment_resolver_keeps_manual_override_and_returns_review_args() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let (state, reason) = resolve_review_environment_args_for_test(
        temp.path(),
        pick_date,
        Some("weak".to_string()),
        Some("manual reason".to_string()),
        || panic!("manual override must not call evaluator"),
    )
    .unwrap();

    assert_eq!(state.as_deref(), Some("weak"));
    assert_eq!(reason.as_deref(), Some("manual reason"));
    assert!(temp.path().join("environment/history.jsonl").exists());
}

#[test]
fn cli_environment_resolver_evaluates_missing_environment_and_returns_review_args() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let (state, reason) =
        resolve_review_environment_args_for_test(temp.path(), pick_date, None, None, || {
            Ok(EnvironmentEvaluation {
                state: "neutral".to_string(),
                score_based_state: "neutral".to_string(),
                rule_based_state: "neutral".to_string(),
                vote_based_state: "neutral".to_string(),
                evaluate_date: pick_date,
                source: "scheduled".to_string(),
                reason: "SSE neutral; CN2000 neutral; 修复或分化，环境中立".to_string(),
                total_score: 0.0,
                score_based_total: 0.0,
            })
        })
        .unwrap();

    assert_eq!(state.as_deref(), Some("neutral"));
    assert_eq!(
        reason.as_deref(),
        Some("SSE neutral; CN2000 neutral; 修复或分化，环境中立")
    );
    assert!(
        temp.path()
            .join("environment/daily/2026-05-25.neutral.json")
            .exists()
    );
}
