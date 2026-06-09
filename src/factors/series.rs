use crate::factors::types::FactorValue;

pub type FactorList = Vec<(String, FactorValue)>;

pub fn push_number(factors: &mut FactorList, key: &str, value: Option<f64>) {
    factors.push((
        key.to_string(),
        value
            .map(round4)
            .map_or(FactorValue::Missing, FactorValue::Number),
    ));
}

pub fn push_category(factors: &mut FactorList, key: &str, value: impl Into<String>) {
    factors.push((key.to_string(), FactorValue::Category(value.into())));
}

pub fn push_bool(factors: &mut FactorList, key: &str, value: Option<bool>) {
    factors.push((
        key.to_string(),
        value.map_or(FactorValue::Missing, FactorValue::Bool),
    ));
}

pub fn round4(value: f64) -> f64 {
    (value * 10000.0).round() / 10000.0
}

pub fn mean_tail(values: &[f64], window: usize) -> Option<f64> {
    if values.len() < window || window == 0 {
        return None;
    }
    let tail = &values[values.len() - window..];
    Some(tail.iter().sum::<f64>() / window as f64)
}

pub fn mean_prefix_tail(values: &[f64], end: usize, window: usize) -> Option<f64> {
    if end < window || window == 0 {
        return None;
    }
    let start = end - window;
    Some(values[start..end].iter().sum::<f64>() / window as f64)
}

pub fn rolling_mean_series(values: &[f64], window: usize, min_periods: usize) -> Vec<Option<f64>> {
    let mut out = Vec::with_capacity(values.len());
    let mut sum = 0.0;
    for idx in 0..values.len() {
        sum += values[idx];
        if idx >= window {
            sum -= values[idx - window];
        }
        let count = (idx + 1).min(window);
        out.push((count >= min_periods).then_some(sum / count as f64));
    }
    out
}

pub fn ema(values: &[f64], span: usize) -> Vec<f64> {
    if values.is_empty() {
        return Vec::new();
    }
    let alpha = 2.0 / (span as f64 + 1.0);
    let beta = 1.0 - alpha;
    let mut out = Vec::with_capacity(values.len());
    let mut prev = values[0];
    out.push(prev);
    for value in &values[1..] {
        let current = alpha * *value + beta * prev;
        out.push(current);
        prev = current;
    }
    out
}

pub fn ratio(current: Option<f64>, base: Option<f64>) -> Option<f64> {
    match (current, base) {
        (Some(current), Some(base)) if base != 0.0 => Some(current / base),
        _ => None,
    }
}

pub fn pct_change(current: Option<f64>, base: Option<f64>) -> Option<f64> {
    ratio(current, base).map(|ratio| (ratio - 1.0) * 100.0)
}

pub fn pct_of(current: Option<f64>, base: Option<f64>) -> Option<f64> {
    ratio(current, base).map(|ratio| ratio * 100.0)
}

pub fn slope_pct_values(values: &[f64], periods: usize) -> Option<f64> {
    if values.len() <= periods {
        return None;
    }
    pct_change(
        values.last().copied(),
        values.get(values.len() - 1 - periods).copied(),
    )
}
