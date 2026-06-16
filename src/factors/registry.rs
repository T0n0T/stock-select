use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use chrono::NaiveDate;
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

pub const FACTOR_ARTIFACT_VERSION: u32 = 1;
pub const FACTOR_LIBRARY_VERSION: &str = "rust-factor-library-v2";
pub(crate) const RAW_MARKET_AMOUNT_FACTOR: &str = "_raw_market_amount";

const B2_FACTOR_BUNDLES: &[FactorBundle] = &[
    FactorBundle::RawCommon,
    FactorBundle::B2ChipAge,
    FactorBundle::B2Semantic,
];
const B3_FACTOR_BUNDLES: &[FactorBundle] = &[FactorBundle::RawCommon, FactorBundle::B3Semantic];
const LSH_FACTOR_BUNDLES: &[FactorBundle] = &[FactorBundle::RawCommon, FactorBundle::LshSemantic];
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
    B2ChipAge,
    B2Semantic,
    B3Semantic,
    LshSemantic,
}

impl FactorBundle {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::RawCommon => "raw_common",
            Self::B2ChipAge => "b2_chip_age",
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
            FactorBundle::B2ChipAge => {
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
    factors
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
    let candidate_codes = candidates
        .iter()
        .map(|candidate| candidate.code.as_str())
        .collect::<std::collections::BTreeSet<_>>();
    let mut rows_by_code: BTreeMap<&str, Vec<FactorInputRow>> = BTreeMap::new();
    let market_state_by_date = market_state_factors_by_date(prepared_rows);
    for row in prepared_rows.iter().copied() {
        if !candidate_codes.contains(row.ts_code.as_str()) {
            continue;
        }
        rows_by_code
            .entry(row.ts_code.as_str())
            .or_default()
            .push(FactorInputRow {
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
                db_factors: row.db_factors.clone(),
            });
    }

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

fn market_state_factors_by_date(rows: &[&PreparedRow]) -> BTreeMap<NaiveDate, FactorList> {
    let mut rows_by_date: BTreeMap<NaiveDate, Vec<&PreparedRow>> = BTreeMap::new();
    for row in rows.iter().copied() {
        rows_by_date.entry(row.trade_date).or_default().push(row);
    }
    let amount_ma5_by_date = market_amount_ma5_ratio_by_date(&rows_by_date);
    rows_by_date
        .iter()
        .map(|(trade_date, rows)| {
            let mut factors = Vec::new();
            let pct_changes = rows
                .iter()
                .filter_map(|row| row.chg_d.filter(|value| value.is_finite()))
                .collect::<Vec<_>>();
            let count = pct_changes.len() as f64;
            push_number(
                &mut factors,
                "market_up_ratio",
                ratio_count(
                    pct_changes.iter().filter(|value| **value > 0.0).count(),
                    count,
                ),
            );
            push_number(
                &mut factors,
                "market_ge5_ratio",
                ratio_count(
                    pct_changes.iter().filter(|value| **value >= 5.0).count(),
                    count,
                ),
            );
            push_number(
                &mut factors,
                "market_le_minus5_ratio",
                ratio_count(
                    pct_changes.iter().filter(|value| **value <= -5.0).count(),
                    count,
                ),
            );
            push_number(&mut factors, "market_median_pct_chg", median(pct_changes));
            push_number(
                &mut factors,
                "market_amount_ma5_ratio",
                amount_ma5_by_date.get(trade_date).copied().flatten(),
            );
            push_number(
                &mut factors,
                "market_net_mf_to_amount_pct",
                mean(rows.iter().filter_map(|row| {
                    row.db_factors
                        .get("net_mf_amount_to_amount_pct")
                        .copied()
                        .filter(|value| value.is_finite())
                })),
            );
            push_number(
                &mut factors,
                "market_approx_limit_up_count",
                Some(
                    rows.iter()
                        .filter(|row| near_limit_factor(row, "dist_to_up_limit_pct"))
                        .count() as f64,
                ),
            );
            push_number(
                &mut factors,
                "market_approx_limit_down_count",
                Some(
                    rows.iter()
                        .filter(|row| near_limit_factor(row, "dist_to_down_limit_pct"))
                        .count() as f64,
                ),
            );
            (*trade_date, factors)
        })
        .collect()
}

fn market_amount_ma5_ratio_by_date(
    rows_by_date: &BTreeMap<NaiveDate, Vec<&PreparedRow>>,
) -> BTreeMap<NaiveDate, Option<f64>> {
    let daily_amounts = rows_by_date
        .iter()
        .map(|(trade_date, rows)| {
            (
                *trade_date,
                rows.iter()
                    .filter_map(|row| market_amount(row))
                    .filter(|value| value.is_finite())
                    .sum::<f64>(),
            )
        })
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

fn mean(values: impl Iterator<Item = f64>) -> Option<f64> {
    let mut count = 0.0;
    let mut total = 0.0;
    for value in values {
        total += value;
        count += 1.0;
    }
    (count > 0.0).then_some(total / count)
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
    std::fs::write(
        &factors_path,
        serde_json::to_vec_pretty(&json!({
            "artifact_version": FACTOR_ARTIFACT_VERSION,
            "method": method.as_str(),
            "artifact_key": artifact_key,
            "factor_library_version": FACTOR_LIBRARY_VERSION,
            "rows": rows,
        }))?,
    )?;
    std::fs::write(
        &manifest_path,
        serde_json::to_vec_pretty(&json!({
            "artifact_version": FACTOR_ARTIFACT_VERSION,
            "method": method.as_str(),
            "artifact_key": artifact_key,
            "factor_library_version": FACTOR_LIBRARY_VERSION,
            "factor_source": "rust_factor_library",
            "candidate_artifact": candidate_artifact.map(|path| path.to_string_lossy().to_string()),
            "row_count": rows.len(),
        }))?,
    )?;
    Ok(dir)
}
