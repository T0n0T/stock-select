use std::borrow::Cow;
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};

use chrono::NaiveDate;
use serde::Serialize;
use serde::ser::{SerializeMap, SerializeSeq};
use serde_json::{Value, json};

use crate::factors::abnormal_volume::push_abnormal_volume_event_factors;
use crate::factors::chip_age::push_chip_age_summary_factors;
use crate::factors::ma::push_ma_support_factors;
use crate::factors::macd::{macd_lines, push_macd_numeric_factors};
use crate::factors::price_position::{
    push_latest_bar_shape_factors, push_price_position_factors, push_range_compression,
};
use crate::factors::semantic::{
    push_b2_semantic_factors, push_b3_semantic_factors, push_lsh_semantic_factors,
};
use crate::factors::series::{FactorList, mean_tail, push_number, rolling_mean_series};
use crate::factors::types::{FactorInputRow, FactorRow, FactorValue};
use crate::factors::volume::{push_latest_volume_shrink_factor, push_volume_turnover_factors};
use crate::factors::zx::{push_zx_pullback_factors, zx_lines};
use crate::model::{Candidate, Method, PreparedRow};

pub const FACTOR_ARTIFACT_VERSION: u32 = 2;
pub const FACTOR_LIBRARY_VERSION: &str = "rust-factor-library-v3";
pub(crate) const RAW_MARKET_AMOUNT_FACTOR: &str = "_raw_market_amount";

const HISTORY_DB_FACTOR_KEYS: &[&str] = &["chip_vwap", "chip_turnover", RAW_MARKET_AMOUNT_FACTOR];

const B2_FACTOR_BUNDLES: &[FactorBundle] = &[
    FactorBundle::RawCommon,
    FactorBundle::ChipAge,
    FactorBundle::B2Semantic,
];
const B3_FACTOR_BUNDLES: &[FactorBundle] = &[
    FactorBundle::RawCommon,
    FactorBundle::ChipAge,
    FactorBundle::B3Semantic,
];
const LSH_FACTOR_BUNDLES: &[FactorBundle] = &[
    FactorBundle::RawCommon,
    FactorBundle::ChipAge,
    FactorBundle::LshSemantic,
];
const RAW_FACTOR_BUNDLES: &[FactorBundle] = &[FactorBundle::RawCommon];

const REVIEW_ONLY_FACTOR_KEYS: &[&str] = &[
    "trend_structure",
    "price_position",
    "volume_behavior",
    "previous_abnormal_move",
    "weekly_daily_combo_score",
    "total_score",
    "verdict",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FactorBundle {
    RawCommon,
    ChipAge,
    B2Semantic,
    B3Semantic,
    LshSemantic,
}

impl FactorBundle {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::RawCommon => "raw_common",
            Self::ChipAge => "chip_age",
            Self::B2Semantic => "b2_semantic",
            Self::B3Semantic => "b3_semantic",
            Self::LshSemantic => "lsh_semantic",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FactorProfile {
    pub method: Method,
    pub name: &'static str,
    pub bundles: &'static [FactorBundle],
}

impl FactorProfile {
    pub fn bundle_names(self) -> Vec<&'static str> {
        self.bundles.iter().map(|bundle| bundle.as_str()).collect()
    }
}

pub fn factor_profile_for_method(method: Method) -> FactorProfile {
    match method {
        Method::B2 => FactorProfile {
            method,
            name: "b2",
            bundles: B2_FACTOR_BUNDLES,
        },
        Method::B3 => FactorProfile {
            method,
            name: "b3",
            bundles: B3_FACTOR_BUNDLES,
        },
        Method::Lsh => FactorProfile {
            method,
            name: "lsh",
            bundles: LSH_FACTOR_BUNDLES,
        },
        _ => FactorProfile {
            method,
            name: method.as_str(),
            bundles: RAW_FACTOR_BUNDLES,
        },
    }
}

pub fn history_raw_factors(history: &[FactorInputRow]) -> FactorList {
    history_factor_fields(history, None, None)
}

pub fn history_factor_fields(
    history: &[FactorInputRow],
    signal: Option<&str>,
    environment_state: Option<&str>,
) -> FactorList {
    history_factor_fields_for_method(Method::B2, history, signal, environment_state)
}

pub fn history_factor_fields_for_method(
    method: Method,
    history: &[FactorInputRow],
    signal: Option<&str>,
    environment_state: Option<&str>,
) -> FactorList {
    history_factor_fields_for_profile(
        factor_profile_for_method(method),
        history,
        signal,
        environment_state,
    )
}

fn history_factor_fields_for_profile(
    profile: FactorProfile,
    history: &[FactorInputRow],
    signal: Option<&str>,
    environment_state: Option<&str>,
) -> FactorList {
    if history.is_empty() {
        return Vec::new();
    }

    let close = history.iter().map(|row| row.close).collect::<Vec<_>>();
    let high = history.iter().map(|row| row.high).collect::<Vec<_>>();
    let low = history.iter().map(|row| row.low).collect::<Vec<_>>();
    let open = history.iter().map(|row| row.open).collect::<Vec<_>>();
    let volume = history.iter().map(|row| row.volume).collect::<Vec<_>>();
    let turnover_basis = history
        .iter()
        .map(|row| {
            row.turnover_rate
                .or_else(|| row.turnover_n.is_finite().then_some(row.turnover_n))
        })
        .collect::<Vec<_>>();
    let derived_ma25 = rolling_mean_series(&close, 25, 25);
    let derived_ma60 = rolling_mean_series(&close, 60, 60);
    let (derived_zxdq, derived_zxdkx) = zx_lines(&close);
    let ma25 = history
        .iter()
        .enumerate()
        .map(|(idx, row)| row.ma25.or(derived_ma25[idx]))
        .collect::<Vec<_>>();
    let ma60 = history
        .iter()
        .enumerate()
        .map(|(idx, row)| row.ma60.or(derived_ma60[idx]))
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

    let latest = history.last();
    let previous = history.iter().rev().nth(1);
    let latest_open = latest.map(|row| row.open);
    let latest_close = latest.map(|row| row.close);
    let latest_low = latest.map(|row| row.low);
    let latest_high = latest.map(|row| row.high);
    let latest_ma25 = ma25.last().copied().flatten();
    let latest_ma60 = ma60.last().copied().flatten();
    let latest_zxdkx = zxdkx.last().copied().flatten();
    let previous_zxdkx = zxdkx.iter().rev().nth(1).copied().flatten();
    let latest_volume = latest.map(|row| row.volume);
    let previous_volume = previous.map(|row| row.volume);
    let latest_turnover_rate = latest.and_then(|row| {
        row.turnover_rate
            .or_else(|| row.turnover_n.is_finite().then_some(row.turnover_n))
    });

    let ma25_values = ma25.iter().copied().flatten().collect::<Vec<_>>();
    let zxdkx_values = zxdkx.iter().copied().flatten().collect::<Vec<_>>();
    let zxdq_values = zxdq.iter().copied().flatten().collect::<Vec<_>>();
    let avg_close5 = mean_tail(&close, 5);
    let avg_volume5 = mean_tail(&volume, 5);
    let avg_volume20 = mean_tail(&volume, 20);
    let avg_turnover5 = if turnover_basis.len() >= 5 {
        turnover_basis[turnover_basis.len() - 5..]
            .iter()
            .copied()
            .collect::<Option<Vec<_>>>()
            .and_then(|values| mean_tail(&values, 5))
    } else {
        None
    };

    let mut factors = Vec::new();
    for bundle in profile.bundles {
        match bundle {
            FactorBundle::RawCommon => {
                push_ma_support_factors(
                    &mut factors,
                    latest_close,
                    latest_low,
                    latest_ma25,
                    latest_zxdkx,
                    &ma25_values,
                );
                push_zx_pullback_factors(
                    &mut factors,
                    latest_close,
                    latest_ma25,
                    latest_zxdkx,
                    previous_zxdkx,
                    &zxdkx_values,
                    &zxdq_values,
                );
                push_price_position_factors(
                    &mut factors,
                    &close,
                    &high,
                    &low,
                    latest_close,
                    latest_low,
                    latest_high,
                    previous.map(|row| row.close),
                    avg_close5,
                );
                push_volume_turnover_factors(
                    &mut factors,
                    latest_volume,
                    previous_volume,
                    avg_volume5,
                    avg_volume20,
                    latest_turnover_rate,
                    avg_turnover5,
                );
                push_macd_numeric_factors(
                    &mut factors,
                    &dif,
                    &dea,
                    &macd_hist,
                    &derived_dif,
                    &derived_dea,
                    &derived_macd_hist,
                    latest_close,
                );
                push_range_compression(&mut factors, &high, &low, latest_close, 20);
                push_range_compression(&mut factors, &high, &low, latest_close, 40);
                push_abnormal_volume_event_factors(
                    &mut factors,
                    &open,
                    &close,
                    &volume,
                    latest_close,
                );
            }
            FactorBundle::ChipAge => {
                push_chip_age_summary_factors(&mut factors, history);
            }
            FactorBundle::B2Semantic => {
                push_b2_semantic_factors(
                    &mut factors,
                    history,
                    signal,
                    environment_state,
                    latest_ma60,
                );
            }
            FactorBundle::B3Semantic => {
                push_latest_volume_shrink_factor(&mut factors, latest_volume, previous_volume);
                push_latest_bar_shape_factors(
                    &mut factors,
                    latest_open,
                    latest_high,
                    latest_low,
                    latest_close,
                    previous.map(|row| row.close),
                );
                push_b3_semantic_factors(&mut factors, history, signal, environment_state);
            }
            FactorBundle::LshSemantic => {
                push_lsh_semantic_factors(&mut factors, history);
            }
        }
    }
    push_latest_db_factor_extras(&mut factors, latest);
    push_stock_relative_to_sw_l2_factors(&mut factors, &close, latest);
    factors
}

fn push_stock_relative_to_sw_l2_factors(
    factors: &mut FactorList,
    close: &[f64],
    latest: Option<&FactorInputRow>,
) {
    let latest = latest.map(|row| &row.db_factors);
    push_number(
        factors,
        "stock_vs_sw_l2_ret5_pct",
        stock_return_minus_factor(
            close,
            5,
            latest.and_then(|factors| factors.get("sw_l2_ret5_pct").copied()),
        ),
    );
    push_number(
        factors,
        "stock_vs_sw_l2_ret20_pct",
        stock_return_minus_factor(
            close,
            20,
            latest.and_then(|factors| factors.get("sw_l2_ret20_pct").copied()),
        ),
    );
}

fn stock_return_minus_factor(
    close: &[f64],
    periods: usize,
    compare_ret_pct: Option<f64>,
) -> Option<f64> {
    let compare_ret_pct = compare_ret_pct.filter(|value| value.is_finite())?;
    if close.len() <= periods {
        return None;
    }
    let latest = *close.last()?;
    let base = close[close.len() - 1 - periods];
    if !latest.is_finite() || !base.is_finite() || base == 0.0 {
        return None;
    }
    Some((latest - base) / base * 100.0 - compare_ret_pct)
}

fn push_latest_db_factor_extras(factors: &mut FactorList, latest: Option<&FactorInputRow>) {
    let Some(latest) = latest else {
        return;
    };
    for (key, value) in &latest.db_factors {
        if key == RAW_MARKET_AMOUNT_FACTOR {
            continue;
        }
        push_number(factors, key, value.is_finite().then_some(*value));
    }
}

pub fn record_factor_profile_diagnostics(row: &mut FactorRow, profile: FactorProfile) {
    row.diagnostics.insert(
        "factor_profile".to_string(),
        Value::String(profile.name.to_string()),
    );
    row.diagnostics
        .insert("factor_bundles".to_string(), json!(profile.bundle_names()));
}

pub fn remove_review_only_factors(row: &mut FactorRow) {
    for key in REVIEW_ONLY_FACTOR_KEYS {
        row.factors.remove(*key);
    }
}

pub fn factor_artifact_dir(runtime_root: &Path, method: Method, artifact_key: &str) -> PathBuf {
    runtime_root
        .join("factors")
        .join(format!("{}.{}", artifact_key, method.as_str()))
}

pub fn build_candidate_factor_rows(
    candidates: &[Candidate],
    prepared_rows: &[PreparedRow],
    method: Method,
    environment_state: Option<&str>,
) -> Vec<FactorRow> {
    let refs = prepared_rows.iter().collect::<Vec<_>>();
    build_candidate_factor_rows_from_refs(candidates, &refs, method, environment_state)
}

pub fn build_candidate_factor_rows_from_refs(
    candidates: &[Candidate],
    prepared_rows: &[&PreparedRow],
    method: Method,
    environment_state: Option<&str>,
) -> Vec<FactorRow> {
    let candidate_pick_dates = candidates
        .iter()
        .map(|candidate| (candidate.code.as_str(), candidate.pick_date))
        .collect::<BTreeMap<_, _>>();
    let rows_by_code = candidate_history_rows_by_code(prepared_rows, &candidate_pick_dates);
    let market_state_by_date = market_state_factors_by_date(prepared_rows);

    candidates
        .iter()
        .map(|candidate| {
            let profile = factor_profile_for_method(method);
            let mut row = FactorRow::new(candidate.code.clone(), method);
            row.factors
                .insert("close".to_string(), FactorValue::Number(candidate.close));
            row.factors.insert(
                "turnover_n".to_string(),
                FactorValue::Number(candidate.turnover_n),
            );
            if let Some(signal) = &candidate.signal {
                row.factors
                    .insert("signal".to_string(), FactorValue::Category(signal.clone()));
            }
            if let Some(state) = environment_state {
                row.factors
                    .insert("env".to_string(), FactorValue::Category(state.to_string()));
            }
            let history = rows_by_code
                .get(candidate.code.as_str())
                .cloned()
                .unwrap_or_default();
            let history_factors = history_factor_fields_for_profile(
                profile,
                &history,
                candidate.signal.as_deref(),
                environment_state,
            );
            let history_factor_count = history_factors.len();
            for (key, value) in history_factors {
                row.factors.insert(key, value);
            }
            remove_review_only_factors(&mut row);
            if let Some(market_state_factors) = market_state_by_date.get(&candidate.pick_date) {
                for (key, value) in market_state_factors {
                    row.factors.insert(key.clone(), value.clone());
                }
            }
            record_factor_profile_diagnostics(&mut row, profile);
            row.diagnostics.insert(
                "factor_source".to_string(),
                Value::String("rust_factor_library".to_string()),
            );
            row.diagnostics.insert(
                "history_source".to_string(),
                Value::String("prepared_cache".to_string()),
            );
            row.diagnostics.insert(
                "history_factor_count".to_string(),
                Value::Number(serde_json::Number::from(history_factor_count)),
            );
            row.diagnostics.insert(
                "factor_count".to_string(),
                Value::Number(serde_json::Number::from(row.factors.len())),
            );
            row
        })
        .collect()
}

fn candidate_history_rows_by_code<'a>(
    prepared_rows: &[&'a PreparedRow],
    candidate_pick_dates: &BTreeMap<&'a str, NaiveDate>,
) -> BTreeMap<&'a str, Vec<FactorInputRow>> {
    let mut prepared_by_code: BTreeMap<&str, Vec<&PreparedRow>> = BTreeMap::new();
    for row in prepared_rows.iter().copied() {
        let Some(pick_date) = candidate_pick_dates.get(row.ts_code.as_str()).copied() else {
            continue;
        };
        if row.trade_date > pick_date {
            continue;
        }
        prepared_by_code
            .entry(row.ts_code.as_str())
            .or_default()
            .push(row);
    }

    prepared_by_code
        .into_iter()
        .map(|(code, rows)| {
            let pick_date = candidate_pick_dates[code];
            let history = rows
                .iter()
                .map(|row| FactorInputRow {
                    trade_date: Some(row.trade_date),
                    open: row.open,
                    high: row.high,
                    low: row.low,
                    close: row.close,
                    volume: row.volume,
                    turnover_n: row.turnover_n,
                    turnover_rate: row.turnover_rate,
                    d: Some(row.d),
                    j: Some(row.j),
                    ma25: row.ma25,
                    ma60: row.ma60,
                    zxdkx: row.zxdkx,
                    zxdq: row.zxdq,
                    dif: Some(row.dif),
                    dea: Some(row.dea),
                    macd_hist: Some(row.macd_hist),
                    db_factors: if row.trade_date == pick_date {
                        row.db_factors.clone()
                    } else {
                        required_history_db_factors(row)
                    },
                })
                .collect();
            (code, history)
        })
        .collect()
}

fn required_history_db_factors(row: &PreparedRow) -> BTreeMap<String, f64> {
    HISTORY_DB_FACTOR_KEYS
        .iter()
        .filter_map(|key| {
            row.db_factors
                .get(*key)
                .copied()
                .map(|value| ((*key).to_string(), value))
        })
        .collect()
}

fn market_state_factors_by_date(rows: &[&PreparedRow]) -> BTreeMap<NaiveDate, FactorList> {
    market_state_factors_by_date_with_accumulators(rows)
}

#[derive(Default)]
struct MarketStateAccumulator {
    pct_changes: Vec<f64>,
    amount_total: f64,
    net_mf_total: f64,
    net_mf_count: usize,
    approx_limit_up_count: usize,
    approx_limit_down_count: usize,
}

fn market_state_factors_by_date_with_accumulators(
    rows: &[&PreparedRow],
) -> BTreeMap<NaiveDate, FactorList> {
    let mut accumulators: BTreeMap<NaiveDate, MarketStateAccumulator> = BTreeMap::new();
    for row in rows.iter().copied() {
        let entry = accumulators.entry(row.trade_date).or_default();
        if let Some(pct_change) = row.chg_d.filter(|value| value.is_finite()) {
            entry.pct_changes.push(pct_change);
        }
        if let Some(amount) = market_amount(row).filter(|value| value.is_finite()) {
            entry.amount_total += amount;
        }
        if let Some(net_mf) = row
            .db_factors
            .get("net_mf_amount_to_amount_pct")
            .copied()
            .filter(|value| value.is_finite())
        {
            entry.net_mf_total += net_mf;
            entry.net_mf_count += 1;
        }
        if near_limit_factor(row, "dist_to_up_limit_pct") {
            entry.approx_limit_up_count += 1;
        }
        if near_limit_factor(row, "dist_to_down_limit_pct") {
            entry.approx_limit_down_count += 1;
        }
    }

    let amount_ma5_by_date = market_amount_ma5_ratio_by_date(&accumulators);
    accumulators
        .iter()
        .map(|(trade_date, accumulator)| {
            let mut factors = Vec::new();
            let count = accumulator.pct_changes.len() as f64;
            push_number(
                &mut factors,
                "market_up_ratio",
                ratio_count(
                    accumulator
                        .pct_changes
                        .iter()
                        .filter(|value| **value > 0.0)
                        .count(),
                    count,
                ),
            );
            push_number(
                &mut factors,
                "market_ge5_ratio",
                ratio_count(
                    accumulator
                        .pct_changes
                        .iter()
                        .filter(|value| **value >= 5.0)
                        .count(),
                    count,
                ),
            );
            push_number(
                &mut factors,
                "market_le_minus5_ratio",
                ratio_count(
                    accumulator
                        .pct_changes
                        .iter()
                        .filter(|value| **value <= -5.0)
                        .count(),
                    count,
                ),
            );
            push_number(
                &mut factors,
                "market_median_pct_chg",
                median(accumulator.pct_changes.clone()),
            );
            push_number(
                &mut factors,
                "market_amount_ma5_ratio",
                amount_ma5_by_date.get(trade_date).copied().flatten(),
            );
            push_number(
                &mut factors,
                "market_net_mf_to_amount_pct",
                mean_totals(accumulator.net_mf_total, accumulator.net_mf_count),
            );
            push_number(
                &mut factors,
                "market_approx_limit_up_count",
                Some(accumulator.approx_limit_up_count as f64),
            );
            push_number(
                &mut factors,
                "market_approx_limit_down_count",
                Some(accumulator.approx_limit_down_count as f64),
            );
            (*trade_date, factors)
        })
        .collect()
}

fn market_amount_ma5_ratio_by_date(
    accumulators: &BTreeMap<NaiveDate, MarketStateAccumulator>,
) -> BTreeMap<NaiveDate, Option<f64>> {
    let daily_amounts = accumulators
        .iter()
        .map(|(trade_date, accumulator)| (*trade_date, accumulator.amount_total))
        .collect::<Vec<_>>();
    let mut ratios = BTreeMap::new();
    for idx in 0..daily_amounts.len() {
        let (trade_date, amount) = daily_amounts[idx];
        let start = idx.saturating_sub(4);
        let window = &daily_amounts[start..=idx];
        let base = window.iter().map(|(_date, amount)| *amount).sum::<f64>() / window.len() as f64;
        ratios.insert(
            trade_date,
            (base != 0.0 && amount.is_finite() && base.is_finite()).then_some(amount / base),
        );
    }
    ratios
}

fn market_amount(row: &PreparedRow) -> Option<f64> {
    row.db_factors
        .get(RAW_MARKET_AMOUNT_FACTOR)
        .copied()
        .filter(|value| value.is_finite())
        .or_else(|| {
            let amount = ((row.open + row.close) / 2.0) * row.volume;
            amount.is_finite().then_some(amount)
        })
}

fn ratio_count(numerator: usize, denominator: f64) -> Option<f64> {
    (denominator > 0.0).then_some(numerator as f64 / denominator)
}

fn median(mut values: Vec<f64>) -> Option<f64> {
    if values.is_empty() {
        return None;
    }
    values.sort_by(f64::total_cmp);
    let mid = values.len() / 2;
    if values.len() % 2 == 0 {
        Some((values[mid - 1] + values[mid]) / 2.0)
    } else {
        Some(values[mid])
    }
}

fn mean_totals(total: f64, count: usize) -> Option<f64> {
    (count > 0).then_some(total / count as f64)
}

fn near_limit_factor(row: &PreparedRow, key: &str) -> bool {
    row.db_factors
        .get(key)
        .is_some_and(|value| value.is_finite() && *value <= 0.2)
}

pub fn write_factor_artifact(
    runtime_root: &Path,
    method: Method,
    artifact_key: &str,
    rows: &[FactorRow],
    candidate_artifact: Option<&Path>,
) -> anyhow::Result<PathBuf> {
    let dir = factor_artifact_dir(runtime_root, method, artifact_key);
    std::fs::create_dir_all(&dir)?;
    let factors_path = dir.join("factors.json");
    let manifest_path = dir.join("manifest.json");
    write_pretty_json_file(
        &factors_path,
        &FactorArtifactFile {
            artifact_version: FACTOR_ARTIFACT_VERSION,
            method: method.as_str(),
            artifact_key,
            factor_library_version: FACTOR_LIBRARY_VERSION,
            rows,
        },
    )?;
    write_pretty_json_file(
        &manifest_path,
        &FactorManifestFile {
            artifact_version: FACTOR_ARTIFACT_VERSION,
            method: method.as_str(),
            artifact_key,
            factor_library_version: FACTOR_LIBRARY_VERSION,
            factor_source: "rust_factor_library",
            candidate_artifact: candidate_artifact.map(|path| path.to_string_lossy()),
            row_count: rows.len(),
        },
    )?;
    Ok(dir)
}

fn write_pretty_json_file<T: Serialize>(path: &Path, value: &T) -> anyhow::Result<()> {
    let file = File::create(path)?;
    let writer = BufWriter::new(file);
    let formatter = serde_json::ser::PrettyFormatter::with_indent(b"  ");
    let mut serializer = serde_json::Serializer::with_formatter(writer, formatter);
    value.serialize(&mut serializer)?;
    serializer.into_inner().flush()?;
    Ok(())
}

struct FactorArtifactFile<'a> {
    artifact_version: u32,
    method: &'a str,
    artifact_key: &'a str,
    factor_library_version: &'static str,
    rows: &'a [FactorRow],
}

struct FactorManifestFile<'a> {
    artifact_version: u32,
    method: &'a str,
    artifact_key: &'a str,
    factor_library_version: &'static str,
    factor_source: &'static str,
    candidate_artifact: Option<Cow<'a, str>>,
    row_count: usize,
}

struct SortedFactorRows<'a>(&'a [FactorRow]);

struct SortedFactorRow<'a>(&'a FactorRow);

impl Serialize for FactorArtifactFile<'_> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        let mut map = serializer.serialize_map(Some(5))?;
        map.serialize_entry("artifact_key", self.artifact_key)?;
        map.serialize_entry("artifact_version", &self.artifact_version)?;
        map.serialize_entry("factor_library_version", self.factor_library_version)?;
        map.serialize_entry("method", self.method)?;
        map.serialize_entry("rows", &SortedFactorRows(self.rows))?;
        map.end()
    }
}

impl Serialize for FactorManifestFile<'_> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        let mut map = serializer.serialize_map(Some(7))?;
        map.serialize_entry("artifact_key", self.artifact_key)?;
        map.serialize_entry("artifact_version", &self.artifact_version)?;
        map.serialize_entry("candidate_artifact", &self.candidate_artifact)?;
        map.serialize_entry("factor_library_version", self.factor_library_version)?;
        map.serialize_entry("factor_source", self.factor_source)?;
        map.serialize_entry("method", self.method)?;
        map.serialize_entry("row_count", &self.row_count)?;
        map.end()
    }
}

impl Serialize for SortedFactorRows<'_> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        let mut seq = serializer.serialize_seq(Some(self.0.len()))?;
        for row in self.0 {
            seq.serialize_element(&SortedFactorRow(row))?;
        }
        seq.end()
    }
}

impl Serialize for SortedFactorRow<'_> {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        let row = self.0;
        let mut map = serializer.serialize_map(Some(4))?;
        map.serialize_entry("code", &row.code)?;
        map.serialize_entry("diagnostics", &row.diagnostics)?;
        map.serialize_entry("factors", &row.factors)?;
        map.serialize_entry("method", &row.method)?;
        map.end()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{Duration, NaiveDate};

    fn test_prepared_row(
        ts_code: &str,
        trade_date: NaiveDate,
        close: f64,
        volume: f64,
        chg_d: Option<f64>,
    ) -> PreparedRow {
        PreparedRow {
            ts_code: ts_code.to_string(),
            trade_date,
            open: close - 0.5,
            high: close + 1.0,
            low: close - 1.0,
            close,
            volume,
            turnover_n: 12.0,
            turnover_rate: Some(0.2),
            k: 50.0,
            d: 40.0,
            j: 60.0,
            zxdq: Some(close - 0.2),
            zxdkx: Some(close - 0.4),
            dif: 0.3,
            dea: 0.2,
            macd_hist: 0.1,
            ma25: Some(close - 0.5),
            ma60: Some(close - 1.0),
            ma144: Some(close - 1.5),
            chg_d,
            weekly_ma_bull: true,
            max_vol_not_bearish: true,
            v_shrink: true,
            safe_mode: true,
            lt_filter: true,
            yellow_b1: false,
            db_factors: BTreeMap::new(),
        }
    }

    #[test]
    fn write_factor_artifact_preserves_pretty_json_payloads() {
        let temp = tempfile::tempdir().unwrap();
        let candidate_artifact = temp.path().join("select/2026-06-23.b2/candidates.json");
        let mut row = FactorRow::new("000001.SZ", Method::B2);
        row.factors
            .insert("close".to_string(), FactorValue::Number(12.34));
        row.factors.insert(
            "signal".to_string(),
            FactorValue::Category("B2".to_string()),
        );
        row.diagnostics.insert(
            "factor_source".to_string(),
            Value::String("rust_factor_library".to_string()),
        );
        let rows = vec![row];

        let dir = write_factor_artifact(
            temp.path(),
            Method::B2,
            "2026-06-23",
            &rows,
            Some(candidate_artifact.as_path()),
        )
        .unwrap();

        let factors = std::fs::read_to_string(dir.join("factors.json")).unwrap();
        let manifest = std::fs::read_to_string(dir.join("manifest.json")).unwrap();

        let expected_factors = serde_json::to_string_pretty(&json!({
            "artifact_version": FACTOR_ARTIFACT_VERSION,
            "method": "b2",
            "artifact_key": "2026-06-23",
            "factor_library_version": FACTOR_LIBRARY_VERSION,
            "rows": rows,
        }))
        .unwrap();
        let expected_manifest = serde_json::to_string_pretty(&json!({
            "artifact_version": FACTOR_ARTIFACT_VERSION,
            "method": "b2",
            "artifact_key": "2026-06-23",
            "factor_library_version": FACTOR_LIBRARY_VERSION,
            "factor_source": "rust_factor_library",
            "candidate_artifact": candidate_artifact.to_string_lossy(),
            "row_count": 1,
        }))
        .unwrap();

        assert_eq!(factors, expected_factors);
        assert_eq!(manifest, expected_manifest);
    }

    #[test]
    fn candidate_history_keeps_only_required_historical_db_factors_and_latest_exports_all() {
        let pick_date = NaiveDate::from_ymd_opt(2026, 6, 23).unwrap();
        let mut prepared = (0..3)
            .map(|offset| {
                let trade_date = pick_date - Duration::days(2 - offset);
                let mut db_factors = BTreeMap::new();
                db_factors.insert("chip_vwap".to_string(), 10.0 + offset as f64);
                db_factors.insert("chip_turnover".to_string(), 0.2);
                db_factors.insert(RAW_MARKET_AMOUNT_FACTOR.to_string(), 1_000_000.0);
                db_factors.insert(format!("history_big_{offset}"), 9_999.0 + offset as f64);
                if offset == 2 {
                    db_factors.insert("latest_export_factor".to_string(), 42.0);
                }
                PreparedRow {
                    ts_code: "000001.SZ".to_string(),
                    trade_date,
                    open: 10.0 + offset as f64,
                    high: 10.5 + offset as f64,
                    low: 9.5 + offset as f64,
                    close: 10.2 + offset as f64,
                    volume: 1_000.0 + offset as f64,
                    turnover_n: 12.0,
                    turnover_rate: Some(0.2),
                    k: 50.0,
                    d: 40.0,
                    j: 60.0,
                    zxdq: Some(9.8 + offset as f64),
                    zxdkx: Some(9.6 + offset as f64),
                    dif: 0.3,
                    dea: 0.2,
                    macd_hist: 0.1,
                    ma25: Some(9.7 + offset as f64),
                    ma60: Some(9.0 + offset as f64),
                    ma144: Some(8.5 + offset as f64),
                    chg_d: Some(1.0),
                    weekly_ma_bull: true,
                    max_vol_not_bearish: true,
                    v_shrink: true,
                    safe_mode: true,
                    lt_filter: true,
                    yellow_b1: false,
                    db_factors,
                }
            })
            .collect::<Vec<_>>();
        let mut future_row = prepared[2].clone();
        future_row.trade_date = pick_date + Duration::days(1);
        future_row.close += 1.0;
        future_row
            .db_factors
            .insert("future_export_factor".to_string(), 77.0);
        prepared.push(future_row);
        let prepared_refs = prepared.iter().collect::<Vec<_>>();
        let candidate_pick_dates = [("000001.SZ", pick_date)].into_iter().collect();

        let history = candidate_history_rows_by_code(&prepared_refs, &candidate_pick_dates)
            .remove("000001.SZ")
            .unwrap();

        assert_eq!(history.len(), 3);
        assert_eq!(
            history[0].db_factors.keys().cloned().collect::<Vec<_>>(),
            vec![
                RAW_MARKET_AMOUNT_FACTOR.to_string(),
                "chip_turnover".to_string(),
                "chip_vwap".to_string(),
            ]
        );
        assert_eq!(
            history[1].db_factors.keys().cloned().collect::<Vec<_>>(),
            vec![
                RAW_MARKET_AMOUNT_FACTOR.to_string(),
                "chip_turnover".to_string(),
                "chip_vwap".to_string(),
            ]
        );
        assert!(history[2].db_factors.contains_key("history_big_2"));
        assert!(history[2].db_factors.contains_key("latest_export_factor"));
        assert!(
            !history
                .iter()
                .any(|row| row.db_factors.contains_key("future_export_factor"))
        );

        let candidate = Candidate {
            code: "000001.SZ".to_string(),
            pick_date,
            close: prepared[2].close,
            turnover_n: prepared[2].turnover_n,
            signal: Some("B2".to_string()),
            yellow_b1: None,
        };
        let rows =
            build_candidate_factor_rows_from_refs(&[candidate], &prepared_refs, Method::B2, None);

        assert_eq!(
            rows[0].factors.get("latest_export_factor"),
            Some(&FactorValue::Number(42.0))
        );
        assert!(!rows[0].factors.contains_key("future_export_factor"));
        assert!(rows[0].factors.contains_key("chip_entropy"));
    }

    #[test]
    fn market_state_factors_match_expected_cross_section_with_amount_ma5_series() {
        let day1 = NaiveDate::from_ymd_opt(2026, 6, 1).unwrap();
        let day2 = day1 + Duration::days(1);
        let day3 = day1 + Duration::days(2);
        let day4 = day1 + Duration::days(3);
        let day5 = day1 + Duration::days(4);
        let day6 = day1 + Duration::days(5);

        let mut rows = Vec::new();
        for (idx, (trade_date, changes, amounts, net_mf, up_count, down_count)) in [
            (
                day1,
                [1.0, -1.0, 0.0],
                [100.0, 200.0, 300.0],
                [1.0, 2.0, 3.0],
                0,
                0,
            ),
            (
                day2,
                [2.0, 2.0, -2.0],
                [100.0, 100.0, 100.0],
                [2.0, 4.0, 6.0],
                0,
                0,
            ),
            (
                day3,
                [3.0, -3.0, 6.0],
                [300.0, 300.0, 300.0],
                [3.0, 6.0, 9.0],
                1,
                0,
            ),
            (
                day4,
                [4.0, -4.0, 8.0],
                [400.0, 400.0, 400.0],
                [4.0, 8.0, 12.0],
                0,
                1,
            ),
            (
                day5,
                [5.0, -6.0, 10.0],
                [500.0, 500.0, 500.0],
                [5.0, 10.0, 15.0],
                1,
                1,
            ),
            (
                day6,
                [10.0, 0.0, -5.0],
                [600.0, 300.0, 300.0],
                [6.0, 12.0, 18.0],
                1,
                1,
            ),
        ]
        .into_iter()
        .enumerate()
        {
            for row_idx in 0..3 {
                let code = format!("{idx:02}{row_idx:02}.SZ");
                let mut row = test_prepared_row(
                    &code,
                    trade_date,
                    10.0 + idx as f64 + row_idx as f64,
                    1_000.0 + row_idx as f64,
                    Some(changes[row_idx]),
                );
                row.db_factors
                    .insert(RAW_MARKET_AMOUNT_FACTOR.to_string(), amounts[row_idx]);
                row.db_factors
                    .insert("net_mf_amount_to_amount_pct".to_string(), net_mf[row_idx]);
                if row_idx < up_count {
                    row.db_factors
                        .insert("dist_to_up_limit_pct".to_string(), 0.1);
                }
                if row_idx < down_count {
                    row.db_factors
                        .insert("dist_to_down_limit_pct".to_string(), 0.1);
                }
                rows.push(row);
            }
        }

        let row_refs = rows.iter().collect::<Vec<_>>();
        let market_state = market_state_factors_by_date_with_accumulators(&row_refs);
        let day6_factors = market_state.get(&day6).unwrap();

        assert_eq!(
            day6_factors,
            &vec![
                ("market_up_ratio".to_string(), FactorValue::Number(0.3333)),
                ("market_ge5_ratio".to_string(), FactorValue::Number(0.3333)),
                (
                    "market_le_minus5_ratio".to_string(),
                    FactorValue::Number(0.3333)
                ),
                (
                    "market_median_pct_chg".to_string(),
                    FactorValue::Number(0.0)
                ),
                (
                    "market_amount_ma5_ratio".to_string(),
                    FactorValue::Number(1.1765)
                ),
                (
                    "market_net_mf_to_amount_pct".to_string(),
                    FactorValue::Number(12.0)
                ),
                (
                    "market_approx_limit_up_count".to_string(),
                    FactorValue::Number(1.0)
                ),
                (
                    "market_approx_limit_down_count".to_string(),
                    FactorValue::Number(1.0)
                ),
            ]
        );
    }
}
