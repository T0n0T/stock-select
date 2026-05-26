use std::collections::BTreeMap;

use chrono::NaiveDate;

use crate::model::{Candidate, PreparedRow};
use crate::strategies::{StrategyOutput, group_by_symbol, sort_candidates};

pub fn run(rows: &[PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let grouped = group_by_symbol(rows);
    let mut stats = BTreeMap::from([
        ("total_symbols".to_string(), grouped.len()),
        ("eligible".to_string(), 0),
        ("fail_no_pick_date".to_string(), 0),
        ("fail_low_j".to_string(), 0),
        ("fail_zx".to_string(), 0),
        ("fail_trend".to_string(), 0),
        ("fail_volume".to_string(), 0),
        ("fail_tightening".to_string(), 0),
        ("selected".to_string(), 0),
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
        let recent_start = idx.saturating_sub(14);
        let recent_low_j = history[recent_start..=idx].iter().any(|item| item.j < 15.0);
        let j_quantile = expanding_quantile(
            &history[..=idx]
                .iter()
                .map(|item| item.j)
                .collect::<Vec<_>>(),
            0.10,
        );
        if !(row.j < 15.0 || row.j <= j_quantile || recent_low_j) {
            increment(&mut stats, "fail_low_j");
            continue;
        }
        let Some(zxdq) = row.zxdq else {
            increment(&mut stats, "fail_zx");
            continue;
        };
        let Some(zxdkx) = row.zxdkx else {
            increment(&mut stats, "fail_zx");
            continue;
        };
        if !(row.close > zxdkx && zxdq > zxdkx) {
            increment(&mut stats, "fail_zx");
            continue;
        }
        if !(row.weekly_ma_bull || row.ma25.unwrap_or(0.0) > row.ma60.unwrap_or(f64::MAX)) {
            increment(&mut stats, "fail_trend");
            continue;
        }
        if !row.max_vol_not_bearish {
            increment(&mut stats, "fail_volume");
            continue;
        }
        if !(row.v_shrink && row.safe_mode && row.lt_filter) {
            increment(&mut stats, "fail_tightening");
            continue;
        }
        candidates.push(Candidate {
            code: code.to_string(),
            pick_date,
            close: row.close,
            turnover_n: row.turnover_n,
            signal: None,
        });
        increment(&mut stats, "selected");
    }
    sort_candidates(&mut candidates);
    StrategyOutput { candidates, stats }
}

fn expanding_quantile(values: &[f64], q: f64) -> f64 {
    if values.is_empty() {
        return f64::NAN;
    }
    let mut sorted = values.to_vec();
    sorted.sort_by(|left, right| left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal));
    let idx = ((sorted.len() - 1) as f64 * q).floor() as usize;
    sorted[idx]
}

fn increment(stats: &mut BTreeMap<String, usize>, key: &str) {
    *stats.entry(key.to_string()).or_insert(0) += 1;
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

    use super::*;

    fn base_row(day: u32, j: f64) -> PreparedRow {
        PreparedRow {
            ts_code: "000001.SZ".to_string(),
            trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
            open: 10.0,
            high: 11.0,
            low: 9.8,
            close: 10.8,
            volume: 90.0,
            turnover_n: 1000.0 + day as f64,
            k: 20.0,
            d: 25.0,
            j,
            zxdq: Some(10.2),
            zxdkx: Some(10.0),
            dif: 0.1,
            dea: 0.0,
            macd_hist: 0.1,
            ma25: Some(10.5),
            ma60: Some(10.0),
            ma144: Some(9.0),
            weekly_ma_bull: true,
            max_vol_not_bearish: true,
            v_shrink: true,
            safe_mode: true,
            lt_filter: true,
        }
    }

    #[test]
    fn selects_b1_candidate_when_filters_pass() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 2).unwrap();
        let output = run(&[base_row(1, 30.0), base_row(2, 10.0)], pick);
        assert_eq!(output.candidates.len(), 1);
        assert_eq!(output.candidates[0].code, "000001.SZ");
        assert_eq!(output.stats["selected"], 1);
    }

    #[test]
    fn b1_no_pick_date_counts_failure() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 3).unwrap();
        let output = run(&[base_row(1, 10.0), base_row(2, 10.0)], pick);
        assert!(output.candidates.is_empty());
        assert_eq!(output.stats["fail_no_pick_date"], 1);
    }
}
