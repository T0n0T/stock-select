use std::collections::BTreeMap;

use chrono::NaiveDate;

use crate::model::{Candidate, PreparedRow};
use crate::strategies::b2::build_b2_signal_series;
use crate::strategies::{StrategyOutput, group_refs_by_symbol, sort_candidates};

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct B3SignalSeries {
    pub(crate) cur_b3: Vec<bool>,
    pub(crate) cur_b3_plus: Vec<bool>,
}

pub fn run_b3_strategy(rows: &[PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let refs = rows.iter().collect::<Vec<_>>();
    run_b3_strategy_from_refs(&refs, pick_date)
}

pub fn run_b3_strategy_from_refs(rows: &[&PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let grouped = group_refs_by_symbol(rows);
    let mut stats = BTreeMap::from([
        ("total_symbols".to_string(), grouped.len()),
        ("eligible".to_string(), 0),
        ("fail_no_pick_date".to_string(), 0),
        ("fail_insufficient_history".to_string(), 0),
        ("fail_no_signal".to_string(), 0),
        ("selected".to_string(), 0),
        ("selected_b2".to_string(), 0),
        ("selected_b3".to_string(), 0),
        ("selected_b3_plus".to_string(), 0),
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
        if idx < 3 {
            *stats
                .entry("fail_insufficient_history".to_string())
                .or_default() += 1;
            continue;
        }

        let active_history = &history[..=idx];
        let signals = build_b3_signal_series(active_history, code);
        let signal = if signals.cur_b3_plus[idx] {
            Some("B3+")
        } else if signals.cur_b3[idx] {
            Some("B3")
        } else {
            None
        };
        if let Some(signal) = signal {
            candidates.push(Candidate {
                code: code.to_string(),
                pick_date,
                close: row.close,
                turnover_n: row.turnover_n,
                signal: Some(signal.to_string()),
                yellow_b1: None,
            });
            *stats.entry("selected".to_string()).or_default() += 1;
            match signal {
                "B3+" => *stats.entry("selected_b3_plus".to_string()).or_default() += 1,
                "B3" => *stats.entry("selected_b3".to_string()).or_default() += 1,
                _ => {}
            }
        } else {
            *stats.entry("fail_no_signal".to_string()).or_default() += 1;
        }
    }

    sort_candidates(&mut candidates);
    StrategyOutput { candidates, stats }
}

pub(crate) fn build_b3_signal_series(history: &[&PreparedRow], code: &str) -> B3SignalSeries {
    let len = history.len();
    let b2 = build_b2_signal_series(history);
    let amp_limit = if code.starts_with("688") || code.starts_with("300") {
        12.0
    } else {
        8.0
    };
    let mut cur_b3 = vec![false; len];
    let mut cur_b3_plus = vec![false; len];

    for idx in 1..len {
        let row = history[idx];
        let prev = history[idx - 1];
        let pct = (row.close - prev.close) / prev.close * 100.0;
        let amp = (row.high - row.low) / prev.close * 100.0;
        let shake = pct.abs() < 5.05 && amp < amp_limit;
        let j_up_now = row.j > prev.j;
        cur_b3[idx] = b2.cur_b2[idx - 1]
            && shake
            && row.volume <= prev.volume * 0.9
            && j_up_now
            && b2.tr_ok[idx]
            && b2.above_lt[idx];
        cur_b3_plus[idx] =
            cur_b3[idx] && row.volume <= prev.volume * 0.52 && row.close > prev.close;
    }

    B3SignalSeries {
        cur_b3,
        cur_b3_plus,
    }
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
            low: close - 0.5,
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
    fn b3_strategy_selects_b3_plus_after_b2_setup() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 4).unwrap();
        let rows = vec![
            row(1, 10.0, 1000.0, 30.0),
            row(2, 10.1, 900.0, 35.0),
            row(3, 10.6, 1200.0, 45.0),
            row(4, 10.7, 600.0, 46.0),
        ];

        let output = run_b3_strategy(&rows, pick);

        assert_eq!(output.candidates.len(), 1);
        assert_eq!(output.candidates[0].signal.as_deref(), Some("B3+"));
        assert_eq!(output.stats["selected_b3"], 0);
        assert_eq!(output.stats["selected_b3_plus"], 1);
    }

    #[test]
    fn b3_ref_strategy_matches_owned_slice_strategy() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 4).unwrap();
        let rows = vec![
            row(1, 10.0, 1000.0, 30.0),
            row(2, 10.1, 900.0, 35.0),
            row(3, 10.6, 1200.0, 45.0),
            row(4, 10.7, 600.0, 46.0),
        ];
        let refs = rows.iter().collect::<Vec<_>>();

        assert_eq!(
            run_b3_strategy_from_refs(&refs, pick),
            run_b3_strategy(&rows, pick)
        );
    }
}
