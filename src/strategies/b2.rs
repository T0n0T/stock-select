use std::collections::BTreeMap;

use chrono::NaiveDate;

use crate::model::{Candidate, PreparedRow};

pub fn run_b2_strategy(
    rows: &[PreparedRow],
    pick_date: NaiveDate,
) -> (Vec<Candidate>, BTreeMap<String, usize>) {
    let mut grouped = BTreeMap::<&str, Vec<&PreparedRow>>::new();
    for row in rows {
        grouped.entry(row.ts_code.as_str()).or_default().push(row);
    }
    let mut stats = BTreeMap::from([
        ("total_symbols".to_string(), grouped.len()),
        ("eligible".to_string(), 0),
        ("fail_no_pick_date".to_string(), 0),
        ("fail_insufficient_history".to_string(), 0),
        ("fail_no_signal".to_string(), 0),
        ("selected".to_string(), 0),
        ("selected_b2".to_string(), 0),
    ]);
    let mut candidates = Vec::new();
    for (code, mut history) in grouped {
        history.sort_by_key(|row| row.trade_date);
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
        let selected = raw_b2_basic_condition(&history, idx)
            && raw_b2_count_in_current_j_up_cycle(&history, idx) == 1;
        if selected {
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
    candidates.sort_by(|left, right| left.code.cmp(&right.code));
    (candidates, stats)
}

fn raw_b2_basic_condition(history: &[&PreparedRow], idx: usize) -> bool {
    if idx < 2 {
        return false;
    }
    let row = history[idx];
    let prev = history[idx - 1];
    let prev2 = history[idx - 2];
    let pct = (row.close - prev.close) / prev.close * 100.0;
    let prev_pct = (prev.close - prev2.close) / prev2.close * 100.0;
    let up_shadow = row.high - row.close;
    let ef_body = row.close - row.open.min(prev.close);
    pct >= 3.7
        && row.volume > prev.volume
        && up_shadow <= ef_body
        && row.close > row.open
        && prev_pct < 3.7
        && prev.j < 39.0
        && row.j > prev.j
        && above_long_term_reference(history, idx)
        && b2_trend_ok(history, idx)
}

fn above_long_term_reference(history: &[&PreparedRow], idx: usize) -> bool {
    if idx < 114 {
        return true;
    }
    let Some(ma14) = rolling_close_mean_at(history, idx, 14) else {
        return false;
    };
    let Some(ma28) = rolling_close_mean_at(history, idx, 28) else {
        return false;
    };
    let Some(ma57) = rolling_close_mean_at(history, idx, 57) else {
        return false;
    };
    let Some(ma114) = rolling_close_mean_at(history, idx, 114) else {
        return false;
    };
    let lt_r = (ma14 + ma28 + ma57 + ma114) / 4.0;
    history[idx].close > lt_r
}

fn rolling_close_mean_at(history: &[&PreparedRow], idx: usize, window: usize) -> Option<f64> {
    let start = idx.checked_add(1)?.checked_sub(window)?;
    let sum = history[start..=idx]
        .iter()
        .map(|row| row.close)
        .sum::<f64>();
    Some(sum / window as f64)
}

fn b2_trend_ok(history: &[&PreparedRow], idx: usize) -> bool {
    if idx < 114 {
        return true;
    }
    let close = history.iter().map(|row| row.close).collect::<Vec<_>>();
    let st_l = ema_values(&ema_values(&close, 10), 10);
    let lt_r = long_term_reference_series(history);
    let flip_count_30 = long_term_direction_flip_count(&lt_r, idx, 30);
    let cross_days = days_since_st_crossed_above_lt(&st_l, &lt_r, idx);
    let Some(lt) = lt_r[idx] else {
        return false;
    };
    b2_trend_ok_decision(
        cross_days.is_some_and(|days| days <= 30.0),
        cross_days.unwrap_or(f64::INFINITY),
        st_l[idx],
        lt,
        flip_count_30,
        history[idx].close,
    )
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

fn long_term_reference_series(history: &[&PreparedRow]) -> Vec<Option<f64>> {
    (0..history.len())
        .map(|idx| {
            if idx + 1 <= 114 {
                return None;
            }
            Some(
                [14, 28, 57, 114]
                    .into_iter()
                    .map(|window| rolling_close_mean_at(history, idx, window))
                    .collect::<Option<Vec<_>>>()?
                    .into_iter()
                    .sum::<f64>()
                    / 4.0,
            )
        })
        .collect()
}

fn long_term_direction_flip_count(lt_r: &[Option<f64>], idx: usize, window: usize) -> f64 {
    let start = idx.saturating_add(1).saturating_sub(window);
    (start..=idx)
        .filter(|current| {
            *current > 0
                && long_term_direction(lt_r, *current)
                    != long_term_direction(lt_r, current.saturating_sub(1))
        })
        .count() as f64
}

fn long_term_direction(lt_r: &[Option<f64>], idx: usize) -> f64 {
    if idx < 114 {
        return 1.0;
    }
    match (
        lt_r.get(idx).copied().flatten(),
        lt_r.get(idx - 1).copied().flatten(),
    ) {
        (Some(current), Some(previous)) if current >= previous * 0.9999 => 1.0,
        _ => -1.0,
    }
}

fn days_since_st_crossed_above_lt(st_l: &[f64], lt_r: &[Option<f64>], idx: usize) -> Option<f64> {
    (1..=idx)
        .rev()
        .find(|current| {
            matches!(
                (lt_r[*current], lt_r[current - 1]),
                (Some(current_lt), Some(previous_lt))
                    if st_l[*current] > current_lt && st_l[current - 1] <= previous_lt
            )
        })
        .map(|last_cross| (idx - last_cross) as f64)
}

fn ema_values(values: &[f64], span: usize) -> Vec<f64> {
    let alpha = 2.0 / (span as f64 + 1.0);
    let beta = 1.0 - alpha;
    let mut out = Vec::with_capacity(values.len());
    let mut prev = f64::NAN;
    let mut missing_after_valid = 0_i32;
    for value in values {
        if value.is_nan() {
            out.push(prev);
            if !prev.is_nan() {
                missing_after_valid += 1;
            }
        } else if prev.is_nan() {
            prev = *value;
            missing_after_valid = 0;
            out.push(prev);
        } else {
            let effective_alpha = alpha / (alpha + beta.powi(missing_after_valid + 1));
            let current = effective_alpha * *value + (1.0 - effective_alpha) * prev;
            out.push(current);
            prev = current;
            missing_after_valid = 0;
        }
    }
    out
}

fn raw_b2_count_in_current_j_up_cycle(history: &[&PreparedRow], idx: usize) -> usize {
    let start = (2..=idx)
        .rev()
        .find(|candidate_idx| {
            history[*candidate_idx].j > history[*candidate_idx - 1].j
                && history[*candidate_idx - 1].j <= history[*candidate_idx - 2].j
        })
        .unwrap_or(0);
    (start..=idx)
        .filter(|candidate_idx| raw_b2_basic_condition(history, *candidate_idx))
        .count()
}

#[cfg(test)]
mod tests {
    use super::*;

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
}
