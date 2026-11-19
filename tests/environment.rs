use chrono::{Duration, NaiveDate};
use stock_select::environment::{
    EnvironmentEvaluation, ensure_market_environment_for_test, evaluate_market_environment,
    resolve_intraday_market_environment_for_test, resolve_market_environment_for_test,
};
use stock_select::model::MarketRow;

#[test]
fn manual_environment_writes_old_runtime_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let resolved = ensure_market_environment_for_test(
        temp.path(),
        pick_date,
        Some("weak".to_string()),
        Some("manual weak".to_string()),
        || panic!("manual override should not evaluate"),
    )
    .unwrap();

    assert_eq!(resolved.state, "weak");
    assert_eq!(resolved.source, "manual_override");
    assert_eq!(resolved.reason.as_deref(), Some("manual weak"));
    assert!(temp.path().join("environment/history.jsonl").exists());
    assert!(temp.path().join("environment/latest.json").exists());
    assert!(
        temp.path()
            .join("environment/daily/2026-05-25.weak.json")
            .exists()
    );
}

#[test]
fn evaluated_environment_persists_and_can_be_resolved() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let resolved = ensure_market_environment_for_test(temp.path(), pick_date, None, None, || {
        Ok(EnvironmentEvaluation {
            state: "strong".to_string(),
            score_based_state: "strong".to_string(),
            rule_based_state: "neutral".to_string(),
            vote_based_state: "strong".to_string(),
            evaluate_date: pick_date,
            source: "scheduled".to_string(),
            reason: "index strong".to_string(),
            total_score: 12.0,
            score_based_total: 12.0,
        })
    })
    .unwrap();

    assert_eq!(resolved.state, "strong");
    let reread = resolve_market_environment_for_test(temp.path(), pick_date).unwrap();
    assert_eq!(reread.state, "strong");
    assert_eq!(reread.interval_start, Some(pick_date));
}

#[test]
fn intraday_without_manual_uses_previous_environment_without_persisting() {
    let temp = tempfile::tempdir().unwrap();
    let previous = NaiveDate::from_ymd_opt(2026, 5, 24).unwrap();
    let intraday = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    ensure_market_environment_for_test(
        temp.path(),
        previous,
        Some("neutral".to_string()),
        Some("previous day".to_string()),
        || panic!("manual override should not evaluate"),
    )
    .unwrap();

    let resolved = resolve_intraday_market_environment_for_test(
        temp.path(),
        intraday,
        None,
        None,
        Some(previous),
    )
    .unwrap();

    assert_eq!(resolved.state, "neutral");
    assert_eq!(resolved.reason.as_deref(), Some("previous day"));
    assert!(
        !temp
            .path()
            .join("environment/daily/2026-05-25.neutral.json")
            .exists()
    );
}

#[test]
fn evaluate_market_environment_scores_strong_weak_and_neutral_histories() {
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let strong_sse = index_history("000001.SH", pick_date, |idx| 100.0 + idx as f64 * 1.8);
    let strong_cn2000 = index_history("399303.SZ", pick_date, |idx| 80.0 + idx as f64 * 1.4);

    let strong = evaluate_market_environment(pick_date, &strong_sse, &strong_cn2000).unwrap();
    assert_eq!(strong.state, "strong");
    assert_eq!(strong.score_based_state, "strong");
    assert_eq!(strong.rule_based_state, "strong");
    assert_eq!(strong.vote_based_state, "strong");
    assert!(strong.reason.contains("双指数共振偏强"));
    assert!(strong.total_score >= 10.0);

    let weak_sse = index_history("000001.SH", pick_date, |idx| 220.0 - idx as f64 * 1.9);
    let weak_cn2000 = index_history("399303.SZ", pick_date, |idx| 180.0 - idx as f64 * 1.5);
    let weak = evaluate_market_environment(pick_date, &weak_sse, &weak_cn2000).unwrap();
    assert_eq!(weak.state, "weak");
    assert_eq!(weak.score_based_state, "weak");
    assert_eq!(weak.rule_based_state, "weak");
    assert_eq!(weak.vote_based_state, "weak");
    assert!(weak.reason.contains("双指数共振偏弱"));
    assert!(weak.total_score <= -4.0);

    let neutral = evaluate_market_environment(pick_date, &strong_sse, &weak_cn2000).unwrap();
    assert_eq!(neutral.state, "neutral");
    assert_eq!(neutral.score_based_state, "neutral");
    assert_eq!(neutral.rule_based_state, "neutral");
    assert_eq!(neutral.vote_based_state, "neutral");
    assert!(neutral.reason.contains("环境中立"));
}

#[test]
fn evaluated_environment_failure_without_history_returns_error() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let err = ensure_market_environment_for_test(temp.path(), pick_date, None, None, || {
        anyhow::bail!("index history unavailable")
    })
    .unwrap_err();

    assert!(err.to_string().contains("index history unavailable"));
    assert!(!temp.path().join("environment/history.jsonl").exists());
}

#[test]
fn invalid_environment_state_returns_error() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();

    let err = ensure_market_environment_for_test(
        temp.path(),
        pick_date,
        Some("bullish".to_string()),
        None,
        || panic!("invalid manual state should not evaluate"),
    )
    .unwrap_err();

    assert!(
        err.to_string()
            .contains("Unsupported environment state 'bullish'")
    );
}

fn index_history(
    ts_code: &str,
    pick_date: NaiveDate,
    close_at: impl Fn(usize) -> f64,
) -> Vec<MarketRow> {
    (0..80)
        .map(|idx| {
            let trade_date = pick_date - chrono::Duration::days((79 - idx) as i64);
            let close = close_at(idx);
            MarketRow {
                ts_code: ts_code.to_string(),
                trade_date,
                open: close,
                high: close,
                low: close,
                close,
                vol: 1_000_000.0,
                turnover_rate: None,
                adj_factor: None,
                db_factors: Default::default(),
            }
        })
        .collect()
}

fn window_market_row(trade_date: NaiveDate, close: f64, vol: f64) -> MarketRow {
    MarketRow {
        ts_code: "000001.SZ".to_string(),
        trade_date,
        open: close - 0.8,
        high: close,
        low: close - 1.0,
        close,
        vol,
        turnover_rate: Some(vol / 100.0),
        adj_factor: None,
        db_factors: Default::default(),
    }
}

#[test]
fn environment_without_cache_is_derived_from_in_memory_window() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
    let window_start = stock_select::screening::prepared_cache_start_date(pick_date);

    let resolved = stock_select::environment::resolve_window_environment_with_loader(
        temp.path(),
        pick_date,
        "fixture.duckdb",
        |_duckdb_path, start_date, end_date| {
            assert_eq!(start_date, window_start);
            assert_eq!(end_date, pick_date);
            Ok((0..365)
                .map(|offset| {
                    window_market_row(
                        window_start + Duration::days(offset),
                        10.0 + offset as f64 * 0.01,
                        100.0,
                    )
                })
                .chain(std::iter::once(window_market_row(pick_date, 12.52, 100.0)))
                .collect::<Vec<MarketRow>>())
        },
    )
    .unwrap();

    assert_eq!(resolved.source, "prepared_market_state");
    assert!(temp.path().join("environment/history.jsonl").exists());
}

#[test]
fn environment_window_fallback_fails_when_window_is_too_short() {
    let temp = tempfile::tempdir().unwrap();
    let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();

    let result = stock_select::environment::resolve_window_environment_with_loader(
        temp.path(),
        pick_date,
        "fixture.duckdb",
        |_duckdb_path, _start, _end| Ok(vec![window_market_row(pick_date, 12.52, 100.0)]),
    );

    assert!(result.is_err());
    assert!(!temp.path().join("environment/history.jsonl").exists());
}
