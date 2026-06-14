use anyhow::Context;
use chrono::NaiveDate;
use serde_json::Value;

use crate::engine::types::{FactorRow, FactorValue, SelectionCandidate};
use crate::factors::registry::{
    factor_profile_for_method, history_factor_fields_for_method, record_factor_profile_diagnostics,
    remove_review_only_factors,
};
use crate::factors::types::FactorInputRow;
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

        let profile = factor_profile_for_method(candidate.method);
        let history_factor_count = if let Some(history) = candidate.raw_payload.get("history") {
            let history = parse_history_rows(history)
                .with_context(|| format!("parse history for {}", candidate.code))?;
            let signal = candidate.signal.as_deref();
            let env = candidate
                .raw_payload
                .get("env")
                .and_then(Value::as_str)
                .or_else(|| {
                    row.factors.get("env").and_then(|value| match value {
                        FactorValue::Category(value) => Some(value.as_str()),
                        _ => None,
                    })
                });
            let factors = history_factor_fields_for_method(candidate.method, &history, signal, env);
            let count = factors.len();
            for (key, value) in factors {
                row.factors.insert(key, value);
            }
            remove_review_only_factors(&mut row);
            Some(count)
        } else {
            None
        };

        row.diagnostics.insert(
            "factor_source".to_string(),
            Value::String("candidate_payload".to_string()),
        );
        record_factor_profile_diagnostics(&mut row, profile);
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

fn parse_history_rows(value: &Value) -> anyhow::Result<Vec<FactorInputRow>> {
    let rows = value
        .as_array()
        .ok_or_else(|| anyhow::anyhow!("candidate history must be a JSON array"))?;
    rows.iter()
        .map(|row| {
            Ok(FactorInputRow {
                trade_date: optional_date(row, "trade_date"),
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
                turnover_rate: optional_f64(row, "turnover_rate"),
                d: optional_f64(row, "d").or_else(|| optional_f64(row, "D")),
                j: optional_f64(row, "j"),
                ma25: optional_f64(row, "ma25"),
                ma60: optional_f64(row, "ma60"),
                zxdkx: optional_f64(row, "zxdkx"),
                zxdq: optional_f64(row, "zxdq"),
                dif: optional_f64(row, "dif").or_else(|| optional_f64(row, "macd_dif")),
                dea: optional_f64(row, "dea").or_else(|| optional_f64(row, "macd_dea")),
                macd_hist: optional_f64(row, "macd_hist"),
                db_factors: parse_db_factors(row),
            })
        })
        .collect()
}

fn parse_db_factors(value: &Value) -> std::collections::BTreeMap<String, f64> {
    value
        .get("db_factors")
        .and_then(Value::as_object)
        .map(|object| {
            object
                .iter()
                .filter_map(|(key, value)| value.as_f64().map(|value| (key.clone(), value)))
                .collect()
        })
        .unwrap_or_default()
}

fn required_f64(value: &Value, key: &str) -> anyhow::Result<f64> {
    optional_f64(value, key).ok_or_else(|| anyhow::anyhow!("history row missing {key}"))
}

fn optional_f64(value: &Value, key: &str) -> Option<f64> {
    value.get(key).and_then(Value::as_f64)
}

fn optional_date(value: &Value, key: &str) -> Option<NaiveDate> {
    value
        .get(key)
        .and_then(Value::as_str)
        .and_then(|value| NaiveDate::parse_from_str(value, "%Y-%m-%d").ok())
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

pub(crate) fn adjust_b2_cyq_post_rerank_score(score: f64, row: &FactorRow) -> f64 {
    match factor_category(row, "env") {
        Some("neutral") => {
            let penalty = factor_number(row, "cyq_winner_rate")
                .map(|winner_rate| ((winner_rate - 80.0) / 20.0).clamp(0.0, 1.0) * 0.14)
                .unwrap_or(0.0);
            score - penalty
        }
        Some("strong") => {
            let penalty = match factor_number(row, "cyq_cost_90_width_pct") {
                Some(width) if width > 25.0 => 0.35,
                _ => 0.0,
            };
            score - penalty
        }
        _ => score,
    }
}

fn factor_number(row: &FactorRow, key: &str) -> Option<f64> {
    match row.factors.get(key) {
        Some(FactorValue::Number(value)) if value.is_finite() => Some(*value),
        _ => None,
    }
}

fn factor_category<'a>(row: &'a FactorRow, key: &str) -> Option<&'a str> {
    match row.factors.get(key) {
        Some(FactorValue::Category(value)) => Some(value.as_str()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn factor_row(code: &str, env: &str) -> FactorRow {
        let mut row = FactorRow::new(code, Method::B2);
        row.factors
            .insert("env".to_string(), FactorValue::Category(env.to_string()));
        row
    }

    #[test]
    fn cyq_post_rerank_penalizes_neutral_high_winner_rate() {
        let mut row = factor_row("000001.SZ", "neutral");
        row.factors
            .insert("cyq_winner_rate".to_string(), FactorValue::Number(90.0));

        let adjusted = adjust_b2_cyq_post_rerank_score(1.0, &row);

        assert!((adjusted - 0.93).abs() < 1e-9);
    }

    #[test]
    fn cyq_post_rerank_penalizes_strong_wide_cost_distribution() {
        let mut row = factor_row("000001.SZ", "strong");
        row.factors.insert(
            "cyq_cost_90_width_pct".to_string(),
            FactorValue::Number(25.1),
        );

        let adjusted = adjust_b2_cyq_post_rerank_score(1.0, &row);

        assert!((adjusted - 0.65).abs() < 1e-9);
    }

    #[test]
    fn cyq_post_rerank_leaves_weak_environment_unchanged() {
        let mut row = factor_row("000001.SZ", "weak");
        row.factors
            .insert("cyq_winner_rate".to_string(), FactorValue::Number(100.0));
        row.factors.insert(
            "cyq_cost_90_width_pct".to_string(),
            FactorValue::Number(40.0),
        );

        let adjusted = adjust_b2_cyq_post_rerank_score(1.0, &row);

        assert_eq!(adjusted, 1.0);
    }
}
