use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

use anyhow::ensure;
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::json;
use stock_cache::{TushareHttpClient, TushareHttpConfig};

use super::types::{FactorRow, FactorValue};
use crate::config::resolve_config_value;

const CYQ_FACTOR_NAMES: [&str; 6] = [
    "cyq_winner_rate",
    "cyq_cost_50_to_close_pct",
    "cyq_cost_85_to_close_pct",
    "cyq_weight_avg_to_close_pct",
    "cyq_cost_70_width_pct",
    "cyq_cost_90_width_pct",
];

const CYQ_PERF_FIELDS: [&str; 9] = [
    "ts_code",
    "trade_date",
    "cost_5pct",
    "cost_15pct",
    "cost_50pct",
    "cost_85pct",
    "cost_95pct",
    "weight_avg",
    "winner_rate",
];

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CyqPerfRow {
    pub ts_code: String,
    pub cost_5pct: Option<f64>,
    pub cost_15pct: Option<f64>,
    pub cost_50pct: Option<f64>,
    pub cost_85pct: Option<f64>,
    pub cost_95pct: Option<f64>,
    pub weight_avg: Option<f64>,
    pub winner_rate: Option<f64>,
}

#[derive(Debug, Default, PartialEq)]
pub(crate) struct CyqEnrichmentReport {
    pub requested_count: usize,
    pub enriched_count: usize,
    pub missing_codes: Vec<String>,
    pub partial_codes: Vec<String>,
    pub cache_hits: usize,
    pub api_rows: usize,
    pub fetch_error: Option<String>,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct CyqPerfCache {
    trade_date: Option<NaiveDate>,
    #[serde(default)]
    fetched_complete: bool,
    rows: BTreeMap<String, CyqPerfRow>,
}

pub(crate) fn attach_cyq_rows(
    factor_rows: &mut [FactorRow],
    trade_date: NaiveDate,
    cyq_by_code: &BTreeMap<String, CyqPerfRow>,
) -> CyqEnrichmentReport {
    let mut report = CyqEnrichmentReport {
        requested_count: factor_rows.len(),
        ..CyqEnrichmentReport::default()
    };
    let trade_date = trade_date.to_string();

    for factor_row in factor_rows {
        let mut status = "missing_row";
        let mut missing_factors = CYQ_FACTOR_NAMES
            .iter()
            .map(|name| (*name).to_string())
            .collect::<Vec<_>>();
        if let Some(cyq_row) = cyq_by_code.get(&factor_row.code) {
            let close = match factor_row.factors.get("close") {
                Some(FactorValue::Number(value)) if value.is_finite() => Some(*value),
                _ => None,
            };
            if let Some(close) = close
                && let Ok(values) = cyq_factors_for_close(cyq_row, close)
            {
                for (name, value) in values {
                    factor_row.factors.insert(name, value);
                }
                missing_factors = CYQ_FACTOR_NAMES
                    .iter()
                    .filter(|name| !factor_row.factors.contains_key(**name))
                    .map(|name| (*name).to_string())
                    .collect();
                if missing_factors.is_empty() {
                    status = "available";
                    report.enriched_count += 1;
                } else if missing_factors.len() < CYQ_FACTOR_NAMES.len() {
                    status = "partial";
                    report.enriched_count += 1;
                    report.partial_codes.push(factor_row.code.clone());
                } else {
                    status = "missing_values";
                    report.missing_codes.push(factor_row.code.clone());
                }
            } else {
                status = "missing_close";
                report.missing_codes.push(factor_row.code.clone());
            }
        } else {
            report.missing_codes.push(factor_row.code.clone());
        }

        factor_row.diagnostics.insert(
            "cyq_perf".to_string(),
            json!({
                "source": "tushare.cyq_perf",
                "trade_date": trade_date,
                "status": status,
                "missing_factors": missing_factors,
            }),
        );
    }
    report
}

pub(crate) fn enrich_factor_rows_from_tushare(
    runtime_root: &Path,
    trade_date: NaiveDate,
    factor_rows: &mut [FactorRow],
) -> CyqEnrichmentReport {
    if factor_rows.is_empty() {
        return CyqEnrichmentReport::default();
    }

    let cache_path = cyq_cache_path(runtime_root, trade_date);
    let mut cache = load_cyq_cache(&cache_path, trade_date);
    let requested_codes = factor_rows
        .iter()
        .map(|row| row.code.clone())
        .collect::<BTreeSet<_>>();
    let cache_hits = requested_codes
        .iter()
        .filter(|code| cache.rows.contains_key(*code))
        .count();
    let missing_codes = requested_codes
        .difference(&cache.rows.keys().cloned().collect())
        .cloned()
        .collect::<BTreeSet<_>>();
    let mut api_rows = 0;
    let mut fetch_error = None;

    if !cache.fetched_complete && !missing_codes.is_empty() {
        match resolve_config_value(None, "TUSHARE_TOKEN") {
            None => fetch_error = Some("TUSHARE_TOKEN is not configured".to_string()),
            Some(token) => match fetch_cyq_perf_for_date(&token, trade_date) {
                Ok(rows) if rows.is_empty() => {
                    fetch_error =
                        Some("Tushare returned no cyq_perf rows for the date".to_string());
                }
                Ok(rows) => {
                    api_rows = rows.len();
                    let rows_by_code = rows
                        .into_iter()
                        .map(|row| (row.ts_code.clone(), row))
                        .collect::<BTreeMap<_, _>>();
                    cache.rows = rows_by_code
                        .into_iter()
                        .filter(|(_, row)| row_has_values(row))
                        .collect();
                    cache.trade_date = Some(trade_date);
                    cache.fetched_complete = true;
                    if let Err(error) = save_cyq_cache(&cache_path, &cache) {
                        fetch_error = Some(format!("could not persist CYQ cache: {error}"));
                    }
                }
                Err(error) => fetch_error = Some(format!("cyq_perf request failed: {error:#}")),
            },
        }
    }

    let mut report = attach_cyq_rows(factor_rows, trade_date, &cache.rows);
    report.cache_hits = cache_hits;
    report.api_rows = api_rows;
    report.fetch_error = fetch_error.clone();
    if let Some(error) = fetch_error {
        for row in factor_rows.iter_mut() {
            if row.diagnostics["cyq_perf"]["status"] != "available" {
                let status = row.diagnostics["cyq_perf"]["status"]
                    .as_str()
                    .unwrap_or("missing_row")
                    .to_string();
                let missing_factors = row.diagnostics["cyq_perf"]["missing_factors"].clone();
                row.diagnostics.insert(
                    "cyq_perf".to_string(),
                    json!({
                        "source": "tushare.cyq_perf",
                        "trade_date": trade_date.to_string(),
                        "status": status,
                        "reason": error,
                        "missing_factors": missing_factors,
                    }),
                );
            }
        }
    }
    report
}

pub(crate) fn log_cyq_enrichment(
    context: &str,
    trade_date: NaiveDate,
    report: &CyqEnrichmentReport,
) {
    if report.requested_count == 0 {
        return;
    }
    eprintln!(
        "[cyq] {context} trade_date={trade_date} covered={}/{} cache_hits={} api_rows={} missing={}",
        report.enriched_count,
        report.requested_count,
        report.cache_hits,
        report.api_rows,
        report.missing_codes.len()
    );
    if let Some(reason) = &report.fetch_error {
        eprintln!("[cyq] warning trade_date={trade_date}: {reason}");
    }
    if !report.missing_codes.is_empty() {
        let sample = report
            .missing_codes
            .iter()
            .take(10)
            .map(String::as_str)
            .collect::<Vec<_>>()
            .join(",");
        eprintln!(
            "[cyq] warning trade_date={trade_date} missing_rows={} sample_codes={sample}",
            report.missing_codes.len()
        );
    }
    if !report.partial_codes.is_empty() {
        eprintln!(
            "[cyq] warning trade_date={trade_date} partial_rows={}",
            report.partial_codes.len()
        );
    }
}

fn fetch_cyq_perf_for_date(token: &str, trade_date: NaiveDate) -> anyhow::Result<Vec<CyqPerfRow>> {
    let mut config = TushareHttpConfig::new(token);
    config.page_size = 6_000;
    if let Some(endpoint) = resolve_config_value(None, "TUSHARE_ENDPOINT") {
        config.endpoint = endpoint;
    }
    let client = TushareHttpClient::new(config)?;
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()?;
    let params = BTreeMap::from([(
        "trade_date".to_string(),
        json!(trade_date.format("%Y%m%d").to_string()),
    )]);
    let rows = runtime.block_on(client.fetch_api("cyq_perf", &CYQ_PERF_FIELDS, &params))?;
    Ok(rows.iter().filter_map(decode_cyq_perf_row).collect())
}

fn decode_cyq_perf_row(raw: &BTreeMap<String, serde_json::Value>) -> Option<CyqPerfRow> {
    Some(CyqPerfRow {
        ts_code: raw.get("ts_code")?.as_str()?.to_string(),
        cost_5pct: value_as_f64(raw.get("cost_5pct")),
        cost_15pct: value_as_f64(raw.get("cost_15pct")),
        cost_50pct: value_as_f64(raw.get("cost_50pct")),
        cost_85pct: value_as_f64(raw.get("cost_85pct")),
        cost_95pct: value_as_f64(raw.get("cost_95pct")),
        weight_avg: value_as_f64(raw.get("weight_avg")),
        winner_rate: value_as_f64(raw.get("winner_rate")),
    })
}

fn value_as_f64(value: Option<&serde_json::Value>) -> Option<f64> {
    let number = value?.as_f64().or_else(|| value?.as_str()?.parse().ok())?;
    number.is_finite().then_some(number)
}

fn row_has_values(row: &CyqPerfRow) -> bool {
    row.cost_5pct.is_some()
        || row.cost_15pct.is_some()
        || row.cost_50pct.is_some()
        || row.cost_85pct.is_some()
        || row.cost_95pct.is_some()
        || row.weight_avg.is_some()
        || row.winner_rate.is_some()
}

fn cyq_cache_path(runtime_root: &Path, trade_date: NaiveDate) -> PathBuf {
    runtime_root
        .join("cyq_perf")
        .join(format!("{}.json", trade_date.format("%Y-%m-%d")))
}

fn load_cyq_cache(path: &Path, trade_date: NaiveDate) -> CyqPerfCache {
    std::fs::read(path)
        .ok()
        .and_then(|bytes| serde_json::from_slice::<CyqPerfCache>(&bytes).ok())
        .filter(|cache| cache.trade_date == Some(trade_date))
        .unwrap_or_default()
}

fn save_cyq_cache(path: &Path, cache: &CyqPerfCache) -> anyhow::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| anyhow::anyhow!("CYQ cache path has no parent directory"))?;
    std::fs::create_dir_all(parent)?;
    let temporary_path = path.with_extension(format!("{}.tmp", std::process::id()));
    std::fs::write(&temporary_path, serde_json::to_vec(cache)?)?;
    std::fs::rename(temporary_path, path)?;
    Ok(())
}

pub fn cyq_factors_for_close(
    row: &CyqPerfRow,
    close: f64,
) -> anyhow::Result<BTreeMap<String, FactorValue>> {
    ensure!(
        close.is_finite() && close > 0.0,
        "close must be positive and finite"
    );

    let mut factors = BTreeMap::new();
    insert_number(&mut factors, "cyq_winner_rate", row.winner_rate);
    insert_number(
        &mut factors,
        "cyq_cost_50_to_close_pct",
        relative_to_close(row.cost_50pct, close),
    );
    insert_number(
        &mut factors,
        "cyq_cost_85_to_close_pct",
        relative_to_close(row.cost_85pct, close),
    );
    insert_number(
        &mut factors,
        "cyq_weight_avg_to_close_pct",
        relative_to_close(row.weight_avg, close),
    );
    insert_number(
        &mut factors,
        "cyq_cost_70_width_pct",
        band_width(row.cost_15pct, row.cost_85pct, close),
    );
    insert_number(
        &mut factors,
        "cyq_cost_90_width_pct",
        band_width(row.cost_5pct, row.cost_95pct, close),
    );
    Ok(factors)
}

fn relative_to_close(value: Option<f64>, close: f64) -> Option<f64> {
    value
        .filter(|value| value.is_finite())
        .map(|value| round4((value / close - 1.0) * 100.0))
}

fn band_width(lower: Option<f64>, upper: Option<f64>, close: f64) -> Option<f64> {
    let (Some(lower), Some(upper)) = (lower, upper) else {
        return None;
    };
    if !lower.is_finite() || !upper.is_finite() {
        return None;
    }
    Some(round4((upper - lower) / close * 100.0))
}

fn insert_number(factors: &mut BTreeMap<String, FactorValue>, name: &str, value: Option<f64>) {
    if let Some(value) = value.filter(|value| value.is_finite()) {
        factors.insert(name.to_string(), FactorValue::Number(value));
    }
}

fn round4(value: f64) -> f64 {
    (value * 10_000.0).round() / 10_000.0
}

#[cfg(test)]
mod tests {
    use super::{CyqPerfRow, attach_cyq_rows, cyq_factors_for_close, decode_cyq_perf_row};
    use crate::{
        factors::types::{FactorRow, FactorValue},
        model::Method,
    };
    use chrono::NaiveDate;
    use serde_json::{Value, json};
    use std::collections::BTreeMap;

    #[test]
    fn cyq_perf_maps_to_close_relative_factors() {
        let row = CyqPerfRow {
            ts_code: "000001.SZ".to_string(),
            cost_5pct: Some(8.0),
            cost_15pct: Some(9.0),
            cost_50pct: Some(9.5),
            cost_85pct: Some(11.0),
            cost_95pct: Some(12.0),
            weight_avg: Some(10.2),
            winner_rate: Some(53.2),
        };

        let factors = cyq_factors_for_close(&row, 10.0).unwrap();

        assert_eq!(factors["cyq_winner_rate"], FactorValue::Number(53.2));
        assert_eq!(
            factors["cyq_cost_50_to_close_pct"],
            FactorValue::Number(-5.0)
        );
        assert_eq!(
            factors["cyq_cost_85_to_close_pct"],
            FactorValue::Number(10.0)
        );
        assert_eq!(
            factors["cyq_weight_avg_to_close_pct"],
            FactorValue::Number(2.0)
        );
        assert_eq!(factors["cyq_cost_70_width_pct"], FactorValue::Number(20.0));
        assert_eq!(factors["cyq_cost_90_width_pct"], FactorValue::Number(40.0));
    }

    #[test]
    fn cyq_rows_enrich_factor_rows_and_report_missing_symbols() {
        let date = NaiveDate::from_ymd_opt(2026, 11, 19).unwrap();
        let mut factors = vec![factor_row("000001.SZ", 10.0), factor_row("000002.SZ", 20.0)];
        let cyq_rows = BTreeMap::from([("000001.SZ".to_string(), sample_cyq_row())]);

        let report = attach_cyq_rows(&mut factors, date, &cyq_rows);

        assert_eq!(report.requested_count, 2);
        assert_eq!(report.enriched_count, 1);
        assert_eq!(report.missing_codes, ["000002.SZ"]);
        assert_eq!(
            factors[0].factors["cyq_winner_rate"],
            FactorValue::Number(53.2)
        );
        assert_eq!(factors[0].diagnostics["cyq_perf"]["status"], "available");
        assert_eq!(
            factors[0].diagnostics["cyq_perf"]["trade_date"],
            "2026-11-19"
        );
        assert_eq!(factors[1].diagnostics["cyq_perf"]["status"], "missing_row");
    }

    #[test]
    fn complete_date_cache_is_reused_without_requiring_a_token() {
        let temp = tempfile::tempdir().unwrap();
        let date = NaiveDate::from_ymd_opt(2026, 11, 19).unwrap();
        let cache_path = super::cyq_cache_path(temp.path(), date);
        super::save_cyq_cache(
            &cache_path,
            &super::CyqPerfCache {
                trade_date: Some(date),
                fetched_complete: true,
                rows: BTreeMap::from([("000001.SZ".to_string(), sample_cyq_row())]),
            },
        )
        .unwrap();
        let mut factors = vec![factor_row("000001.SZ", 10.0)];

        let report = super::enrich_factor_rows_from_tushare(temp.path(), date, &mut factors);

        assert_eq!(report.enriched_count, 1);
        assert_eq!(report.cache_hits, 1);
        assert_eq!(report.api_rows, 0);
        assert_eq!(report.fetch_error, None);
        assert_eq!(
            factors[0].factors["cyq_winner_rate"],
            FactorValue::Number(53.2)
        );
    }

    #[test]
    fn decodes_tushare_cyq_perf_numeric_strings_and_nulls() {
        let raw = BTreeMap::from([
            ("ts_code".to_string(), json!("000001.SZ")),
            ("cost_5pct".to_string(), json!(8.0)),
            ("cost_15pct".to_string(), json!("9.0")),
            ("cost_50pct".to_string(), json!(9.5)),
            ("cost_85pct".to_string(), json!(11.0)),
            ("cost_95pct".to_string(), json!(12.0)),
            ("weight_avg".to_string(), Value::Null),
            ("winner_rate".to_string(), json!(53.2)),
        ]);

        let row = decode_cyq_perf_row(&raw).unwrap();

        assert_eq!(row.ts_code, "000001.SZ");
        assert_eq!(row.cost_15pct, Some(9.0));
        assert_eq!(row.weight_avg, None);
        assert_eq!(row.winner_rate, Some(53.2));
    }

    fn factor_row(code: &str, close: f64) -> FactorRow {
        FactorRow {
            code: code.to_string(),
            method: Method::B2,
            factors: BTreeMap::from([("close".to_string(), FactorValue::Number(close))]),
            diagnostics: BTreeMap::new(),
        }
    }

    fn sample_cyq_row() -> CyqPerfRow {
        CyqPerfRow {
            ts_code: "000001.SZ".to_string(),
            cost_5pct: Some(8.0),
            cost_15pct: Some(9.0),
            cost_50pct: Some(9.5),
            cost_85pct: Some(11.0),
            cost_95pct: Some(12.0),
            weight_avg: Some(10.2),
            winner_rate: Some(53.2),
        }
    }
}
