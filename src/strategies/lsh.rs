use std::collections::BTreeMap;

use chrono::{Datelike, NaiveDate};

use crate::indicators::macd;
use crate::model::{Candidate, PreparedRow};
use crate::strategies::{StrategyOutput, group_refs_by_symbol, sort_candidates};

pub fn run_lsh_strategy(rows: &[PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let refs = rows.iter().collect::<Vec<_>>();
    run_lsh_strategy_from_refs(&refs, pick_date)
}

pub fn run_lsh_strategy_from_refs(rows: &[&PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let grouped = group_refs_by_symbol(rows);
    let mut stats = BTreeMap::from([
        ("total_symbols".to_string(), grouped.len()),
        ("eligible".to_string(), 0),
        ("fail_no_pick_date".to_string(), 0),
        ("fail_insufficient_history".to_string(), 0),
        ("fail_daily_shape".to_string(), 0),
        ("fail_macd".to_string(), 0),
        ("selected".to_string(), 0),
        ("selected_lsh".to_string(), 0),
    ]);
    let mut candidates = Vec::new();

    for (code, history) in grouped {
        let Some((idx, row)) = history
            .iter()
            .enumerate()
            .find(|(_idx, row)| row.trade_date == pick_date)
        else {
            *stats.entry("fail_no_pick_date".to_string()).or_default() += 1;
            continue;
        };
        *stats.entry("eligible".to_string()).or_default() += 1;
        if idx < 24 || row.ma25.is_none() {
            *stats
                .entry("fail_insufficient_history".to_string())
                .or_default() += 1;
            continue;
        }

        let ma25 = row.ma25.unwrap();
        if !(row.low < ma25 && row.close > row.open && row.close > ma25) {
            *stats.entry("fail_daily_shape".to_string()).or_default() += 1;
            continue;
        }

        let active_history = &history[..=idx];
        if !weekly_monthly_macd_positive(active_history) {
            *stats.entry("fail_macd".to_string()).or_default() += 1;
            continue;
        }

        candidates.push(Candidate {
            code: code.to_string(),
            pick_date,
            close: row.close,
            turnover_n: row.turnover_n,
            signal: Some("LSH".to_string()),
            yellow_b1: None,
        });
        *stats.entry("selected".to_string()).or_default() += 1;
        *stats.entry("selected_lsh".to_string()).or_default() += 1;
    }

    sort_candidates(&mut candidates);
    StrategyOutput { candidates, stats }
}

fn weekly_monthly_macd_positive(history: &[&PreparedRow]) -> bool {
    latest_macd_hist_and_dea_positive(&period_closes_by_week(history))
        && latest_macd_hist_and_dea_positive(&period_closes_by_month(history))
}

fn latest_macd_hist_and_dea_positive(closes: &[f64]) -> bool {
    if closes.is_empty() {
        return false;
    }
    let (_dif, dea, hist) = macd(closes, 12, 26, 9);
    hist.last()
        .zip(dea.last())
        .is_some_and(|(hist, dea)| hist.is_finite() && dea.is_finite() && *hist > 0.0 && *dea > 0.0)
}

fn period_closes_by_week(history: &[&PreparedRow]) -> Vec<f64> {
    let mut closes = BTreeMap::<(i32, u32), f64>::new();
    for row in history {
        let week = row.trade_date.iso_week();
        closes.insert((week.year(), week.week()), row.close);
    }
    closes.into_values().collect()
}

fn period_closes_by_month(history: &[&PreparedRow]) -> Vec<f64> {
    let mut closes = BTreeMap::<(i32, u32), f64>::new();
    for row in history {
        closes.insert((row.trade_date.year(), row.trade_date.month()), row.close);
    }
    closes.into_values().collect()
}

#[cfg(test)]
mod tests {
    use chrono::{Duration, NaiveDate};

    use crate::model::PreparedRow;
    use crate::strategies::lsh::run_lsh_strategy;

    #[test]
    fn lsh_strategy_selects_pullback_reclaim_with_positive_weekly_and_monthly_macd() {
        let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
        let pick_date = first_date + Duration::days(429);
        let rows = rows(first_date, 430, true);

        let output = run_lsh_strategy(&rows, pick_date);

        assert_eq!(output.candidates.len(), 1);
        assert_eq!(output.candidates[0].code, "000001.SZ");
        assert_eq!(output.candidates[0].signal.as_deref(), Some("LSH"));
        assert_eq!(output.stats["selected_lsh"], 1);
    }

    #[test]
    fn lsh_strategy_rejects_when_weekly_or_monthly_macd_hist_is_not_positive() {
        let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
        let pick_date = first_date + Duration::days(429);
        let rows = rows(first_date, 430, false);

        let output = run_lsh_strategy(&rows, pick_date);

        assert!(output.candidates.is_empty());
        assert_eq!(output.stats["fail_macd"], 1);
    }

    #[test]
    fn lsh_strategy_rejects_when_daily_ma25_reclaim_shape_is_missing() {
        let first_date = NaiveDate::from_ymd_opt(2025, 1, 1).unwrap();
        let pick_date = first_date + Duration::days(429);
        let mut rows = rows(first_date, 430, true);
        let latest = rows.last_mut().unwrap();
        latest.low = latest.ma25.unwrap() + 0.1;

        let output = run_lsh_strategy(&rows, pick_date);

        assert!(output.candidates.is_empty());
        assert_eq!(output.stats["fail_daily_shape"], 1);
    }

    fn rows(
        first_date: NaiveDate,
        len: usize,
        constructive_weekly_monthly: bool,
    ) -> Vec<PreparedRow> {
        (0..len)
            .map(|offset| {
                let trade_date = first_date + Duration::days(offset as i64);
                let base_close = if constructive_weekly_monthly {
                    10.0 + offset as f64 * 0.03 + (offset as f64 * offset as f64) * 0.0001
                } else {
                    50.0 - offset as f64 * 0.03
                };
                let is_latest = offset + 1 == len;
                let close = if is_latest {
                    base_close + 1.0
                } else {
                    base_close
                };
                PreparedRow {
                    ts_code: "000001.SZ".to_string(),
                    trade_date,
                    open: if is_latest { close - 0.5 } else { close - 0.1 },
                    high: close + 0.2,
                    low: if is_latest { close - 1.5 } else { close - 0.2 },
                    close,
                    volume: 1000.0,
                    turnover_n: 1000.0 * close,
                    turnover_rate: Some(1.0),
                    k: 50.0,
                    d: 40.0,
                    j: 45.0,
                    zxdq: Some(close),
                    zxdkx: Some(close - 0.5),
                    dif: 0.3,
                    dea: 0.2,
                    macd_hist: 0.1,
                    ma25: Some(if is_latest { close - 0.7 } else { close - 0.5 }),
                    ma60: Some(close - 1.0),
                    ma144: Some(close - 1.5),
                    chg_d: None,
                    weekly_ma_bull: true,
                    max_vol_not_bearish: true,
                    v_shrink: false,
                    safe_mode: true,
                    lt_filter: true,
                    yellow_b1: false,
                    db_factors: Default::default(),
                }
            })
            .collect()
    }
}
