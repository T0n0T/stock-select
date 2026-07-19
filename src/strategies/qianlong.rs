use std::collections::BTreeMap;

use chrono::NaiveDate;

use crate::model::{Candidate, PreparedRow};
use crate::strategies::{StrategyOutput, group_refs_by_symbol, sort_candidates};

const MIN_DAILY_BARS: usize = 15;
const MIN_WEEKLY_PERIODS: f64 = 40.0;
const MIN_MONTHLY_PERIODS: f64 = 30.0;
const SURGE_LOOKBACK_DAYS: usize = 22;
const SURGE_PCT_THRESHOLD: f64 = 9.5;
const SURGE_VOLUME_RATIO_THRESHOLD: f64 = 1.5;

pub fn run_qianlong_strategy(rows: &[PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let refs = rows.iter().collect::<Vec<_>>();
    run_qianlong_strategy_from_refs(&refs, pick_date)
}

pub fn run_qianlong_strategy_from_refs(
    rows: &[&PreparedRow],
    pick_date: NaiveDate,
) -> StrategyOutput {
    let grouped = group_refs_by_symbol(rows);
    let mut stats = BTreeMap::from([
        ("total_symbols".to_string(), grouped.len()),
        ("eligible".to_string(), 0),
        ("fail_no_pick_date".to_string(), 0),
        ("fail_insufficient_history".to_string(), 0),
        ("fail_monthly_macd".to_string(), 0),
        ("fail_weekly_macd".to_string(), 0),
        ("fail_daily_divergence".to_string(), 0),
        ("fail_bullish_engulfing".to_string(), 0),
        ("fail_surge_volume".to_string(), 0),
        ("selected".to_string(), 0),
        ("selected_qianlong".to_string(), 0),
    ]);
    let mut candidates = Vec::new();

    for (code, history) in grouped {
        if code.ends_with(".BJ") {
            continue;
        }
        let Some((idx, row)) = history
            .iter()
            .enumerate()
            .find(|(_idx, row)| row.trade_date == pick_date)
        else {
            *stats.entry("fail_no_pick_date".to_string()).or_default() += 1;
            continue;
        };
        *stats.entry("eligible".to_string()).or_default() += 1;
        if idx + 1 < MIN_DAILY_BARS {
            *stats
                .entry("fail_insufficient_history".to_string())
                .or_default() += 1;
            continue;
        }

        let active_history = &history[..=idx];
        if !monthly_macd_increasing(row) {
            *stats.entry("fail_monthly_macd".to_string()).or_default() += 1;
            continue;
        }
        if !weekly_macd_increasing(row) {
            *stats.entry("fail_weekly_macd".to_string()).or_default() += 1;
            continue;
        }
        if !daily_green_divergence(active_history) {
            *stats
                .entry("fail_daily_divergence".to_string())
                .or_default() += 1;
            continue;
        }
        if !bullish_engulfing(active_history) {
            *stats
                .entry("fail_bullish_engulfing".to_string())
                .or_default() += 1;
            continue;
        }
        if !recent_surge_volume(active_history) {
            *stats.entry("fail_surge_volume".to_string()).or_default() += 1;
            continue;
        }

        candidates.push(Candidate {
            code: code.to_string(),
            pick_date,
            close: row.close,
            turnover_n: row.turnover_n,
            signal: Some("QIANLONG".to_string()),
            yellow_b1: None,
        });
        *stats.entry("selected".to_string()).or_default() += 1;
        *stats.entry("selected_qianlong".to_string()).or_default() += 1;
    }

    sort_candidates(&mut candidates);
    StrategyOutput { candidates, stats }
}

fn monthly_macd_increasing(row: &PreparedRow) -> bool {
    period_hist_pair(row, "monthly", MIN_MONTHLY_PERIODS)
        .is_some_and(|(current, previous)| current > 0.0 && current > previous)
}

fn weekly_macd_increasing(row: &PreparedRow) -> bool {
    period_hist_pair(row, "weekly", MIN_WEEKLY_PERIODS)
        .is_some_and(|(current, previous)| current > previous)
}

fn period_hist_pair(row: &PreparedRow, period: &str, minimum_periods: f64) -> Option<(f64, f64)> {
    let current = finite_factor(row, &format!("macd_{period}_hist"))?;
    let previous = finite_factor(row, &format!("macd_{period}_prev_hist"))?;
    let period_count = finite_factor(row, &format!("macd_{period}_period_count"))?;
    (period_count >= minimum_periods).then_some((current, previous))
}

fn finite_factor(row: &PreparedRow, key: &str) -> Option<f64> {
    row.db_factors
        .get(key)
        .copied()
        .filter(|value| value.is_finite())
}

fn daily_green_divergence(history: &[&PreparedRow]) -> bool {
    let hist = history.iter().map(|row| row.macd_hist).collect::<Vec<_>>();
    if hist.len() < MIN_DAILY_BARS {
        return false;
    }

    let segments = green_segments(&hist);
    if segments.len() >= 2 {
        let first = segments[segments.len() - 2];
        let second = segments[segments.len() - 1];
        return completed_green_peak(&hist, first)
            .zip(completed_green_peak(&hist, second))
            .is_some_and(|(first_peak, second_peak)| second_peak.abs() < first_peak.abs());
    }

    segments.last().is_some_and(|segment| {
        completed_local_green_peaks(&hist, *segment)
            .windows(2)
            .last()
            .is_some_and(|peaks| peaks[1].abs() < peaks[0].abs())
    })
}

fn green_segments(hist: &[f64]) -> Vec<(usize, usize)> {
    let mut segments = Vec::new();
    let mut start = None;
    for (idx, value) in hist.iter().enumerate() {
        if value.is_finite() && *value < 0.0 {
            start.get_or_insert(idx);
        } else if let Some(segment_start) = start.take() {
            segments.push((segment_start, idx - 1));
        }
    }
    if let Some(segment_start) = start {
        segments.push((segment_start, hist.len() - 1));
    }
    segments
}

fn completed_green_peak(hist: &[f64], segment: (usize, usize)) -> Option<f64> {
    let (start, end) = segment;
    let peak_idx = (start..=end).min_by(|left, right| hist[*left].total_cmp(&hist[*right]))?;
    let contracted_inside_segment = peak_idx < end;
    let contracted_to_non_green = end + 1 < hist.len() && hist[end + 1] >= 0.0;
    (contracted_inside_segment || contracted_to_non_green).then_some(hist[peak_idx])
}

fn completed_local_green_peaks(hist: &[f64], segment: (usize, usize)) -> Vec<f64> {
    let (start, end) = segment;
    if end.saturating_sub(start) < 4 {
        return Vec::new();
    }
    let mut peaks = (start + 1..end)
        .filter(|idx| hist[*idx] <= hist[*idx - 1] && hist[*idx] < hist[*idx + 1])
        .map(|idx| hist[idx])
        .collect::<Vec<_>>();
    if end > start && hist[end] < hist[end - 1] && end + 1 < hist.len() && hist[end + 1] >= 0.0 {
        peaks.push(hist[end]);
    }
    peaks
}

fn bullish_engulfing(history: &[&PreparedRow]) -> bool {
    let Some((previous, current)) = history
        .get(history.len().saturating_sub(2))
        .zip(history.last())
    else {
        return false;
    };
    previous.close < previous.open
        && current.close > current.open
        && current.close > previous.high
        && current.open < previous.close
}

fn recent_surge_volume(history: &[&PreparedRow]) -> bool {
    let start = history.len().saturating_sub(SURGE_LOOKBACK_DAYS);
    (start..history.len()).any(|idx| {
        if idx == 0 {
            return false;
        }
        let previous_close = history[idx - 1].close;
        if !previous_close.is_finite() || previous_close <= 0.0 {
            return false;
        }
        let pct_change = (history[idx].close - previous_close) / previous_close * 100.0;
        let volume_start = idx.saturating_sub(5);
        let previous_volumes = &history[volume_start..idx];
        if previous_volumes.len() < 3 {
            return false;
        }
        let average_volume = previous_volumes.iter().map(|row| row.volume).sum::<f64>()
            / previous_volumes.len() as f64;
        average_volume > 0.0
            && pct_change >= SURGE_PCT_THRESHOLD
            && history[idx].volume / average_volume >= SURGE_VOLUME_RATIO_THRESHOLD
    })
}
