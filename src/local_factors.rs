use std::collections::BTreeMap;

use crate::model::MarketRow;

pub fn enrich_local_market_factors(rows: &mut [MarketRow]) {
    let mut grouped = BTreeMap::<String, Vec<usize>>::new();
    for (idx, row) in rows.iter().enumerate() {
        grouped.entry(row.ts_code.clone()).or_default().push(idx);
    }

    for indices in grouped.values_mut() {
        indices.sort_by_key(|idx| rows[*idx].trade_date);
        let close = indices
            .iter()
            .map(|idx| rows[*idx].close)
            .collect::<Vec<_>>();
        let high = indices
            .iter()
            .map(|idx| rows[*idx].high)
            .collect::<Vec<_>>();
        let low = indices.iter().map(|idx| rows[*idx].low).collect::<Vec<_>>();
        for (pos, idx) in indices.iter().copied().enumerate() {
            let mut factors = std::mem::take(&mut rows[idx].db_factors);
            insert_if_missing(&mut factors, "boll_width_pct", boll_width(&close, pos, 20));
            insert_if_missing(&mut factors, "bias1_qfq", bias(&close, pos, 6));
            insert_if_missing(&mut factors, "roc_qfq", roc(&close, pos, 12));
            insert_if_missing(&mut factors, "mtm_qfq", mtm(&close, pos, 12));
            insert_if_missing(&mut factors, "psy_qfq", psy(&close, pos, 12));
            insert_if_missing(
                &mut factors,
                "wr_qfq",
                wr_positive(&high, &low, &close, pos, 10),
            );
            let (dist_up, dist_down) = limit_dist(&rows, indices, pos);
            insert_if_missing(&mut factors, "dist_to_up_limit_pct", dist_up);
            insert_if_missing(&mut factors, "dist_to_down_limit_pct", dist_down);
            rows[idx].db_factors = factors;
        }
    }
}

fn insert_if_missing(factors: &mut BTreeMap<String, f64>, key: &str, value: Option<f64>) {
    if factors.contains_key(key) {
        return;
    }
    if let Some(value) = value.filter(|value| value.is_finite()) {
        factors.insert(key.to_string(), value);
    }
}

fn window(values: &[f64], pos: usize, len: usize) -> Option<&[f64]> {
    if pos + 1 < len {
        return None;
    }
    Some(&values[pos + 1 - len..=pos])
}

fn mean(values: &[f64]) -> Option<f64> {
    values
        .iter()
        .all(|value| value.is_finite())
        .then(|| values.iter().sum::<f64>() / values.len() as f64)
}

fn boll_width(close: &[f64], pos: usize, len: usize) -> Option<f64> {
    let values = window(close, pos, len)?;
    let mean = mean(values)?;
    if mean == 0.0 {
        return None;
    }
    let variance = values
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / len as f64;
    Some(4.0 * variance.sqrt() / mean * 100.0)
}

fn bias(close: &[f64], pos: usize, len: usize) -> Option<f64> {
    let mean = mean(window(close, pos, len)?)?;
    (mean != 0.0).then_some((close[pos] - mean) / mean * 100.0)
}

fn roc(close: &[f64], pos: usize, periods: usize) -> Option<f64> {
    if pos < periods || !close[pos].is_finite() || !close[pos - periods].is_finite() {
        return None;
    }
    let base = close[pos - periods];
    (base != 0.0).then_some((close[pos] - base) / base * 100.0)
}

fn mtm(close: &[f64], pos: usize, periods: usize) -> Option<f64> {
    if pos < periods || !close[pos].is_finite() || !close[pos - periods].is_finite() {
        return None;
    }
    Some(close[pos] - close[pos - periods])
}

fn psy(close: &[f64], pos: usize, len: usize) -> Option<f64> {
    if pos < len {
        return None;
    }
    let start = pos + 1 - len;
    let mut ups = 0_usize;
    for idx in start..=pos {
        if !close[idx].is_finite() || !close[idx - 1].is_finite() {
            return None;
        }
        if close[idx] > close[idx - 1] {
            ups += 1;
        }
    }
    Some(ups as f64 / len as f64 * 100.0)
}

fn wr_positive(high: &[f64], low: &[f64], close: &[f64], pos: usize, len: usize) -> Option<f64> {
    let high_window = window(high, pos, len)?;
    let low_window = window(low, pos, len)?;
    if high_window
        .iter()
        .chain(low_window.iter())
        .any(|value| !value.is_finite())
        || !close[pos].is_finite()
    {
        return None;
    }
    let highest = high_window
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    let lowest = low_window.iter().copied().fold(f64::INFINITY, f64::min);
    (highest != lowest).then_some((highest - close[pos]) / (highest - lowest) * 100.0)
}

fn limit_dist(rows: &[MarketRow], indices: &[usize], pos: usize) -> (Option<f64>, Option<f64>) {
    if pos == 0 {
        return (None, None);
    }
    let latest = &rows[indices[pos]];
    let previous = &rows[indices[pos - 1]];
    if latest.close == 0.0 || !latest.close.is_finite() || !previous.close.is_finite() {
        return (None, None);
    }
    let pct = limit_pct(&latest.ts_code);
    let up_limit = (previous.close * (1.0 + pct) * 100.0).round() / 100.0;
    let down_limit = (previous.close * (1.0 - pct) * 100.0).round() / 100.0;
    (
        Some((up_limit - latest.close) / latest.close * 100.0),
        Some((latest.close - down_limit) / latest.close * 100.0),
    )
}

fn limit_pct(code: &str) -> f64 {
    let symbol = code.split('.').next().unwrap_or(code);
    if code.ends_with(".BJ") || symbol.starts_with('4') || symbol.starts_with('8') {
        0.30
    } else if symbol.starts_with("300")
        || symbol.starts_with("301")
        || symbol.starts_with("688")
        || symbol.starts_with("689")
    {
        0.20
    } else {
        0.10
    }
}
