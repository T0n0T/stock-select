use std::collections::BTreeMap;

use chrono::{Datelike, NaiveDate};
use rayon::prelude::*;

use crate::indicators::{
    barslast, count_dynamic, ema, kdj, macd, rolling_max, rolling_mean, rolling_min, rolling_sum,
    tdx_sma, zx_lines,
};
use crate::model::{MarketRow, PreparedRow};

pub fn prepare_rows(rows: &[MarketRow]) -> Vec<PreparedRow> {
    let mut grouped: BTreeMap<String, Vec<MarketRow>> = BTreeMap::new();
    for row in rows {
        grouped
            .entry(row.ts_code.clone())
            .or_default()
            .push(row.clone());
    }

    let mut prepared: Vec<PreparedRow> = grouped
        .into_par_iter()
        .flat_map(|(_code, mut group)| {
            group.sort_by_key(|row| row.trade_date);
            prepare_symbol(&group)
        })
        .collect();
    prepared.sort_by(|left, right| {
        left.ts_code
            .cmp(&right.ts_code)
            .then(left.trade_date.cmp(&right.trade_date))
    });
    prepared
}

fn prepare_symbol(rows: &[MarketRow]) -> Vec<PreparedRow> {
    let open: Vec<f64> = rows.iter().map(|row| row.open).collect();
    let high: Vec<f64> = rows.iter().map(|row| row.high).collect();
    let low: Vec<f64> = rows.iter().map(|row| row.low).collect();
    let close: Vec<f64> = rows.iter().map(|row| row.close).collect();
    let volume: Vec<f64> = rows.iter().map(|row| row.vol).collect();
    let turnover_daily: Vec<f64> = open
        .iter()
        .zip(close.iter())
        .zip(volume.iter())
        .map(|((open, close), volume)| ((open + close) / 2.0) * volume)
        .collect();
    let turnover_n: Vec<f64> = rolling_sum(&turnover_daily, 43, 1)
        .into_iter()
        .map(|value| value.unwrap_or(0.0))
        .collect();
    let (k, d, j) = kdj(&high, &low, &close, 9);
    let (zxdq, zxdkx) = zx_lines(&close);
    let (dif, dea, macd_hist) = macd(&close, 12, 26, 9);
    let dates: Vec<NaiveDate> = rows.iter().map(|row| row.trade_date).collect();
    let ma25 = rolling_mean(&close, 25, 25);
    let ma60 = rolling_mean(&close, 60, 60);
    let ma144 = rolling_mean(&close, 144, 144);
    let weekly_ma_bull = weekly_ma_bull(&dates, &close);
    let max_vol_not_bearish = max_vol_not_bearish(&open, &close, &volume, 20);
    let tightening = tightening_helpers(&open, &high, &low, &close, &volume);
    let yellow_b1 = yellow_b1_signal(rows, &open, &high, &low, &close, &volume, &j);

    rows.iter()
        .enumerate()
        .map(|(idx, row)| PreparedRow {
            ts_code: row.ts_code.clone(),
            trade_date: row.trade_date,
            open: row.open,
            high: row.high,
            low: row.low,
            close: row.close,
            volume: row.vol,
            turnover_n: turnover_n[idx],
            k: k[idx],
            d: d[idx],
            j: j[idx],
            zxdq: Some(zxdq[idx]),
            zxdkx: zxdkx[idx],
            dif: dif[idx],
            dea: dea[idx],
            macd_hist: macd_hist[idx],
            ma25: ma25[idx],
            ma60: ma60[idx],
            ma144: ma144[idx],
            chg_d: tightening.chg_d[idx],
            weekly_ma_bull: weekly_ma_bull[idx],
            max_vol_not_bearish: max_vol_not_bearish[idx],
            v_shrink: tightening.v_shrink[idx],
            safe_mode: tightening.safe_mode[idx],
            lt_filter: tightening.lt_filter[idx],
            yellow_b1: yellow_b1[idx],
        })
        .collect()
}

fn weekly_ma_bull(dates: &[NaiveDate], close: &[f64]) -> Vec<bool> {
    let mut weekly_dates = Vec::new();
    let mut weekly_close = Vec::new();
    let mut last_key: Option<(i32, u32)> = None;
    for (idx, date) in dates.iter().enumerate() {
        let week = date.iso_week();
        let key = (week.year(), week.week());
        if Some(key) != last_key {
            weekly_dates.push(*date);
            weekly_close.push(close[idx]);
            last_key = Some(key);
        } else if let Some(last_close) = weekly_close.last_mut() {
            *last_close = close[idx];
            if let Some(last_date) = weekly_dates.last_mut() {
                *last_date = *date;
            }
        }
    }
    let ma10 = rolling_mean(&weekly_close, 10, 10);
    let ma20 = rolling_mean(&weekly_close, 20, 20);
    let ma30 = rolling_mean(&weekly_close, 30, 30);
    let weekly_flags: Vec<bool> = (0..weekly_close.len())
        .map(|idx| match (ma10[idx], ma20[idx], ma30[idx]) {
            (Some(short), Some(medium), Some(long)) => short > medium && medium > long,
            _ => false,
        })
        .collect();
    let mut out = Vec::with_capacity(dates.len());
    let mut weekly_idx = 0;
    let mut current = false;
    for date in dates {
        while weekly_idx < weekly_dates.len() && weekly_dates[weekly_idx] <= *date {
            current = weekly_flags[weekly_idx];
            weekly_idx += 1;
        }
        out.push(current);
    }
    out
}

fn max_vol_not_bearish(open: &[f64], close: &[f64], volume: &[f64], lookback: usize) -> Vec<bool> {
    (0..volume.len())
        .map(|idx| {
            let start = idx.saturating_sub(lookback - 1);
            let mut max_idx = start;
            for current in start..=idx {
                if volume[current] > volume[max_idx] {
                    max_idx = current;
                }
            }
            close[max_idx] >= open[max_idx]
        })
        .collect()
}

struct Tightening {
    chg_d: Vec<Option<f64>>,
    v_shrink: Vec<bool>,
    safe_mode: Vec<bool>,
    lt_filter: Vec<bool>,
}

fn tightening_helpers(
    open: &[f64],
    high: &[f64],
    low: &[f64],
    close: &[f64],
    volume: &[f64],
) -> Tightening {
    let mut chg_d = vec![None; close.len()];
    let mut body_d = vec![None; close.len()];
    for idx in 1..close.len() {
        let ref_close = close[idx - 1];
        chg_d[idx] = Some((close[idx] - ref_close) / ref_close * 100.0);
        body_d[idx] = Some((open[idx] - close[idx]) / ref_close * 100.0);
    }
    let vm3 = rolling_mean(volume, 3, 1);
    let vm10 = rolling_mean(volume, 10, 1);
    let v_shrink: Vec<bool> = vm3
        .iter()
        .zip(vm10.iter())
        .map(|(short, long)| short.unwrap_or(0.0) < long.unwrap_or(0.0))
        .collect();

    let high20 = rolling_max(high, 20, 1);
    let low20 = rolling_min(low, 20, 1);
    let vm5 = rolling_mean(volume, 5, 1);
    let mut bad_dump = vec![false; close.len()];
    for idx in 1..close.len() {
        let high_pos = match (high20[idx], low20[idx]) {
            (Some(h), Some(l)) if l != 0.0 => ((h - l) / l * 100.0) > 15.0,
            _ => false,
        };
        let vol_big = volume[idx] > vm5[idx].unwrap_or(0.0) * 1.3
            || volume[idx] > vm10[idx].unwrap_or(0.0) * 1.5;
        bad_dump[idx] = ((body_d[idx].unwrap_or(f64::NAN) > 6.0)
            || (chg_d[idx].unwrap_or(f64::NAN) < -5.5))
            && vol_big
            && high_pos;
    }
    let dump_day = barslast(&bad_dump);
    let bad_dump_count10: Vec<f64> = rolling_sum(
        &bad_dump
            .iter()
            .map(|value| if *value { 1.0 } else { 0.0 })
            .collect::<Vec<_>>(),
        10,
        1,
    )
    .into_iter()
    .map(|value| value.unwrap_or(0.0))
    .collect();
    let safe_mode: Vec<bool> = dump_day
        .iter()
        .zip(bad_dump_count10.iter())
        .map(|(dump_day, count10)| *dump_day >= if *count10 >= 2.0 { 10.0 } else { 5.0 })
        .collect();

    let st_l = ema(&ema(close, 10), 10);
    let ma14 = rolling_mean(close, 14, 1);
    let ma28 = rolling_mean(close, 28, 1);
    let ma57 = rolling_mean(close, 57, 1);
    let ma114 = rolling_mean(close, 114, 1);
    let lt: Vec<f64> = (0..close.len())
        .map(|idx| {
            (ma14[idx].unwrap_or(f64::NAN)
                + ma28[idx].unwrap_or(f64::NAN)
                + ma57[idx].unwrap_or(f64::NAN)
                + ma114[idx].unwrap_or(f64::NAN))
                / 4.0
        })
        .collect();
    let cross_up: Vec<bool> = (0..close.len())
        .map(|idx| idx > 0 && st_l[idx] > lt[idx] && st_l[idx - 1] <= lt[idx - 1])
        .collect();
    let c_days = barslast(&cross_up);
    let waiver: Vec<bool> = (0..close.len())
        .map(|idx| {
            ((c_days[idx] >= 0.0) && (c_days[idx] <= 30.0) && (st_l[idx] > lt[idx]))
                || st_l[idx] > lt[idx] * 1.03
        })
        .collect();
    let mut lt_dir = vec![1.0; close.len()];
    for idx in 0..close.len() {
        if idx + 1 > 114 {
            lt_dir[idx] =
                if idx > 0 && !lt[idx].is_nan() && !lt[idx - 1].is_nan() && lt[idx] > lt[idx - 1] {
                    1.0
                } else {
                    -1.0
                };
        }
    }
    let lt_flips_bool: Vec<f64> = (0..close.len())
        .map(|idx| {
            if idx > 0 && (lt_dir[idx] != lt_dir[idx - 1]) {
                1.0
            } else {
                0.0
            }
        })
        .collect();
    let lt_flips = rolling_sum(&lt_flips_bool, 30, 1);
    let lt_filter: Vec<bool> = (0..close.len())
        .map(|idx| lt_flips[idx].unwrap_or(0.0) <= 2.0 || waiver[idx])
        .collect();

    Tightening {
        chg_d,
        v_shrink,
        safe_mode,
        lt_filter,
    }
}

fn yellow_b1_signal(
    rows: &[MarketRow],
    open: &[f64],
    high: &[f64],
    low: &[f64],
    close: &[f64],
    volume: &[f64],
    j: &[f64],
) -> Vec<bool> {
    let len = close.len();
    let days_l: Vec<f64> = (1..=len).map(|value| value as f64).collect();
    let is_new: Vec<bool> = days_l.iter().map(|value| *value <= 114.0).collect();
    let st_l = ema(&ema(close, 10), 10);
    let ma14 = rolling_mean(close, 14, 14);
    let ma28 = rolling_mean(close, 28, 28);
    let ma57 = rolling_mean(close, 57, 57);
    let ma114 = rolling_mean(close, 114, 114);
    let lt_r: Vec<Option<f64>> = (0..len)
        .map(|idx| {
            if is_new[idx] {
                None
            } else {
                match (ma14[idx], ma28[idx], ma57[idx], ma114[idx]) {
                    (Some(a), Some(b), Some(c), Some(d)) => Some((a + b + c + d) / 4.0),
                    _ => None,
                }
            }
        })
        .collect();
    let cross_up: Vec<bool> = (0..len)
        .map(|idx| {
            idx > 0
                && matches!((lt_r[idx], lt_r[idx - 1]), (Some(cur), Some(prev)) if st_l[idx] > cur && st_l[idx - 1] <= prev)
        })
        .collect();
    let c_days = barslast(&cross_up);
    let mut lt_dir = vec![1.0; len];
    for idx in 0..len {
        if !is_new[idx] {
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
    let flip_values: Vec<f64> = (0..len)
        .map(|idx| {
            if idx > 0 && lt_dir[idx] != lt_dir[idx - 1] {
                1.0
            } else {
                0.0
            }
        })
        .collect();
    let flip_c = rolling_sum(&flip_values, 30, 1);
    let tr_ok: Vec<bool> = (0..len)
        .map(|idx| {
            if is_new[idx] {
                return true;
            }
            let Some(lt) = lt_r[idx] else {
                return false;
            };
            let honeymoon = c_days[idx] >= 0.0 && c_days[idx] <= 30.0 && st_l[idx] > lt;
            let breakaway = st_l[idx] > lt * 1.03;
            let lt_stable = flip_c[idx].unwrap_or(0.0) <= 2.0;
            let support = close[idx] >= lt * 0.95;
            honeymoon
                || breakaway
                || ((st_l[idx] > lt) && (close[idx] > lt) && lt_stable && support)
        })
        .collect();
    let above_lt: Vec<bool> = (0..len)
        .map(|idx| is_new[idx] || lt_r[idx].map(|lt| close[idx] > lt).unwrap_or(false))
        .collect();

    let high4 = rolling_max(high, 4, 1);
    let low4 = rolling_min(low, 4, 1);
    let mut v1a = vec![0.0; len];
    let mut v3a = vec![0.0; len];
    for idx in 0..len {
        let h = high4[idx].unwrap_or(f64::NAN);
        let l = low4[idx].unwrap_or(f64::NAN);
        let range = (h - l).max(0.01);
        v1a[idx] = (h - close[idx]) / range * 100.0 - 90.0;
        v3a[idx] = (close[idx] - l) / range * 100.0;
    }
    let v2a: Vec<f64> = tdx_sma(&v1a, 4, 1)
        .into_iter()
        .map(|value| value + 100.0)
        .collect();
    let v5a_inner = tdx_sma(&v3a, 6, 1);
    let v5a: Vec<f64> = tdx_sma(&v5a_inner, 6, 1)
        .into_iter()
        .map(|value| value + 100.0)
        .collect();
    let v_diff: Vec<f64> = v5a
        .iter()
        .zip(v2a.iter())
        .map(|(v5, v2)| v5 - v2 - 4.0)
        .collect();
    let turn_color: Vec<bool> = (0..len)
        .map(|idx| idx > 1 && v_diff[idx] > v_diff[idx - 1] && v_diff[idx - 1] <= v_diff[idx - 2])
        .collect();

    let pct: Vec<Option<f64>> = (0..len)
        .map(|idx| {
            if idx > 0 {
                Some((close[idx] - close[idx - 1]) / close[idx - 1] * 100.0)
            } else {
                None
            }
        })
        .collect();
    let amp: Vec<Option<f64>> = (0..len)
        .map(|idx| {
            if idx > 0 {
                Some((high[idx] - low[idx]) / close[idx - 1] * 100.0)
            } else {
                None
            }
        })
        .collect();
    let j_up: Vec<bool> = (0..len).map(|idx| idx > 0 && j[idx] > j[idx - 1]).collect();
    let j_turn_up: Vec<bool> = (0..len)
        .map(|idx| idx > 1 && j_up[idx] && !j_up[idx - 1])
        .collect();
    let up_days = barslast(&j_turn_up);
    let raw_b2: Vec<bool> = (0..len)
        .map(|idx| {
            if idx < 2 {
                return false;
            }
            let amp_limit =
                if rows[idx].ts_code.starts_with("688") || rows[idx].ts_code.starts_with("300") {
                    12.0
                } else {
                    8.0
                };
            let _shake = pct[idx].unwrap_or(f64::NAN).abs() < 5.05
                && amp[idx].unwrap_or(f64::NAN) < amp_limit;
            let pre_ok = pct[idx - 1].unwrap_or(f64::NAN) < 3.7 && j[idx - 1] < 39.0;
            let up_shadow = high[idx] - close[idx].max(open[idx]);
            let ef_body = close[idx] - open[idx].min(close[idx - 1]);
            let k_shape = up_shadow <= ef_body && close[idx] > close[idx - 1];
            pct[idx].unwrap_or(f64::NAN) >= 3.7
                && volume[idx] > volume[idx - 1]
                && k_shape
                && pre_ok
                && j_up[idx]
                && tr_ok[idx]
                && above_lt[idx]
        })
        .collect();
    let cur_b2_count = count_dynamic(
        &raw_b2,
        &up_days.iter().map(|value| value + 1.0).collect::<Vec<_>>(),
    );
    let cur_b2: Vec<bool> = raw_b2
        .iter()
        .zip(cur_b2_count.iter())
        .map(|(raw, count)| *raw && *count == 1.0)
        .collect();
    let b1_environment: Vec<bool> = (0..len)
        .map(|idx| tr_ok[idx] && above_lt[idx] && !cur_b2[idx])
        .collect();
    let yellow_raw: Vec<bool> = (0..len)
        .map(|idx| {
            b1_environment[idx]
                && turn_color[idx]
                && j[idx] < 29.0
                && pct[idx].unwrap_or(f64::NAN) <= 3.7
        })
        .collect();
    let yellow_count5 = rolling_sum(
        &yellow_raw
            .iter()
            .map(|value| if *value { 1.0 } else { 0.0 })
            .collect::<Vec<_>>(),
        5,
        1,
    );
    (0..len)
        .map(|idx| yellow_raw[idx] && yellow_count5[idx].unwrap_or(0.0) <= 3.0)
        .collect()
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

    use super::*;

    fn row(code: &str, day: u32, close: f64, vol: f64) -> MarketRow {
        MarketRow {
            ts_code: code.to_string(),
            trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
            open: close - 0.5,
            high: close + 1.0,
            low: close - 1.0,
            close,
            vol,
        }
    }

    #[test]
    fn prepare_rows_groups_and_sorts_by_symbol_then_date() {
        let rows = vec![
            row("000002.SZ", 2, 12.0, 20.0),
            row("000001.SZ", 2, 11.0, 10.0),
            row("000001.SZ", 1, 10.0, 10.0),
        ];
        let prepared = prepare_rows(&rows);
        assert_eq!(prepared.len(), 3);
        assert_eq!(prepared[0].ts_code, "000001.SZ");
        assert_eq!(
            prepared[0].trade_date,
            NaiveDate::from_ymd_opt(2026, 5, 1).unwrap()
        );
        assert_eq!(prepared[2].ts_code, "000002.SZ");
    }

    #[test]
    fn prepare_rows_computes_turnover_and_indicators() {
        let rows = vec![
            row("000001.SZ", 1, 10.0, 10.0),
            row("000001.SZ", 2, 11.0, 20.0),
        ];
        let prepared = prepare_rows(&rows);
        assert_eq!(prepared[0].turnover_n, 97.5);
        assert_eq!(prepared[1].turnover_n, 97.5 + 215.0);
        assert_eq!(prepared[0].j, 50.0);
        assert!(prepared[1].dif > prepared[0].dif);
    }
}
