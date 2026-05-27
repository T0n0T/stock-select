use std::collections::BTreeMap;

use chrono::NaiveDate;

use crate::indicators::{barslast, count_dynamic, ema, rolling_mean, rolling_sum};
use crate::model::{Candidate, PreparedRow};
use crate::strategies::{StrategyOutput, group_by_symbol, sort_candidates};

pub fn run(rows: &[PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let grouped = group_by_symbol(rows);
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
            increment(&mut stats, "fail_no_pick_date");
            continue;
        };
        increment(&mut stats, "eligible");
        if idx < 2 {
            increment(&mut stats, "fail_insufficient_history");
            continue;
        }
        let signals = build_signals(&history[..=idx], code);
        let signal = signals[idx].clone();
        if let Some(signal) = signal {
            candidates.push(Candidate {
                code: code.to_string(),
                pick_date,
                close: row.close,
                turnover_n: row.turnover_n,
                signal: Some(signal.clone()),
                yellow_b1: None,
            });
            increment(&mut stats, "selected");
            match signal.as_str() {
                "B2" => increment(&mut stats, "selected_b2"),
                "B3" => increment(&mut stats, "selected_b3"),
                "B3+" => increment(&mut stats, "selected_b3_plus"),
                _ => {}
            }
        } else {
            increment(&mut stats, "fail_no_signal");
        }
    }
    sort_candidates(&mut candidates);
    StrategyOutput { candidates, stats }
}

fn build_signals(history: &[&PreparedRow], code: &str) -> Vec<Option<String>> {
    let len = history.len();
    let mut raw_b2 = vec![false; len];
    let mut cur_b2 = vec![false; len];
    let mut cur_b3 = vec![false; len];
    let mut cur_b3_plus = vec![false; len];
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
        let is_new = idx + 1 <= 114;
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
            let is_new = idx + 1 <= 114;
            if is_new {
                return true;
            }
            let Some(lt) = lt_r[idx] else {
                return false;
            };
            let honeymoon = c_days[idx] >= 0.0 && c_days[idx] <= 30.0 && st_l[idx] > lt;
            let breakaway = st_l[idx] > lt * 1.03;
            let lt_stable = flip_c[idx].unwrap_or(0.0) <= 2.0;
            let support = history[idx].close >= lt * 0.95;
            honeymoon
                || breakaway
                || (st_l[idx] > lt && history[idx].close > lt && lt_stable && support)
        })
        .collect::<Vec<_>>();
    let above_lt = (0..len)
        .map(|idx| {
            let is_new = idx + 1 <= 114;
            is_new || lt_r[idx].is_some_and(|lt| history[idx].close > lt)
        })
        .collect::<Vec<_>>();
    let amp_limit = if code.starts_with("688") || code.starts_with("300") {
        12.0
    } else {
        8.0
    };

    for idx in 2..len {
        let row = history[idx];
        let prev = history[idx - 1];
        let pct = (row.close - prev.close) / prev.close * 100.0;
        let prev_pct = (prev.close - history[idx - 2].close) / history[idx - 2].close * 100.0;
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

    let j_up: Vec<bool> = (0..len)
        .map(|idx| idx > 0 && history[idx].j > history[idx - 1].j)
        .collect();
    let j_turn_up: Vec<bool> = (0..len)
        .map(|idx| idx > 1 && j_up[idx] && !j_up[idx - 1])
        .collect();
    let up_days = barslast(&j_turn_up);
    let raw_unique = count_dynamic(
        &raw_b2,
        &up_days.iter().map(|value| value + 1.0).collect::<Vec<_>>(),
    );
    for idx in 0..len {
        cur_b2[idx] = raw_b2[idx] && raw_unique[idx] == 1.0;
    }

    for idx in 1..len {
        let row = history[idx];
        let prev = history[idx - 1];
        let pct = (row.close - prev.close) / prev.close * 100.0;
        let amp = (row.high - row.low) / prev.close * 100.0;
        let shake = pct.abs() < 5.05 && amp < amp_limit;
        let j_up_now = row.j > prev.j;
        cur_b3[idx] = cur_b2[idx - 1]
            && shake
            && row.volume <= prev.volume * 0.9
            && j_up_now
            && tr_ok[idx]
            && above_lt[idx];
        cur_b3_plus[idx] =
            cur_b3[idx] && row.volume <= prev.volume * 0.52 && row.close > prev.close;
    }

    (0..len)
        .map(|idx| {
            if cur_b2[idx] {
                Some("B2".to_string())
            } else if cur_b3_plus[idx] {
                Some("B3+".to_string())
            } else if cur_b3[idx] {
                Some("B3".to_string())
            } else {
                None
            }
        })
        .collect()
}

fn increment(stats: &mut BTreeMap<String, usize>, key: &str) {
    *stats.entry(key.to_string()).or_insert(0) += 1;
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

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
        }
    }

    #[test]
    fn selects_b2_signal() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 3).unwrap();
        let rows = vec![
            row(1, 10.0, 100.0, 30.0),
            row(2, 10.1, 90.0, 35.0),
            row(3, 10.6, 120.0, 45.0),
        ];
        let output = run(&rows, pick);
        assert_eq!(output.candidates.len(), 1);
        assert_eq!(output.candidates[0].signal.as_deref(), Some("B2"));
    }

    #[test]
    fn b2_no_pick_date_counts_failure() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 4).unwrap();
        let output = run(&[row(1, 10.0, 100.0, 30.0), row(2, 10.1, 90.0, 35.0)], pick);
        assert!(output.candidates.is_empty());
        assert_eq!(output.stats["fail_no_pick_date"], 1);
    }
}
