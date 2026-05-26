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
        ("fail_recent_j".to_string(), 0),
        ("fail_support_ma25".to_string(), 0),
        ("fail_volume_shrink".to_string(), 0),
        ("fail_zxdq_zxdkx".to_string(), 0),
        ("fail_ma60_trend".to_string(), 0),
        ("fail_ma144_distance".to_string(), 0),
        ("fail_macd".to_string(), 0),
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
        if !history[recent_start..=idx].iter().any(|item| item.j < 15.0) {
            increment(&mut stats, "fail_recent_j");
            continue;
        }
        if !(row.zxdq.unwrap_or(f64::NEG_INFINITY) > row.zxdkx.unwrap_or(f64::INFINITY)) {
            increment(&mut stats, "fail_zxdq_zxdkx");
            continue;
        }
        let Some(ma25) = row.ma25 else {
            increment(&mut stats, "fail_support_ma25");
            continue;
        };
        if !(row.low <= ma25 * 1.005 && row.close >= ma25) {
            increment(&mut stats, "fail_support_ma25");
            continue;
        }
        if idx == 0 || row.volume >= history[idx - 1].volume {
            increment(&mut stats, "fail_volume_shrink");
            continue;
        }
        let Some(ma60) = row.ma60 else {
            increment(&mut stats, "fail_ma60_trend");
            continue;
        };
        if idx == 0 || ma60 < history[idx - 1].ma60.unwrap_or(f64::INFINITY) {
            increment(&mut stats, "fail_ma60_trend");
            continue;
        }
        let Some(ma144) = row.ma144 else {
            increment(&mut stats, "fail_ma144_distance");
            continue;
        };
        if ((row.close / ma144 - 1.0) * 100.0).abs() > 30.0 {
            increment(&mut stats, "fail_ma144_distance");
            continue;
        }
        if !(row.dif >= row.dea || row.macd_hist > history[idx - 1].macd_hist) {
            increment(&mut stats, "fail_macd");
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

fn increment(stats: &mut BTreeMap<String, usize>, key: &str) {
    *stats.entry(key.to_string()).or_insert(0) += 1;
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

    use super::*;

    fn row(day: u32, j: f64, volume: f64) -> PreparedRow {
        PreparedRow {
            ts_code: "000001.SZ".to_string(),
            trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
            open: 10.0,
            high: 11.0,
            low: 9.9,
            close: 10.5,
            volume,
            turnover_n: 1000.0 + day as f64,
            k: 20.0,
            d: 20.0,
            j,
            zxdq: Some(10.3),
            zxdkx: Some(10.0),
            dif: 0.2,
            dea: 0.1,
            macd_hist: 0.1 + day as f64 * 0.01,
            ma25: Some(10.0),
            ma60: Some(9.8 + day as f64 * 0.01),
            ma144: Some(9.7),
            weekly_ma_bull: true,
            max_vol_not_bearish: true,
            v_shrink: true,
            safe_mode: true,
            lt_filter: true,
        }
    }

    #[test]
    fn selects_dribull_candidate_when_filters_pass() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 2).unwrap();
        let output = run(&[row(1, 10.0, 120.0), row(2, 20.0, 90.0)], pick);
        assert_eq!(output.candidates.len(), 1);
        assert_eq!(output.stats["selected"], 1);
    }

    #[test]
    fn dribull_no_pick_date_counts_failure() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 3).unwrap();
        let output = run(&[row(1, 10.0, 120.0), row(2, 20.0, 90.0)], pick);
        assert!(output.candidates.is_empty());
        assert_eq!(output.stats["fail_no_pick_date"], 1);
    }
}
