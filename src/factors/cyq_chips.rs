use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

use anyhow::{Context, ensure};
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use stock_cache::{TushareHttpClient, TushareHttpConfig};

use super::{
    cyq::CyqEnrichmentReport,
    types::{FactorRow, FactorValue},
};
use crate::config::resolve_config_value;

const CYQ_CHIPS_FIELDS: [&str; 4] = ["ts_code", "trade_date", "price", "percent"];

pub const CYQ_CHIPS_FACTOR_NAMES: [&str; 5] = [
    "cyq_chips_near_close_5pct",
    "cyq_chips_overhead_10pct",
    "cyq_chips_support_10pct",
    "cyq_chips_peak_to_close_pct",
    "cyq_chips_std_to_close_pct",
];

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CyqChip {
    pub price: f64,
    pub percent: f64,
}

pub fn chips_factors_for_close(
    chips: &[CyqChip],
    close: f64,
) -> anyhow::Result<BTreeMap<String, FactorValue>> {
    ensure!(
        close.is_finite() && close > 0.0,
        "close must be positive and finite"
    );
    validate_distribution(chips)?;
    let mut sorted = chips.to_vec();
    sorted.sort_by(|a, b| a.price.total_cmp(&b.price));
    let mut bins: Vec<CyqChip> = Vec::new();
    for chip in sorted {
        if let Some(last) = bins.last_mut()
            && last.price == chip.price
        {
            last.percent += chip.percent;
        } else {
            bins.push(chip);
        }
    }
    let total: f64 = bins.iter().map(|chip| chip.percent).sum();
    let mean = bins
        .iter()
        .map(|chip| chip.price * (chip.percent / total))
        .sum::<f64>();
    let variance = bins
        .iter()
        .map(|chip| (chip.price - mean).powi(2) * (chip.percent / total))
        .sum::<f64>();
    // 同权主峰固定取低价，避免返回行顺序影响结果。
    let peak = bins
        .iter()
        .reduce(|best, chip| {
            if chip.percent > best.percent {
                chip
            } else {
                best
            }
        })
        .unwrap();
    let share = |lower: f64, upper: f64, exclude_close: bool| {
        bins.iter()
            .filter(|chip| {
                chip.price >= lower
                    && chip.price <= upper
                    && (!exclude_close || chip.price != close)
            })
            .map(|chip| chip.percent / total * 100.0)
            .sum::<f64>()
    };
    let values = [
        share(close * 0.95, close * 1.05, false),
        share(close, close * 1.10, true),
        share(close * 0.90, close, true),
        (peak.price / close - 1.0) * 100.0,
        variance.sqrt() / close * 100.0,
    ];
    ensure!(
        values.iter().all(|value| value.is_finite()),
        "non-finite chip factors"
    );
    Ok(CYQ_CHIPS_FACTOR_NAMES
        .into_iter()
        .zip(values)
        .map(|(name, value)| {
            (
                name.to_string(),
                FactorValue::Number((value * 10_000.0).round() / 10_000.0),
            )
        })
        .collect())
}

fn validate_distribution(chips: &[CyqChip]) -> anyhow::Result<()> {
    ensure!(!chips.is_empty(), "Tushare returned no cyq_chips rows");
    ensure!(
        chips.iter().all(|chip| chip.price.is_finite()
            && chip.price > 0.0
            && chip.percent.is_finite()
            && chip.percent >= 0.0),
        "invalid cyq_chips price or percent"
    );
    let total: f64 = chips.iter().map(|chip| chip.percent).sum();
    // percent 保留两位小数；允许逐档舍入误差，但不把截断分布归一化为完整分布。
    let tolerance = (chips.len() as f64 * 0.005 + 1e-6).max(1.0);
    ensure!(
        total.is_finite() && total > 0.0 && (total - 100.0).abs() <= tolerance,
        "incomplete cyq_chips distribution: total percent={total}"
    );
    Ok(())
}

#[derive(Serialize, Deserialize)]
struct ChipsCache {
    version: u32,
    trade_date: NaiveDate,
    ts_code: String,
    rows: Vec<CyqChip>,
}

pub(crate) fn enrich_chip_factor_rows_from_tushare(
    runtime_root: &Path,
    trade_date: NaiveDate,
    factor_rows: &mut [FactorRow],
) -> CyqEnrichmentReport {
    // 延迟构建客户端，缓存全命中时不需要 token 或网络。
    let mut fetcher = None;
    enrich_chips_with_fetcher(runtime_root, trade_date, factor_rows, |code, date| {
        if fetcher.is_none() {
            fetcher = Some(ChipsFetcher::from_config()?);
        }
        fetcher.as_ref().unwrap().fetch(code, date)
    })
}

fn enrich_chips_with_fetcher(
    runtime_root: &Path,
    trade_date: NaiveDate,
    factor_rows: &mut [FactorRow],
    mut fetch: impl FnMut(&str, NaiveDate) -> anyhow::Result<Vec<CyqChip>>,
) -> CyqEnrichmentReport {
    let mut report = CyqEnrichmentReport {
        requested_count: factor_rows.len(),
        ..Default::default()
    };
    let requested_codes: BTreeSet<_> = factor_rows
        .iter()
        .filter(|row| row_close(row).is_some())
        .map(|row| row.code.clone())
        .collect();
    let mut distributions = BTreeMap::new();
    let mut errors = BTreeMap::new();
    for code in requested_codes {
        if !valid_ts_code(&code) {
            errors.insert(code, "invalid ts_code".to_string());
            continue;
        }
        let path = chips_cache_path(runtime_root, trade_date, &code);
        let cached = std::fs::read(&path)
            .ok()
            .and_then(|bytes| serde_json::from_slice::<ChipsCache>(&bytes).ok())
            .filter(|cache| {
                cache.version == 1 && cache.trade_date == trade_date && cache.ts_code == code
            })
            .filter(|cache| validate_distribution(&cache.rows).is_ok());
        let chips = if let Some(cache) = cached {
            report.cache_hits += 1;
            cache.rows
        } else {
            match fetch(&code, trade_date).and_then(|chips| {
                validate_distribution(&chips)?;
                Ok(chips)
            }) {
                Ok(chips) => {
                    report.api_rows += chips.len();
                    let cache = ChipsCache {
                        version: 1,
                        trade_date,
                        ts_code: code.clone(),
                        rows: chips.clone(),
                    };
                    if let Err(error) = save_chips_cache(&path, &cache) {
                        errors.insert(
                            code.clone(),
                            format!("could not persist cyq_chips cache: {error}"),
                        );
                    }
                    chips
                }
                Err(error) => {
                    errors.insert(code, format!("{error:#}"));
                    continue;
                }
            }
        };
        distributions.insert(code, chips);
    }
    for row in factor_rows {
        for name in CYQ_CHIPS_FACTOR_NAMES {
            row.factors.remove(name);
        }
        let mut diagnostic = json!({
            "source": "tushare.cyq_chips",
            "trade_date": trade_date.to_string(),
            "status": "missing_row",
            "missing_factors": CYQ_CHIPS_FACTOR_NAMES,
        });
        if let Some(close) = row_close(row) {
            if let Some(chips) = distributions.get(&row.code) {
                match chips_factors_for_close(chips, close) {
                    Ok(values) => {
                        row.factors.extend(values);
                        diagnostic["status"] = json!("available");
                        diagnostic["missing_factors"] = json!([]);
                        diagnostic["price_bin_count"] = json!(chips.len());
                        diagnostic["total_percent"] =
                            json!(chips.iter().map(|chip| chip.percent).sum::<f64>());
                        report.enriched_count += 1;
                    }
                    Err(error) => {
                        diagnostic["reason"] = json!(error.to_string());
                    }
                }
            }
        } else {
            diagnostic["status"] = json!("missing_close");
        }
        if let Some(error) = errors.get(&row.code) {
            diagnostic["reason"] = json!(error);
        }
        if diagnostic["status"] != "available" {
            report.missing_codes.push(row.code.clone());
        }
        row.diagnostics.insert("cyq_chips".to_string(), diagnostic);
    }
    if !errors.is_empty() {
        report.fetch_error = Some(
            errors
                .iter()
                .take(10)
                .map(|(code, error)| format!("{code}: {error}"))
                .collect::<Vec<_>>()
                .join("; "),
        );
    }
    report
}

fn row_close(row: &FactorRow) -> Option<f64> {
    match row.factors.get("close") {
        Some(FactorValue::Number(close)) if close.is_finite() && *close > 0.0 => Some(*close),
        _ => None,
    }
}

fn valid_ts_code(code: &str) -> bool {
    code.len() == 9
        && code.as_bytes()[..6].iter().all(u8::is_ascii_digit)
        && matches!(&code[6..], ".SH" | ".SZ" | ".BJ")
}

fn chips_cache_path(runtime_root: &Path, trade_date: NaiveDate, code: &str) -> PathBuf {
    runtime_root
        .join("cyq_chips")
        .join(trade_date.to_string())
        .join(format!("{code}.json"))
}

fn save_chips_cache(path: &Path, cache: &ChipsCache) -> anyhow::Result<()> {
    std::fs::create_dir_all(
        path.parent()
            .context("cyq_chips cache path has no parent")?,
    )?;
    let temporary = path.with_extension(format!("{}.tmp", std::process::id()));
    std::fs::write(&temporary, serde_json::to_vec(cache)?)?;
    std::fs::rename(temporary, path)?;
    Ok(())
}

struct ChipsFetcher {
    client: TushareHttpClient,
    runtime: tokio::runtime::Runtime,
}

impl ChipsFetcher {
    fn from_config() -> anyhow::Result<Self> {
        let token = resolve_config_value(None, "TUSHARE_TOKEN")
            .context("TUSHARE_TOKEN is not configured")?;
        let mut config = TushareHttpConfig::new(token);
        config.page_size = 6_000;
        config.requests_per_minute = 180;
        if let Some(endpoint) = resolve_config_value(None, "TUSHARE_ENDPOINT") {
            config.endpoint = endpoint;
        }
        Ok(Self {
            client: TushareHttpClient::new(config)?,
            runtime: tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()?,
        })
    }

    fn fetch(&self, code: &str, trade_date: NaiveDate) -> anyhow::Result<Vec<CyqChip>> {
        let params = BTreeMap::from([
            ("ts_code".to_string(), json!(code)),
            (
                "trade_date".to_string(),
                json!(trade_date.format("%Y%m%d").to_string()),
            ),
        ]);
        let rows = self.runtime.block_on(self.client.fetch_api(
            "cyq_chips",
            &CYQ_CHIPS_FIELDS,
            &params,
        ))?;
        decode_chips_rows(&rows, code, trade_date)
    }
}

fn decode_chips_rows(
    rows: &[BTreeMap<String, Value>],
    code: &str,
    trade_date: NaiveDate,
) -> anyhow::Result<Vec<CyqChip>> {
    let date = trade_date.format("%Y%m%d").to_string();
    rows.iter()
        .map(|row| {
            ensure!(
                row.get("ts_code").and_then(Value::as_str) == Some(code)
                    && row.get("trade_date").and_then(Value::as_str) == Some(date.as_str()),
                "cyq_chips returned another symbol or date"
            );
            let number = |key| {
                row.get(key)
                    .and_then(|value| value.as_f64().or_else(|| value.as_str()?.parse().ok()))
                    .filter(|value| value.is_finite())
            };
            Ok(CyqChip {
                price: number("price").context("invalid cyq_chips price")?,
                percent: number("percent").context("invalid cyq_chips percent")?,
            })
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn distribution() -> Vec<CyqChip> {
        [
            (8.0, 10.0),
            (9.0, 20.0),
            (10.0, 40.0),
            (11.0, 20.0),
            (12.0, 10.0),
        ]
        .into_iter()
        .map(|(price, percent)| CyqChip { price, percent })
        .collect()
    }

    #[test]
    fn chips_distribution_maps_to_shape_factors() {
        let values = chips_factors_for_close(&distribution(), 10.0).unwrap();
        assert_eq!(values.len(), 5);
        assert_eq!(
            values["cyq_chips_near_close_5pct"],
            FactorValue::Number(40.0)
        );
        assert_eq!(
            values["cyq_chips_overhead_10pct"],
            FactorValue::Number(20.0)
        );
        assert_eq!(values["cyq_chips_support_10pct"], FactorValue::Number(20.0));
        assert_eq!(
            values["cyq_chips_peak_to_close_pct"],
            FactorValue::Number(0.0)
        );
        assert_eq!(
            values["cyq_chips_std_to_close_pct"],
            FactorValue::Number(10.9545)
        );
    }

    #[test]
    fn chips_normalize_rounding_and_merge_duplicate_prices_before_finding_peak() {
        let chips = vec![
            CyqChip {
                price: 11.0,
                percent: 49.9,
            },
            CyqChip {
                price: 9.0,
                percent: 25.0,
            },
            CyqChip {
                price: 9.0,
                percent: 25.0,
            },
        ];
        let values = chips_factors_for_close(&chips, 10.0).unwrap();
        assert_eq!(
            values["cyq_chips_peak_to_close_pct"],
            FactorValue::Number(-10.0)
        );
        assert_eq!(
            values["cyq_chips_support_10pct"],
            FactorValue::Number(50.0501)
        );
        let mut reversed = chips.clone();
        reversed.reverse();
        assert_eq!(values, chips_factors_for_close(&reversed, 10.0).unwrap());
    }

    #[test]
    fn chips_reject_invalid_or_incomplete_distributions_and_close() {
        for chips in [
            vec![],
            vec![CyqChip {
                price: 10.0,
                percent: 0.0,
            }],
            vec![CyqChip {
                price: 10.0,
                percent: 40.0,
            }],
            vec![CyqChip {
                price: 0.0,
                percent: 100.0,
            }],
            vec![CyqChip {
                price: f64::NAN,
                percent: 100.0,
            }],
            vec![CyqChip {
                price: 10.0,
                percent: f64::INFINITY,
            }],
            vec![
                CyqChip {
                    price: 9.0,
                    percent: -1.0,
                },
                CyqChip {
                    price: 10.0,
                    percent: 101.0,
                },
            ],
        ] {
            assert!(chips_factors_for_close(&chips, 10.0).is_err());
        }
        for close in [0.0, -1.0, f64::NAN, f64::INFINITY] {
            assert!(chips_factors_for_close(&distribution(), close).is_err());
        }
    }

    #[test]
    fn chips_fetch_only_uncached_candidates_and_share_cache_between_methods() {
        let root = tempfile::tempdir().unwrap();
        let date = chrono::NaiveDate::from_ymd_opt(2026, 1, 5).unwrap();
        let mut rows = vec![factor_row("000001.SZ"), factor_row("000001.SZ")];
        let mut fetched = Vec::new();
        let report =
            enrich_chips_with_fetcher(root.path(), date, &mut rows, |code, requested_date| {
                assert_eq!(requested_date, date);
                fetched.push(code.to_string());
                Ok(distribution())
            });
        assert_eq!(fetched, ["000001.SZ"]);
        assert_eq!(report.enriched_count, 2);
        assert_eq!(report.api_rows, 5);
        let mut rows = vec![factor_row("000001.SZ"), factor_row("000002.SZ")];
        rows[0].method = crate::model::Method::Scm;
        let report = enrich_chips_with_fetcher(root.path(), date, &mut rows, |code, _| {
            assert_eq!(code, "000002.SZ");
            Ok(distribution())
        });
        assert_eq!(report.cache_hits, 1);
        assert_eq!(report.enriched_count, 2);
        assert_eq!(rows[0].diagnostics["cyq_chips"]["status"], "available");
        assert_eq!(
            rows[0].factors["cyq_chips_near_close_5pct"],
            FactorValue::Number(40.0)
        );
    }

    #[test]
    fn chips_failures_remain_missing_and_are_retried_instead_of_negative_cached() {
        let root = tempfile::tempdir().unwrap();
        let date = chrono::NaiveDate::from_ymd_opt(2026, 1, 5).unwrap();
        let mut rows = vec![factor_row("000001.SZ"), factor_row("000002.SZ")];
        let report = enrich_chips_with_fetcher(root.path(), date, &mut rows, |code, _| {
            if code == "000001.SZ" {
                anyhow::bail!("TUSHARE_TOKEN is not configured");
            }
            Ok(vec![])
        });
        assert_eq!(report.enriched_count, 0);
        assert_eq!(report.missing_codes, ["000001.SZ", "000002.SZ"]);
        assert_eq!(rows[0].diagnostics["cyq_chips"]["status"], "missing_row");
        assert!(
            rows[0].diagnostics["cyq_chips"]["reason"]
                .as_str()
                .unwrap()
                .contains("TUSHARE_TOKEN")
        );
        assert!(!rows[0].factors.contains_key("cyq_chips_near_close_5pct"));
        let report =
            enrich_chips_with_fetcher(root.path(), date, &mut rows, |_, _| Ok(distribution()));
        assert_eq!(report.cache_hits, 0);
        assert_eq!(report.enriched_count, 2);
    }

    #[test]
    fn chips_skip_rows_without_close_and_reject_cache_for_another_date() {
        let root = tempfile::tempdir().unwrap();
        let date = chrono::NaiveDate::from_ymd_opt(2026, 1, 5).unwrap();
        let mut rows = vec![factor_row("000001.SZ")];
        rows[0].factors.clear();
        let report =
            enrich_chips_with_fetcher(root.path(), date, &mut rows, |_, _| panic!("no close"));
        assert_eq!(report.enriched_count, 0);
        assert_eq!(rows[0].diagnostics["cyq_chips"]["status"], "missing_close");
        rows[0] = factor_row("000001.SZ");
        enrich_chips_with_fetcher(root.path(), date, &mut rows, |_, _| Ok(distribution()));
        let mut cached: serde_json::Value = serde_json::from_slice(
            &std::fs::read(chips_cache_path(root.path(), date, "000001.SZ")).unwrap(),
        )
        .unwrap();
        cached["trade_date"] = serde_json::json!("2026-01-06");
        std::fs::write(
            chips_cache_path(root.path(), date, "000001.SZ"),
            cached.to_string(),
        )
        .unwrap();
        let mut calls = 0;
        let report = enrich_chips_with_fetcher(root.path(), date, &mut rows, |_, _| {
            calls += 1;
            Ok(distribution())
        });
        assert_eq!(calls, 1);
        assert_eq!(report.cache_hits, 0);
    }

    #[test]
    fn chips_decode_numeric_strings_and_reject_wrong_dates_or_invalid_bins() {
        let date = NaiveDate::from_ymd_opt(2026, 1, 5).unwrap();
        let mut raw = BTreeMap::from([
            ("ts_code".to_string(), json!("000001.SZ")),
            ("trade_date".to_string(), json!("20260105")),
            ("price".to_string(), json!("10.0")),
            ("percent".to_string(), json!(100.0)),
        ]);
        assert_eq!(
            decode_chips_rows(&[raw.clone()], "000001.SZ", date).unwrap(),
            vec![CyqChip {
                price: 10.0,
                percent: 100.0
            }]
        );
        assert!(decode_chips_rows(&[raw.clone()], "000002.SZ", date).is_err());
        assert!(decode_chips_rows(&[raw.clone()], "000001.SZ", date.succ_opt().unwrap()).is_err());
        raw.insert("percent".to_string(), Value::Null);
        assert!(decode_chips_rows(&[raw], "000001.SZ", date).is_err());
    }

    #[test]
    fn chips_fetcher_scopes_requests_and_collects_all_pages() {
        use std::{
            io::{Read, Write},
            net::TcpListener,
        };
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let endpoint = format!("http://{}", listener.local_addr().unwrap());
        let server = std::thread::spawn(move || {
            for page in 0..2 {
                let (mut stream, _) = listener.accept().unwrap();
                stream
                    .set_read_timeout(Some(std::time::Duration::from_secs(5)))
                    .unwrap();
                let mut bytes = Vec::new();
                let request: Value = loop {
                    let mut buffer = [0; 4096];
                    let size = stream.read(&mut buffer).unwrap();
                    assert!(size > 0);
                    bytes.extend_from_slice(&buffer[..size]);
                    if let Some(end) = bytes.windows(4).position(|chunk| chunk == b"\r\n\r\n") {
                        let headers = String::from_utf8_lossy(&bytes[..end]).to_lowercase();
                        let length: usize = headers
                            .lines()
                            .find_map(|line| line.strip_prefix("content-length:"))
                            .unwrap()
                            .trim()
                            .parse()
                            .unwrap();
                        if bytes.len() >= end + 4 + length {
                            break serde_json::from_slice(&bytes[end + 4..end + 4 + length])
                                .unwrap();
                        }
                    }
                };
                assert_eq!(request["api_name"], "cyq_chips");
                assert_eq!(request["params"]["ts_code"], "000001.SZ");
                assert_eq!(request["params"]["trade_date"], "20260105");
                assert_eq!(request["params"]["offset"], page * 3);
                assert_eq!(request["params"]["limit"], 3);
                let chips = distribution();
                let items: Vec<_> = chips
                    .iter()
                    .skip(page * 3)
                    .take(3)
                    .map(|chip| json!(["000001.SZ", "20260105", chip.price, chip.percent]))
                    .collect();
                let body = json!({"code": 0, "data": {"fields": CYQ_CHIPS_FIELDS, "items": items, "has_more": page == 0}}).to_string();
                write!(stream, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", body.len(), body).unwrap();
            }
        });
        let mut config = TushareHttpConfig::new("fixture");
        config.endpoint = endpoint;
        config.page_size = 3;
        config.max_retries = 0;
        let fetcher = ChipsFetcher {
            client: TushareHttpClient::new(config).unwrap(),
            runtime: tokio::runtime::Builder::new_current_thread()
                .enable_all()
                .build()
                .unwrap(),
        };
        let chips = fetcher
            .fetch("000001.SZ", NaiveDate::from_ymd_opt(2026, 1, 5).unwrap())
            .unwrap();
        assert_eq!(chips, distribution());
        server.join().unwrap();
    }

    fn factor_row(code: &str) -> super::super::types::FactorRow {
        super::super::types::FactorRow {
            code: code.to_string(),
            method: crate::model::Method::B2,
            factors: BTreeMap::from([("close".to_string(), FactorValue::Number(10.0))]),
            diagnostics: BTreeMap::new(),
        }
    }
}
