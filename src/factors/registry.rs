use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use serde_json::{Value, json};

use crate::factors::abnormal_volume::push_abnormal_volume_event_factors;
use crate::factors::ma::push_ma_support_factors;
use crate::factors::macd::{macd_lines, push_macd_numeric_factors};
use crate::factors::price_position::{push_price_position_factors, push_range_compression};
use crate::factors::semantic::push_b2_semantic_factors;
use crate::factors::series::{FactorList, mean_tail, rolling_mean_series};
use crate::factors::types::{FactorInputRow, FactorRow, FactorValue};
use crate::factors::volume::push_volume_turnover_factors;
use crate::factors::zx::{push_zx_pullback_factors, zx_lines};
use crate::model::{Candidate, Method, PreparedRow};

pub const FACTOR_ARTIFACT_VERSION: u32 = 1;
pub const FACTOR_LIBRARY_VERSION: &str = "rust-factor-library-v2";

pub fn history_raw_factors(history: &[FactorInputRow]) -> FactorList {
    history_factor_fields(history, None, None)
}

pub fn history_factor_fields(
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
    let turnover_rates = history
        .iter()
        .map(|row| row.turnover_rate)
        .collect::<Vec<_>>();
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
    let latest_turnover_rate = latest.and_then(|row| row.turnover_rate);

    let ma25_values = ma25.iter().copied().flatten().collect::<Vec<_>>();
    let zxdkx_values = zxdkx.iter().copied().flatten().collect::<Vec<_>>();
    let zxdq_values = zxdq.iter().copied().flatten().collect::<Vec<_>>();
    let avg_close5 = mean_tail(&close, 5);
    let avg_volume5 = mean_tail(&volume, 5);
    let avg_volume20 = mean_tail(&volume, 20);
    let avg_turnover5 = if turnover_rates.len() >= 5 {
        turnover_rates[turnover_rates.len() - 5..]
            .iter()
            .copied()
            .collect::<Option<Vec<_>>>()
            .and_then(|values| mean_tail(&values, 5))
    } else {
        None
    };

    let mut factors = Vec::new();
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
    push_abnormal_volume_event_factors(&mut factors, &open, &close, &volume, latest_close);
    push_b2_semantic_factors(&mut factors, history, signal, environment_state);
    factors
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
    let mut rows_by_code: BTreeMap<&str, Vec<FactorInputRow>> = BTreeMap::new();
    for row in prepared_rows {
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
                ma25: row.ma25,
                zxdkx: row.zxdkx,
                zxdq: row.zxdq,
                dif: Some(row.dif),
                dea: Some(row.dea),
                macd_hist: Some(row.macd_hist),
            });
    }

    candidates
        .iter()
        .map(|candidate| {
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
            let history_factors =
                history_factor_fields(&history, candidate.signal.as_deref(), environment_state);
            let history_factor_count = history_factors.len();
            for (key, value) in history_factors {
                row.factors.insert(key, value);
            }
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
