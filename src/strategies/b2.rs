use std::collections::BTreeMap;

use chrono::NaiveDate;

use crate::indicators::{barslast, count_dynamic, ema, rolling_mean, rolling_sum};
use crate::model::{Candidate, PreparedRow};
use crate::strategies::{
    StrategyOutput, group_refs_by_symbol, latest_monthly_macd_dea_positive, sort_candidates,
};

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct B2SignalSeries {
    pub(crate) raw_b2: Vec<bool>,
    pub(crate) raw_b2_count: Vec<f64>,
    pub(crate) cur_b2: Vec<bool>,
    pub(crate) tr_ok: Vec<bool>,
    pub(crate) above_lt: Vec<bool>,
}

pub fn run_b2_strategy(rows: &[PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let refs = rows.iter().collect::<Vec<_>>();
    run_b2_strategy_from_refs(&refs, pick_date)
}

pub fn run_b2_strategy_from_refs(rows: &[&PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let grouped = group_refs_by_symbol(rows);
    let mut stats = BTreeMap::from([
        ("total_symbols".to_string(), grouped.len()),
        ("eligible".to_string(), 0),
        ("fail_no_pick_date".to_string(), 0),
        ("fail_insufficient_history".to_string(), 0),
        ("fail_no_signal".to_string(), 0),
        ("fail_monthly_macd_dea".to_string(), 0),
        ("selected".to_string(), 0),
        ("selected_b2".to_string(), 0),
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
        if idx < 2 {
            *stats
                .entry("fail_insufficient_history".to_string())
                .or_default() += 1;
            continue;
        }
        let active_history = &history[..=idx];
        let signals = build_b2_signal_series(active_history);
        if signals.cur_b2[idx] {
            if !latest_monthly_macd_dea_positive(active_history) {
                *stats
                    .entry("fail_monthly_macd_dea".to_string())
                    .or_default() += 1;
                continue;
            }
            candidates.push(Candidate {
                code: code.to_string(),
                pick_date,
                close: row.close,
                turnover_n: row.turnover_n,
                signal: Some("B2".to_string()),
                yellow_b1: None,
            });
            *stats.entry("selected".to_string()).or_default() += 1;
            *stats.entry("selected_b2".to_string()).or_default() += 1;
        } else {
            *stats.entry("fail_no_signal".to_string()).or_default() += 1;
        }
    }
    sort_candidates(&mut candidates);
    StrategyOutput { candidates, stats }
}

pub(crate) fn build_b2_signal_series(history: &[&PreparedRow]) -> B2SignalSeries {
    let len = history.len();
    let close = history.iter().map(|row| row.close).collect::<Vec<_>>();
    let st_l = ema(&ema(&close, 10), 10);
    let ma14 = rolling_mean(&close, 14, 14);
    let ma28 = rolling_mean(&close, 28, 28);
    let ma57 = rolling_mean(&close, 57, 57);
    let ma114 = rolling_mean(&close, 114, 114);
    let lt_r = (0..len)
        .map(|idx| match (ma14[idx], ma28[idx], ma57[idx], ma114[idx]) {
            (Some(a), Some(b), Some(c), Some(d)) if idx + 1 > 114 => Some((a + b + c + d) / 4.0),
            _ => None,
        })
        .collect::<Vec<_>>();
    let cross_up = (0..len)
        .map(|idx| {
            idx > 0
                && matches!(
                    (lt_r[idx], lt_r[idx - 1]),
                    (Some(cur), Some(prev)) if st_l[idx] > cur && st_l[idx - 1] <= prev
                )
        })
        .collect::<Vec<_>>();
    let c_days = barslast(&cross_up);
    let mut lt_dir = vec![1.0; len];
    for idx in 0..len {
        let is_new = idx < 114;
        if !is_new {
            lt_dir[idx] = if idx > 0
                && lt_r[idx].is_some()
                && lt_r[idx - 1].is_some()
                && lt_r[idx].unwrap() >= lt_r[idx - 1].unwrap() * 0.9999
            {
                1.0
            } else {
                -1.0
            };
        }
    }
    let flip_values = (0..len)
        .map(|idx| {
            if idx > 0 && lt_dir[idx] != lt_dir[idx - 1] {
                1.0
            } else {
                0.0
            }
        })
        .collect::<Vec<_>>();
    let flip_c = rolling_sum(&flip_values, 30, 1);
    let tr_ok = (0..len)
        .map(|idx| {
            let is_new = idx < 114;
            if is_new {
                return true;
            }
            let Some(lt) = lt_r[idx] else {
                return false;
            };
            b2_trend_ok_decision(
                c_days[idx] >= 0.0 && c_days[idx] <= 30.0,
                c_days[idx],
                st_l[idx],
                lt,
                flip_c[idx].unwrap_or(0.0),
                history[idx].close,
            )
        })
        .collect::<Vec<_>>();
    let above_lt = (0..len)
        .map(|idx| {
            let is_new = idx < 114;
            is_new || lt_r[idx].is_some_and(|lt| history[idx].close > lt)
        })
        .collect::<Vec<_>>();
    let mut raw_b2 = vec![false; len];
    for idx in 2..len {
        let row = history[idx];
        let prev = history[idx - 1];
        let prev2 = history[idx - 2];
        let pct = (row.close - prev.close) / prev.close * 100.0;
        let prev_pct = (prev.close - prev2.close) / prev2.close * 100.0;
        let pre_ok = prev_pct < 3.7 && prev.j < 39.0;
        let up_shadow = row.high - row.close;
        let ef_body = row.close - row.open.min(prev.close);
        let k_shape = up_shadow <= ef_body && row.close > row.open;
        let j_up = row.j > prev.j;
        raw_b2[idx] = pct >= 3.7
            && row.volume > prev.volume
            && k_shape
            && pre_ok
            && j_up
            && tr_ok[idx]
            && above_lt[idx];
    }
    let j_up = (0..len)
        .map(|idx| idx > 0 && history[idx].j > history[idx - 1].j)
        .collect::<Vec<_>>();
    let j_turn_up = (0..len)
        .map(|idx| idx > 1 && j_up[idx] && !j_up[idx - 1])
        .collect::<Vec<_>>();
    let up_days = barslast(&j_turn_up);
    let raw_b2_count = count_dynamic(
        &raw_b2,
        &up_days.iter().map(|value| value + 1.0).collect::<Vec<_>>(),
    );
    let cur_b2 = raw_b2
        .iter()
        .zip(raw_b2_count.iter())
        .map(|(raw, count)| *raw && *count == 1.0)
        .collect::<Vec<_>>();
    B2SignalSeries {
        raw_b2,
        raw_b2_count,
        cur_b2,
        tr_ok,
        above_lt,
    }
}

fn b2_trend_ok_decision(
    crossed_within_30_days: bool,
    _cross_days: f64,
    st_l: f64,
    lt_r: f64,
    flip_count_30: f64,
    close: f64,
) -> bool {
    let honeymoon = crossed_within_30_days && st_l > lt_r;
    let breakaway = st_l > lt_r * 1.03;
    let lt_stable = flip_count_30 <= 2.0;
    let support = close >= lt_r * 0.95;
    honeymoon || breakaway || (st_l > lt_r && close > lt_r && lt_stable && support)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(day: u32, close: f64, volume: f64, j: f64) -> PreparedRow {
        PreparedRow {
            ts_code: "000001.SZ".to_string(),
            trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
            open: close - 0.8,
            high: close,
            low: close - 1.0,
            close,
            volume,
            turnover_n: 1000.0 + day as f64,
            turnover_rate: None,
            k: 20.0,
            d: 20.0,
            j,
            zxdq: Some(10.5),
            zxdkx: Some(10.0),
            dif: 0.1,
            dea: 0.0,
            macd_hist: 0.1,
            ma25: Some(10.0),
            ma60: Some(9.0),
            ma144: Some(8.0),
            chg_d: Some(1.0),
            weekly_ma_bull: true,
            max_vol_not_bearish: true,
            v_shrink: true,
            safe_mode: true,
            lt_filter: true,
            yellow_b1: false,
            db_factors: Default::default(),
        }
    }

    #[test]
    fn b2_trend_decision_rejects_unstable_non_breakaway_trend() {
        assert!(!b2_trend_ok_decision(false, 40.0, 101.0, 100.0, 3.0, 101.0,));
    }

    #[test]
    fn b2_trend_decision_accepts_honeymoon_breakaway_and_stable_support() {
        assert!(b2_trend_ok_decision(true, 10.0, 101.0, 100.0, 9.0, 101.0,));
        assert!(b2_trend_ok_decision(false, 40.0, 104.0, 100.0, 9.0, 90.0,));
        assert!(b2_trend_ok_decision(false, 40.0, 101.0, 100.0, 2.0, 101.0,));
    }

    #[test]
    fn b2_strategy_returns_structured_output_with_b2_only_stats() {
        let first = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
        let pick = first + chrono::Duration::days(89);
        let rows = monthly_macd_rows(first, true);

        let output = run_b2_strategy(&rows, pick);

        assert_eq!(output.candidates.len(), 1);
        assert_eq!(output.candidates[0].signal.as_deref(), Some("B2"));
        assert_eq!(output.stats["selected"], 1);
        assert_eq!(output.stats["selected_b2"], 1);
        assert!(!output.stats.contains_key("selected_b3"));
        assert!(!output.stats.contains_key("selected_b3_plus"));
    }

    #[test]
    fn b2_strategy_rejects_signal_when_monthly_macd_dea_is_not_positive() {
        let first = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
        let pick = first + chrono::Duration::days(89);
        let rows = monthly_macd_rows(first, false);

        let output = run_b2_strategy(&rows, pick);

        assert!(output.candidates.is_empty());
        assert_eq!(output.stats["selected_b2"], 0);
        assert_eq!(output.stats["fail_no_signal"], 0);
        assert_eq!(output.stats["fail_monthly_macd_dea"], 1);
    }

    #[test]
    fn b2_strategy_accepts_signal_when_monthly_macd_dea_is_positive() {
        let first = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
        let pick = first + chrono::Duration::days(89);
        let rows = monthly_macd_rows(first, true);

        let output = run_b2_strategy(&rows, pick);

        assert_eq!(output.candidates.len(), 1);
        assert_eq!(output.candidates[0].signal.as_deref(), Some("B2"));
    }

    #[test]
    fn b2_ref_strategy_matches_owned_slice_strategy() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 3).unwrap();
        let rows = vec![
            row(1, 10.0, 100.0, 30.0),
            row(2, 10.1, 90.0, 35.0),
            row(3, 10.6, 120.0, 45.0),
        ];
        let refs = rows.iter().collect::<Vec<_>>();

        assert_eq!(
            run_b2_strategy_from_refs(&refs, pick),
            run_b2_strategy(&rows, pick)
        );
    }

    #[test]
    fn b2_signal_series_keeps_only_first_raw_b2_in_j_up_cycle() {
        let rows = vec![
            row(1, 10.0, 1000.0, 30.0),
            row(2, 10.1, 1000.0, 32.0),
            row(3, 10.5, 1300.0, 35.0),
            row(4, 10.6, 1100.0, 36.0),
            row(5, 11.0, 1400.0, 38.0),
        ];
        let history = rows.iter().collect::<Vec<_>>();

        let signals = build_b2_signal_series(&history);

        assert_eq!(signals.raw_b2, vec![false, false, true, false, true]);
        assert_eq!(signals.raw_b2_count[4], 2.0);
        assert_eq!(signals.cur_b2, vec![false, false, true, false, false]);
    }

    fn monthly_macd_rows(first: NaiveDate, constructive_monthly: bool) -> Vec<PreparedRow> {
        let len = 90;
        let mut rows = (0..len)
            .map(|offset| {
                let close = if constructive_monthly {
                    10.0 + offset as f64 * 0.03
                } else {
                    20.0 - offset as f64 * 0.03
                };
                row_at_date(
                    first + chrono::Duration::days(offset as i64),
                    close,
                    1000.0,
                    25.0,
                )
            })
            .collect::<Vec<_>>();
        let prev2 = len - 3;
        let prev = len - 2;
        let latest = len - 1;
        rows[prev2].close = rows[prev].close - 0.05;
        rows[prev2].high = rows[prev2].close;
        rows[prev2].open = rows[prev2].close - 0.2;
        rows[prev2].j = 28.0;
        rows[prev].close = rows[prev2].close + 0.10;
        rows[prev].high = rows[prev].close;
        rows[prev].open = rows[prev].close - 0.2;
        rows[prev].j = 32.0;
        rows[latest].close = rows[prev].close * 1.04;
        rows[latest].high = rows[latest].close;
        rows[latest].open = rows[latest].close - 0.8;
        rows[latest].volume = rows[prev].volume + 500.0;
        rows[latest].j = 45.0;
        rows
    }

    fn row_at_date(trade_date: NaiveDate, close: f64, volume: f64, j: f64) -> PreparedRow {
        PreparedRow {
            trade_date,
            close,
            high: close,
            open: close - 0.8,
            low: close - 1.0,
            volume,
            ..row(1, close, volume, j)
        }
    }
}
