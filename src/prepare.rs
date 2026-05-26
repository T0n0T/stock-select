use std::collections::BTreeMap;

use rayon::prelude::*;

use crate::indicators::{
    ema, kdj, macd, rolling_max, rolling_mean, rolling_min, rolling_sum, zx_lines,
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
    let ma25 = rolling_mean(&close, 25, 1);
    let ma60 = rolling_mean(&close, 60, 1);
    let ma144 = rolling_mean(&close, 144, 1);
    let weekly_ma_bull = weekly_ma_bull_approx(&close);
    let max_vol_not_bearish = max_vol_not_bearish(&open, &close, &volume, 20);
    let (v_shrink, safe_mode, lt_filter) = tightening_helpers(&open, &high, &low, &close, &volume);

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
            weekly_ma_bull: weekly_ma_bull[idx],
            max_vol_not_bearish: max_vol_not_bearish[idx],
            v_shrink: v_shrink[idx],
            safe_mode: safe_mode[idx],
            lt_filter: lt_filter[idx],
        })
        .collect()
}

fn weekly_ma_bull_approx(close: &[f64]) -> Vec<bool> {
    let ma10 = rolling_mean(close, 50, 50);
    let ma20 = rolling_mean(close, 100, 100);
    let ma30 = rolling_mean(close, 150, 150);
    (0..close.len())
        .map(|idx| match (ma10[idx], ma20[idx], ma30[idx]) {
            (Some(short), Some(medium), Some(long)) => short > medium && medium > long,
            _ => false,
        })
        .collect()
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

fn tightening_helpers(
    open: &[f64],
    high: &[f64],
    low: &[f64],
    close: &[f64],
    volume: &[f64],
) -> (Vec<bool>, Vec<bool>, Vec<bool>) {
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
        let ref_close = close[idx - 1];
        let chg_d = (close[idx] - ref_close) / ref_close * 100.0;
        let body_d = (open[idx] - close[idx]) / ref_close * 100.0;
        let high_pos = match (high20[idx], low20[idx]) {
            (Some(h), Some(l)) if l != 0.0 => ((h - l) / l * 100.0) > 15.0,
            _ => false,
        };
        let vol_big = volume[idx] > vm5[idx].unwrap_or(0.0) * 1.3
            || volume[idx] > vm10[idx].unwrap_or(0.0) * 1.5;
        bad_dump[idx] = ((body_d > 6.0) || (chg_d < -5.5)) && vol_big && high_pos;
    }
    let safe_mode = barslast_bool_threshold(&bad_dump, 5.0);

    let st_l = ema(&ema(close, 10), 10);
    let ma14 = rolling_mean(close, 14, 1);
    let ma28 = rolling_mean(close, 28, 1);
    let ma57 = rolling_mean(close, 57, 1);
    let ma114 = rolling_mean(close, 114, 1);
    let lt: Vec<f64> = (0..close.len())
        .map(|idx| {
            (ma14[idx].unwrap_or(close[idx])
                + ma28[idx].unwrap_or(close[idx])
                + ma57[idx].unwrap_or(close[idx])
                + ma114[idx].unwrap_or(close[idx]))
                / 4.0
        })
        .collect();
    let lt_filter: Vec<bool> = (0..close.len())
        .map(|idx| idx < 114 || st_l[idx] >= lt[idx] * 0.97 || close[idx] >= lt[idx] * 0.95)
        .collect();

    (v_shrink, safe_mode, lt_filter)
}

fn barslast_bool_threshold(condition: &[bool], threshold: f64) -> Vec<bool> {
    crate::indicators::barslast(condition)
        .into_iter()
        .map(|distance| distance >= threshold)
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
