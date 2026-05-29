pub fn ema(values: &[f64], span: usize) -> Vec<f64> {
    assert!(span > 0, "span must be positive");
    if values.is_empty() {
        return Vec::new();
    }
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

pub fn rolling_mean(values: &[f64], window: usize, min_periods: usize) -> Vec<Option<f64>> {
    assert!(window > 0, "window must be positive");
    rolling_sum(values, window, min_periods)
        .into_iter()
        .enumerate()
        .map(|(idx, sum)| {
            let count = (idx + 1).min(window);
            sum.map(|value| value / count as f64)
        })
        .collect()
}

pub fn rolling_sum(values: &[f64], window: usize, min_periods: usize) -> Vec<Option<f64>> {
    assert!(window > 0, "window must be positive");
    let mut out = Vec::with_capacity(values.len());
    let mut sum = 0.0;
    let mut nan_count = 0_usize;
    for idx in 0..values.len() {
        if values[idx].is_nan() {
            nan_count += 1;
        } else {
            sum += values[idx];
        }
        if idx >= window {
            if values[idx - window].is_nan() {
                nan_count -= 1;
            } else {
                sum -= values[idx - window];
            }
        }
        let count = (idx + 1).min(window);
        out.push((count >= min_periods && nan_count == 0).then_some(sum));
    }
    out
}

pub fn rolling_min(values: &[f64], window: usize, min_periods: usize) -> Vec<Option<f64>> {
    rolling_extreme(values, window, min_periods, f64::min)
}

pub fn rolling_max(values: &[f64], window: usize, min_periods: usize) -> Vec<Option<f64>> {
    rolling_extreme(values, window, min_periods, f64::max)
}

pub fn kdj(high: &[f64], low: &[f64], close: &[f64], n: usize) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    assert_eq!(high.len(), low.len());
    assert_eq!(high.len(), close.len());
    if high.is_empty() {
        return (Vec::new(), Vec::new(), Vec::new());
    }

    let low_n = rolling_min(low, n, 1);
    let high_n = rolling_max(high, n, 1);
    let mut k = Vec::with_capacity(high.len());
    let mut d = Vec::with_capacity(high.len());
    let mut j = Vec::with_capacity(high.len());
    let mut prev_k = 50.0;
    let mut prev_d = 50.0;

    for idx in 0..high.len() {
        let rsv = match (low_n[idx], high_n[idx]) {
            (Some(low_value), Some(high_value)) if !close[idx].is_nan() => {
                (close[idx] - low_value) / (high_value - low_value + 1e-9) * 100.0
            }
            _ => 0.0,
        };
        let (current_k, current_d) = if idx == 0 {
            (50.0, 50.0)
        } else {
            let current_k = (2.0 * prev_k + rsv) / 3.0;
            let current_d = (2.0 * prev_d + current_k) / 3.0;
            (current_k, current_d)
        };
        k.push(current_k);
        d.push(current_d);
        j.push(3.0 * current_k - 2.0 * current_d);
        prev_k = current_k;
        prev_d = current_d;
    }
    (k, d, j)
}

pub fn macd(
    close: &[f64],
    fast: usize,
    slow: usize,
    signal: usize,
) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let fast_ema = ema(close, fast);
    let slow_ema = ema(close, slow);
    let dif: Vec<f64> = fast_ema
        .iter()
        .zip(slow_ema.iter())
        .map(|(fast, slow)| fast - slow)
        .collect();
    let dea = ema(&dif, signal);
    let hist = dif
        .iter()
        .zip(dea.iter())
        .map(|(dif, dea)| dif - dea)
        .collect();
    (dif, dea, hist)
}

pub fn zx_lines(close: &[f64]) -> (Vec<f64>, Vec<Option<f64>>) {
    let first = ema(close, 10);
    let zxdq = ema(&first, 10);
    let ma14 = rolling_mean(close, 14, 14);
    let ma28 = rolling_mean(close, 28, 28);
    let ma57 = rolling_mean(close, 57, 57);
    let ma114 = rolling_mean(close, 114, 114);
    let zxdkx = (0..close.len())
        .map(|idx| match (ma14[idx], ma28[idx], ma57[idx], ma114[idx]) {
            (Some(a), Some(b), Some(c), Some(d)) => Some((a + b + c + d) / 4.0),
            _ => None,
        })
        .collect();
    (zxdq, zxdkx)
}

pub fn barslast(condition: &[bool]) -> Vec<f64> {
    barslast_with_default(condition, None)
}

pub fn barslast_with_default(condition: &[bool], default_distance: Option<f64>) -> Vec<f64> {
    let mut out = Vec::with_capacity(condition.len());
    let mut last_true: Option<usize> = None;
    let default_distance = default_distance.unwrap_or(condition.len() as f64 + 1.0);
    for (idx, value) in condition.iter().enumerate() {
        if *value {
            last_true = Some(idx);
            out.push(0.0);
        } else if let Some(last) = last_true {
            out.push((idx - last) as f64);
        } else {
            out.push(default_distance);
        }
    }
    out
}

pub fn barslast_initial_index_distance(condition: &[bool]) -> Vec<f64> {
    let mut out = Vec::with_capacity(condition.len());
    let mut last_true: Option<usize> = None;
    for (idx, value) in condition.iter().enumerate() {
        if *value {
            last_true = Some(idx);
            out.push(0.0);
        } else if let Some(last) = last_true {
            out.push((idx - last) as f64);
        } else {
            out.push((idx + 1) as f64);
        }
    }
    out
}

pub fn tdx_sma(values: &[f64], n: usize, m: usize) -> Vec<f64> {
    assert!(n > 0, "n must be positive");
    let mut out = Vec::with_capacity(values.len());
    let mut previous: Option<f64> = None;
    for value in values {
        let input = if value.is_nan() { 0.0 } else { *value };
        let current = match previous {
            Some(prev) => (m as f64 * input + (n - m) as f64 * prev) / n as f64,
            None => input,
        };
        out.push(current);
        previous = Some(current);
    }
    out
}

pub fn count_dynamic(condition: &[bool], windows: &[f64]) -> Vec<f64> {
    assert_eq!(condition.len(), windows.len());
    (0..condition.len())
        .map(|idx| {
            let window = windows[idx].max(1.0) as usize;
            let start = idx.saturating_sub(window - 1);
            condition[start..=idx]
                .iter()
                .filter(|value| **value)
                .count() as f64
        })
        .collect()
}

fn rolling_extreme(
    values: &[f64],
    window: usize,
    min_periods: usize,
    op: fn(f64, f64) -> f64,
) -> Vec<Option<f64>> {
    assert!(window > 0, "window must be positive");
    let mut out = Vec::with_capacity(values.len());
    for idx in 0..values.len() {
        let start = idx.saturating_sub(window - 1);
        let count = idx - start + 1;
        if count < min_periods {
            out.push(None);
            continue;
        }
        if values[start..=idx].iter().any(|value| value.is_nan()) {
            out.push(None);
            continue;
        }
        let mut value = values[start];
        for item in &values[start + 1..=idx] {
            value = op(value, *item);
        }
        out.push(Some(value));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn assert_close(actual: f64, expected: f64) {
        assert!(
            (actual - expected).abs() < 1e-6,
            "actual={actual} expected={expected}"
        );
    }

    #[test]
    fn ema_uses_first_value_as_seed() {
        let out = ema(&[10.0, 12.0, 14.0], 3);
        assert_close(out[0], 10.0);
        assert_close(out[1], 11.0);
        assert_close(out[2], 12.5);
    }

    #[test]
    fn ema_matches_pandas_adjust_false_after_nan_gap() {
        let out = ema(&[1.0, f64::NAN, 3.0, 4.0], 2);
        assert_close(out[0], 1.0);
        assert_close(out[1], 1.0);
        assert_close(out[2], 2.7142857142857144);
        assert_close(out[3], 3.571428571428571);
    }

    #[test]
    fn rolling_mean_respects_min_periods() {
        let out = rolling_mean(&[1.0, 2.0, 3.0, 4.0], 3, 3);
        assert_eq!(out[0], None);
        assert_eq!(out[1], None);
        assert_eq!(out[2], Some(2.0));
        assert_eq!(out[3], Some(3.0));
    }

    #[test]
    fn kdj_first_row_matches_python_seed() {
        let (k, d, j) = kdj(&[10.0, 12.0], &[5.0, 6.0], &[7.5, 11.0], 9);
        assert_close(k[0], 50.0);
        assert_close(d[0], 50.0);
        assert_close(j[0], 50.0);
        assert!(k[1] > k[0]);
    }

    #[test]
    fn macd_has_zero_first_row_when_ema_seeds_match() {
        let (dif, dea, hist) = macd(&[10.0, 11.0, 12.0], 12, 26, 9);
        assert_close(dif[0], 0.0);
        assert_close(dea[0], 0.0);
        assert_close(hist[0], 0.0);
        assert!(dif[2] > 0.0);
    }

    #[test]
    fn zxdkx_requires_full_long_window() {
        let close: Vec<f64> = (1..=114).map(|value| value as f64).collect();
        let (zxdq, zxdkx) = zx_lines(&close);
        assert_eq!(zxdq.len(), 114);
        assert_eq!(zxdkx[112], None);
        assert!(zxdkx[113].is_some());
    }

    #[test]
    fn barslast_matches_tdx_style_distance() {
        let out = barslast_initial_index_distance(&[false, false, true, false, false, true]);
        assert_eq!(out, vec![1.0, 2.0, 0.0, 1.0, 2.0, 0.0]);
    }

    #[test]
    fn barslast_default_matches_python_helper() {
        let out = barslast(&[false, false, true, false]);
        assert_eq!(out, vec![5.0, 5.0, 0.0, 1.0]);
    }

    #[test]
    fn count_dynamic_counts_recent_true_values() {
        let out = count_dynamic(&[true, false, true, true], &[1.0, 2.0, 3.0, 2.0]);
        assert_eq!(out, vec![1.0, 1.0, 2.0, 2.0]);
    }
}
