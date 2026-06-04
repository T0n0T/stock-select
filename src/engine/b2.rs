use chrono::NaiveDate;
use serde_json::Value;

use crate::engine::types::{FactorRow, FactorValue, SelectionCandidate};
use crate::model::Method;

pub trait B2FactorProvider {
    fn factor_row(&self, candidate: &SelectionCandidate) -> anyhow::Result<FactorRow>;
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CandidatePayloadFactorProvider;

impl B2FactorProvider for CandidatePayloadFactorProvider {
    fn factor_row(&self, candidate: &SelectionCandidate) -> anyhow::Result<FactorRow> {
        let mut row = FactorRow::new(&candidate.code, candidate.method);

        if let Some(object) = candidate.raw_payload.as_object() {
            for (key, value) in object {
                if should_extract_top_level_factor(key, value) {
                    row.factors
                        .insert(key.clone(), factor_value_from_json(value));
                }
            }
        }

        if let Some(factors) = candidate.raw_payload.get("factors") {
            let object = factors
                .as_object()
                .ok_or_else(|| anyhow::anyhow!("candidate factors must be a JSON object"))?;
            for (key, value) in object {
                row.factors
                    .insert(key.clone(), factor_value_from_json(value));
            }
        }

        if let Some(close) = candidate.close {
            row.factors
                .insert("close".to_string(), FactorValue::Number(close));
        }
        if let Some(turnover_n) = candidate.turnover_n {
            row.factors
                .insert("turnover_n".to_string(), FactorValue::Number(turnover_n));
        }
        if let Some(signal) = &candidate.signal {
            row.factors
                .insert("signal".to_string(), FactorValue::Category(signal.clone()));
        }
        if let Some(env) = candidate.raw_payload.get("env").and_then(Value::as_str) {
            row.factors
                .insert("env".to_string(), FactorValue::Category(env.to_string()));
        }

        let history_factor_count = if let Some(history) = candidate.raw_payload.get("history") {
            let history = parse_history_rows(history)?;
            let factors = b2_history_raw_factors(&history);
            let count = factors.len();
            for (key, value) in factors {
                row.factors.insert(key, value);
            }
            Some(count)
        } else {
            None
        };

        row.diagnostics.insert(
            "factor_source".to_string(),
            Value::String("candidate_payload".to_string()),
        );
        if let Some(history_source) = candidate
            .raw_payload
            .get("history_source")
            .and_then(Value::as_str)
        {
            row.diagnostics.insert(
                "history_source".to_string(),
                Value::String(history_source.to_string()),
            );
        }
        if let Some(count) = history_factor_count {
            row.diagnostics.insert(
                "history_factor_count".to_string(),
                Value::Number(serde_json::Number::from(count)),
            );
        }
        row.diagnostics.insert(
            "factor_count".to_string(),
            Value::Number(serde_json::Number::from(row.factors.len())),
        );

        Ok(row)
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct B2HistoryRow {
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
    turnover_n: f64,
    ma25: Option<f64>,
    zxdkx: Option<f64>,
    zxdq: Option<f64>,
    dif: Option<f64>,
    dea: Option<f64>,
    macd_hist: Option<f64>,
}

fn parse_history_rows(value: &Value) -> anyhow::Result<Vec<B2HistoryRow>> {
    let rows = value
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("candidate history must be a JSON array"))?;
    rows.iter()
        .map(|row| {
            Ok(B2HistoryRow {
                open: required_f64(row, "open")?,
                high: required_f64(row, "high")?,
                low: required_f64(row, "low")?,
                close: required_f64(row, "close")?,
                volume: optional_f64(row, "volume")
                    .or_else(|| optional_f64(row, "vol"))
                    .ok_or_else(|| anyhow::anyhow!("history row missing volume"))?,
                turnover_n: optional_f64(row, "turnover_n")
                    .or_else(|| optional_f64(row, "turnover_rate"))
                    .ok_or_else(|| anyhow::anyhow!("history row missing turnover_n"))?,
                ma25: optional_f64(row, "ma25"),
                zxdkx: optional_f64(row, "zxdkx"),
                zxdq: optional_f64(row, "zxdq"),
                dif: optional_f64(row, "dif").or_else(|| optional_f64(row, "macd_dif")),
                dea: optional_f64(row, "dea").or_else(|| optional_f64(row, "macd_dea")),
                macd_hist: optional_f64(row, "macd_hist"),
            })
        })
        .collect()
}

fn b2_history_raw_factors(history: &[B2HistoryRow]) -> Vec<(String, FactorValue)> {
    if history.is_empty() {
        return Vec::new();
    }

    let close = history.iter().map(|row| row.close).collect::<Vec<_>>();
    let high = history.iter().map(|row| row.high).collect::<Vec<_>>();
    let low = history.iter().map(|row| row.low).collect::<Vec<_>>();
    let open = history.iter().map(|row| row.open).collect::<Vec<_>>();
    let volume = history.iter().map(|row| row.volume).collect::<Vec<_>>();
    let turnover = history.iter().map(|row| row.turnover_n).collect::<Vec<_>>();
    let derived_ma25 = rolling_mean_series(&close, 25, 25);
    let (derived_zxdq, derived_zxdkx) = zx_lines(&close);
    let ma25 = history
        .iter()
        .enumerate()
        .map(|(idx, row)| row.ma25.or(derived_ma25[idx]))
        .collect::<Vec<_>>();
    let zxdkx = history
        .iter()
        .enumerate()
        .map(|(idx, row)| row.zxdkx.or(derived_zxdkx[idx]))
        .collect::<Vec<_>>();
    let zxdq = history
        .iter()
        .enumerate()
        .map(|(idx, row)| Some(row.zxdq.unwrap_or(derived_zxdq[idx])))
        .collect::<Vec<_>>();
    let dif = history.iter().map(|row| row.dif).collect::<Vec<_>>();
    let dea = history.iter().map(|row| row.dea).collect::<Vec<_>>();
    let macd_hist = history.iter().map(|row| row.macd_hist).collect::<Vec<_>>();
    let (derived_dif, derived_dea, derived_macd_hist) = macd_lines(&close);

    let latest = history.last().copied();
    let previous = history.iter().rev().nth(1).copied();
    let latest_close = latest.map(|row| row.close);
    let latest_low = latest.map(|row| row.low);
    let latest_high = latest.map(|row| row.high);
    let latest_ma25 = ma25.last().copied().flatten();
    let latest_zxdkx = zxdkx.last().copied().flatten();
    let previous_zxdkx = zxdkx.iter().rev().nth(1).copied().flatten();
    let latest_volume = latest.map(|row| row.volume);
    let previous_volume = previous.map(|row| row.volume);
    let latest_turnover = latest.map(|row| row.turnover_n);
    let latest_macd_hist = macd_hist
        .last()
        .copied()
        .flatten()
        .or_else(|| derived_macd_hist.last().copied());
    let previous_macd_hist = macd_hist
        .iter()
        .rev()
        .nth(1)
        .copied()
        .flatten()
        .or_else(|| derived_macd_hist.iter().rev().nth(1).copied());
    let macd_hist_delta = latest_macd_hist.zip(previous_macd_hist).map(|(a, b)| a - b);
    let macd_hist_slope_3d = if macd_hist.len() >= 4 {
        let previous = macd_hist[macd_hist.len() - 4]
            .or_else(|| derived_macd_hist.get(macd_hist.len() - 4).copied());
        latest_macd_hist
            .zip(previous)
            .map(|(latest, previous)| latest - previous)
    } else {
        None
    };

    let ma25_values = ma25.iter().copied().flatten().collect::<Vec<_>>();
    let zxdkx_values = zxdkx.iter().copied().flatten().collect::<Vec<_>>();
    let zxdq_values = zxdq.iter().copied().flatten().collect::<Vec<_>>();
    let avg_close5 = mean_tail(&close, 5);
    let avg_volume5 = mean_tail(&volume, 5);
    let avg_volume20 = mean_tail(&volume, 20);
    let avg_turnover5 = mean_tail(&turnover, 5);

    let latest_bar_position = match (latest_close, latest_low, latest_high) {
        (Some(close), Some(low), Some(high)) if high != low => {
            Some((close - low) / (high - low) * 100.0)
        }
        _ => None,
    };
    let high_20_close = if close.len() >= 20 {
        Some(
            close[close.len() - 20..]
                .iter()
                .copied()
                .fold(f64::NEG_INFINITY, f64::max),
        )
    } else {
        None
    };
    let tail_high_120 = if high.len() >= 120 {
        &high[high.len() - 120..]
    } else {
        high.as_slice()
    };
    let tail_low_120 = if low.len() >= 120 {
        &low[low.len() - 120..]
    } else {
        low.as_slice()
    };
    let high_120 = tail_high_120.iter().copied().reduce(f64::max);
    let low_120 = tail_low_120.iter().copied().reduce(f64::min);
    let range_center_120 = high_120.zip(low_120).map(|(high, low)| (high + low) / 2.0);
    let range_width_120 = high_120.zip(low_120).map(|(high, low)| high - low);
    let box_position_120 = match (latest_close, low_120, range_width_120) {
        (Some(close), Some(low), Some(width)) if width != 0.0 => {
            Some((close - low) / width * 100.0)
        }
        _ => None,
    };

    let mut factors = Vec::new();
    push_number(
        &mut factors,
        "close_to_ma25_pct",
        pct_change(latest_close, latest_ma25),
    );
    push_number(
        &mut factors,
        "close_to_zxdkx_pct",
        pct_change(latest_close, latest_zxdkx),
    );
    push_number(
        &mut factors,
        "ma25_to_zxdkx_pct",
        pct_change(latest_ma25, latest_zxdkx),
    );
    push_number(
        &mut factors,
        "ma25_slope_5d_pct",
        slope_pct_values(&ma25_values, 5),
    );
    push_number(
        &mut factors,
        "zxdkx_slope_5d_pct",
        slope_pct_values(&zxdkx_values, 5),
    );
    push_number(
        &mut factors,
        "zxdq_slope_5d_pct",
        slope_pct_values(&zxdq_values, 5),
    );
    push_number(
        &mut factors,
        "low_to_ma25_pct",
        pct_change(latest_low, latest_ma25),
    );
    push_flag(
        &mut factors,
        "near_ma25_support_flag",
        latest_low
            .zip(latest_ma25)
            .map(|(low, ma25)| low <= ma25 * 1.03),
    );
    push_flag(
        &mut factors,
        "ma_aligned_flag",
        match (latest_close, latest_ma25, latest_zxdkx) {
            (Some(close), Some(ma25), Some(zxdkx)) => Some(close >= ma25 && ma25 >= zxdkx),
            _ => None,
        },
    );
    push_flag(
        &mut factors,
        "zxdkx_up_1d_flag",
        latest_zxdkx
            .zip(previous_zxdkx)
            .map(|(latest, previous)| latest >= previous),
    );
    push_number(&mut factors, "latest_bar_position_pct", latest_bar_position);
    push_number(
        &mut factors,
        "volume_to_ma5_ratio",
        ratio(latest_volume, avg_volume5),
    );
    push_number(
        &mut factors,
        "volume_to_ma20_ratio",
        ratio(latest_volume, avg_volume20),
    );
    push_number(
        &mut factors,
        "volume_ma5_to_ma20_ratio",
        ratio(avg_volume5, avg_volume20),
    );
    push_number(
        &mut factors,
        "close_to_close_ma5_pct",
        pct_change(latest_close, avg_close5),
    );
    push_number(&mut factors, "box_position_120d_pct", box_position_120);
    push_number(
        &mut factors,
        "close_to_120d_max_pct",
        pct_change(latest_close, high_120),
    );
    push_number(
        &mut factors,
        "close_to_120d_min_pct",
        pct_change(latest_close, low_120),
    );
    push_number(
        &mut factors,
        "close_to_120d_range_center_pct",
        pct_change(latest_close, range_center_120),
    );
    push_number(
        &mut factors,
        "range_width_120d_pct",
        match (range_width_120, latest_close) {
            (Some(width), Some(close)) if close != 0.0 => Some(width / close * 100.0),
            _ => None,
        },
    );
    push_number(
        &mut factors,
        "close_to_20d_max_close_pct",
        pct_change(latest_close, high_20_close),
    );
    push_number(
        &mut factors,
        "pct_chg_1d",
        pct_change(latest_close, previous.map(|row| row.close)),
    );
    push_flag(
        &mut factors,
        "price_up_1d_flag",
        latest_close
            .zip(previous.map(|row| row.close))
            .map(|(a, b)| a > b),
    );
    push_flag(
        &mut factors,
        "volume_up_1d_flag",
        latest_volume.zip(previous_volume).map(|(a, b)| a > b),
    );
    push_number(
        &mut factors,
        "turnover_to_ma5_ratio",
        ratio(latest_turnover, avg_turnover5),
    );
    push_number(
        &mut factors,
        "macd_dif_to_close_pct",
        pct_of(
            dif.last()
                .copied()
                .flatten()
                .or_else(|| derived_dif.last().copied()),
            latest_close,
        ),
    );
    push_number(
        &mut factors,
        "macd_dea_to_close_pct",
        pct_of(
            dea.last()
                .copied()
                .flatten()
                .or_else(|| derived_dea.last().copied()),
            latest_close,
        ),
    );
    push_number(
        &mut factors,
        "macd_hist_to_close_pct",
        pct_of(latest_macd_hist, latest_close),
    );
    push_number(
        &mut factors,
        "macd_hist_delta_to_close_pct",
        pct_of(macd_hist_delta, latest_close),
    );
    push_number(
        &mut factors,
        "macd_hist_slope_3d_to_close_pct",
        pct_of(macd_hist_slope_3d, latest_close),
    );
    push_flag(
        &mut factors,
        "macd_hist_positive_flag",
        latest_macd_hist.map(|value| value > 0.0),
    );

    push_range_compression(&mut factors, &high, &low, latest_close, 20);
    push_range_compression(&mut factors, &high, &low, latest_close, 40);
    push_abnormal_volume_event_factors(&mut factors, &open, &close, &volume, latest_close);

    factors
}

fn push_range_compression(
    factors: &mut Vec<(String, FactorValue)>,
    high: &[f64],
    low: &[f64],
    latest_close: Option<f64>,
    window: usize,
) {
    let value = if high.len() >= window && low.len() >= window {
        let max_high = high[high.len() - window..]
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        let min_low = low[low.len() - window..]
            .iter()
            .copied()
            .fold(f64::INFINITY, f64::min);
        latest_close.and_then(|close| {
            if close != 0.0 {
                Some((max_high - min_low) / close * 100.0)
            } else {
                None
            }
        })
    } else {
        None
    };
    push_number(factors, &format!("range_compression_{window}d"), value);
}

fn push_abnormal_volume_event_factors(
    factors: &mut Vec<(String, FactorValue)>,
    open: &[f64],
    close: &[f64],
    volume: &[f64],
    latest_close: Option<f64>,
) {
    if volume.is_empty() {
        return;
    }

    let event_start = volume.len().saturating_sub(90);
    let Some((event_offset, event_volume)) = volume[event_start..]
        .iter()
        .copied()
        .enumerate()
        .max_by(|left, right| left.1.total_cmp(&right.1))
    else {
        return;
    };
    let event_idx = event_start + event_offset;
    let event_open = open.get(event_idx).copied();
    let event_close = close.get(event_idx).copied();
    let event_price = event_open
        .zip(event_close)
        .map(|(open, close)| open.max(close))
        .or(event_close);
    let event_volume_ma20 = mean_prefix_tail(volume, event_idx + 1, 20);
    let min_body_after = if event_idx + 1 < close.len() {
        (event_idx + 1..close.len())
            .map(|idx| open[idx].min(close[idx]))
            .reduce(f64::min)
    } else {
        event_open
            .zip(event_close)
            .map(|(open, close)| open.min(close))
    };
    let redundant_price = event_price.map(|price| price * 0.90);

    push_number(
        factors,
        "abnormal_volume_event_days_ago",
        Some((close.len() - 1 - event_idx) as f64),
    );
    push_number(
        factors,
        "abnormal_volume_to_ma20_ratio",
        ratio(Some(event_volume), event_volume_ma20),
    );
    push_number(
        factors,
        "abnormal_event_body_pct",
        event_open
            .zip(event_close)
            .and_then(|(open, close)| pct_change(Some(close), Some(open)))
            .map(f64::abs),
    );
    push_number(
        factors,
        "abnormal_event_price_to_current_pct",
        pct_change(event_price, latest_close),
    );
    push_number(
        factors,
        "post_abnormal_min_body_to_event_price_pct",
        pct_change(min_body_after, event_price),
    );
    push_number(
        factors,
        "post_abnormal_drawdown_pct",
        pct_change(min_body_after, event_price),
    );
    push_number(
        factors,
        "abnormal_redundant_position_pct",
        pct_change(min_body_after, redundant_price),
    );
}

fn required_f64(value: &Value, key: &str) -> anyhow::Result<f64> {
    optional_f64(value, key).ok_or_else(|| anyhow::anyhow!("history row missing {key}"))
}

fn optional_f64(value: &Value, key: &str) -> Option<f64> {
    value.get(key).and_then(Value::as_f64)
}

fn push_number(factors: &mut Vec<(String, FactorValue)>, key: &str, value: Option<f64>) {
    factors.push((
        key.to_string(),
        value
            .map(round4)
            .map_or(FactorValue::Missing, FactorValue::Number),
    ));
}

fn push_flag(factors: &mut Vec<(String, FactorValue)>, key: &str, value: Option<bool>) {
    factors.push((
        key.to_string(),
        value
            .map(|value| if value { 1.0 } else { 0.0 })
            .map_or(FactorValue::Missing, FactorValue::Number),
    ));
}

fn round4(value: f64) -> f64 {
    (value * 10000.0).round() / 10000.0
}

fn mean_tail(values: &[f64], window: usize) -> Option<f64> {
    if values.len() < window || window == 0 {
        return None;
    }
    let tail = &values[values.len() - window..];
    Some(tail.iter().sum::<f64>() / window as f64)
}

fn mean_prefix_tail(values: &[f64], end: usize, window: usize) -> Option<f64> {
    if end < window || window == 0 {
        return None;
    }
    let start = end - window;
    Some(values[start..end].iter().sum::<f64>() / window as f64)
}

fn rolling_mean_series(values: &[f64], window: usize, min_periods: usize) -> Vec<Option<f64>> {
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

fn ema(values: &[f64], span: usize) -> Vec<f64> {
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

fn zx_lines(close: &[f64]) -> (Vec<f64>, Vec<Option<f64>>) {
    let first = ema(close, 10);
    let zxdq = ema(&first, 10);
    let ma14 = rolling_mean_series(close, 14, 14);
    let ma28 = rolling_mean_series(close, 28, 28);
    let ma57 = rolling_mean_series(close, 57, 57);
    let ma114 = rolling_mean_series(close, 114, 114);
    let zxdkx = (0..close.len())
        .map(|idx| match (ma14[idx], ma28[idx], ma57[idx], ma114[idx]) {
            (Some(a), Some(b), Some(c), Some(d)) => Some((a + b + c + d) / 4.0),
            _ => None,
        })
        .collect();
    (zxdq, zxdkx)
}

fn macd_lines(close: &[f64]) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    if close.is_empty() {
        return (Vec::new(), Vec::new(), Vec::new());
    }
    let ema12 = ema(close, 12);
    let ema26 = ema(close, 26);
    let dif = ema12
        .iter()
        .zip(ema26.iter())
        .map(|(fast, slow)| fast - slow)
        .collect::<Vec<_>>();
    let dea = ema(&dif, 9);
    let hist = dif
        .iter()
        .zip(dea.iter())
        .map(|(dif, dea)| dif - dea)
        .collect::<Vec<_>>();
    (dif, dea, hist)
}

fn ratio(current: Option<f64>, base: Option<f64>) -> Option<f64> {
    match (current, base) {
        (Some(current), Some(base)) if base != 0.0 => Some(current / base),
        _ => None,
    }
}

fn pct_change(current: Option<f64>, base: Option<f64>) -> Option<f64> {
    ratio(current, base).map(|ratio| (ratio - 1.0) * 100.0)
}

fn pct_of(current: Option<f64>, base: Option<f64>) -> Option<f64> {
    ratio(current, base).map(|ratio| ratio * 100.0)
}

fn slope_pct_values(values: &[f64], periods: usize) -> Option<f64> {
    if values.len() <= periods {
        return None;
    }
    pct_change(
        values.last().copied(),
        values.get(values.len() - 1 - periods).copied(),
    )
}

fn should_extract_top_level_factor(key: &str, value: &Value) -> bool {
    !matches!(
        key,
        "code"
            | "name"
            | "pick_date"
            | "method"
            | "model_score"
            | "factors"
            | "history"
            | "history_source"
            | "raw_payload"
    ) && matches!(
        value,
        Value::Number(_) | Value::String(_) | Value::Bool(_) | Value::Null
    )
}

fn factor_value_from_json(value: &Value) -> FactorValue {
    match value {
        Value::Number(number) => number
            .as_f64()
            .map(FactorValue::Number)
            .unwrap_or(FactorValue::Missing),
        Value::String(value) => FactorValue::Category(value.clone()),
        Value::Bool(value) => FactorValue::Bool(*value),
        Value::Null => FactorValue::Missing,
        _ => FactorValue::Missing,
    }
}

pub fn artifact_key_for_run(pick_date: NaiveDate, intraday: bool) -> String {
    if intraday {
        format!("{}.intraday", pick_date.format("%Y-%m-%d"))
    } else {
        pick_date.format("%Y-%m-%d").to_string()
    }
}

pub fn candidate_from_legacy_json(
    value: &Value,
    pick_date: NaiveDate,
) -> anyhow::Result<SelectionCandidate> {
    let code = value
        .get("code")
        .and_then(Value::as_str)
        .ok_or_else(|| anyhow::anyhow!("candidate missing code"))?
        .to_string();

    Ok(SelectionCandidate {
        code,
        name: value
            .get("name")
            .and_then(Value::as_str)
            .map(str::to_string),
        method: Method::B2,
        pick_date,
        close: value.get("close").and_then(Value::as_f64),
        turnover_n: value.get("turnover_n").and_then(Value::as_f64),
        signal: value
            .get("signal")
            .and_then(Value::as_str)
            .map(str::to_string),
        raw_payload: value.clone(),
    })
}
