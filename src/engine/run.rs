use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use chrono::{Duration, NaiveDate};
use serde_json::{Value, json};

use crate::cache::{history_payload_for_code, load_prepared_cache_for_mode};
use crate::engine::artifacts::{SelectionRunPaths, write_selection_json};
use crate::engine::b2::{
    B2FactorProvider, CandidatePayloadFactorProvider, adjust_b2_cyq_post_rerank_score,
    artifact_key_for_run, candidate_from_legacy_json,
};
use crate::engine::capability::ensure_model_run_supported;
use crate::engine::inference::{
    LightGbmRuntimeModel, ModelFeatureMetadata, build_feature_vector,
    resolve_method_model_artifacts_for_mode_with_overrides,
};
use crate::engine::types::{
    DisplayRow, FactorRow, FactorValue, RankedCandidate, SelectionCandidate,
};
use crate::environment::ResolvedEnvironment;
use crate::factors::registry::{build_candidate_factor_rows_from_refs, write_factor_artifact};
use crate::model::{Candidate, Method, PreparedRow};

const FEATURE_VECTORS_ARTIFACT: &str = "feature_vectors.json";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SelectionRunRequest {
    pub method: Method,
    pub pick_date: NaiveDate,
    pub runtime_root: PathBuf,
    pub intraday: bool,
    pub candidates_path: PathBuf,
    pub model_path: Option<PathBuf>,
    pub model_feature_metadata_path: Option<PathBuf>,
    pub environment: Option<ResolvedEnvironment>,
    pub record: bool,
    pub record_window_trading_days: Option<usize>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SelectionRunResult {
    pub artifact_key: String,
    pub run_dir: PathBuf,
    pub rows: usize,
}

pub fn run_selection(request: SelectionRunRequest) -> anyhow::Result<SelectionRunResult> {
    ensure_model_run_supported(request.method)?;

    let artifact_key = artifact_key_for_run(request.pick_date, request.intraday);
    let paths = SelectionRunPaths::new(&request.runtime_root, request.method, &artifact_key);
    eprintln!(
        "[selection] resolve model method={} runtime_root={}",
        request.method,
        request.runtime_root.display()
    );
    let model_artifacts = resolve_method_model_artifacts_for_mode_with_overrides(
        request.method,
        &request.runtime_root,
        request.intraday,
        request.model_path.as_deref(),
        request.model_feature_metadata_path.as_deref(),
    )?;
    let model = load_model(
        model_artifacts.model_path.as_deref(),
        model_artifacts.metadata_path.as_deref(),
    )?;
    let mut candidates =
        read_candidates(&request.candidates_path, request.pick_date, request.method)?;
    inject_environment_factor(&mut candidates, request.environment.as_ref());
    eprintln!(
        "[selection] loaded candidates rows={} source={}",
        candidates.len(),
        display_candidate_source(&request.runtime_root, &request.candidates_path)
    );
    inject_prepared_history_if_available(
        &mut candidates,
        &request.runtime_root,
        request.method,
        request.pick_date,
        request.intraday,
    )?;
    eprintln!("[selection] prepared history injection checked");
    let factors = match factor_rows_from_prepared_cache(
        &request.runtime_root,
        request.method,
        request.pick_date,
        request.intraday,
        request
            .environment
            .as_ref()
            .map(|environment| environment.state.as_str()),
        &candidates,
    )? {
        Some(rows) => rows,
        None => {
            let factor_provider = CandidatePayloadFactorProvider;
            candidates
                .iter()
                .map(|candidate| factor_provider.factor_row(candidate))
                .collect::<anyhow::Result<Vec<_>>>()?
        }
    };
    eprintln!("[selection] computed factors rows={}", factors.len());
    write_factor_artifact(
        &request.runtime_root,
        request.method,
        &artifact_key,
        &factors,
        Some(&request.candidates_path),
    )?;
    let (ranked, feature_vectors) = rank_candidates(&candidates, &factors, model.as_ref())?;
    eprintln!(
        "[selection] ranked rows={} feature_vectors={}",
        ranked.len(),
        feature_vectors.len()
    );
    let display = display_rows(&candidates, &ranked);

    write_selection_json(
        &paths.run_path(),
        &json!({
            "method": request.method.as_str(),
            "artifact_key": artifact_key,
            "intraday": request.intraday,
            "pick_date": request.pick_date,
            "model_path": model_artifacts.model_path,
            "metadata_path": model_artifacts.metadata_path,
            "candidate_source": display_candidate_source(&request.runtime_root, &request.candidates_path),
            "environment": {
                "state": request.environment.as_ref().map(|env| env.state.as_str()),
                "reason": request.environment.as_ref().and_then(|env| env.reason.as_deref()),
                "source": request.environment.as_ref().map(|env| env.source.as_str()),
                "interval_start": request.environment.as_ref().and_then(|env| env.interval_start),
                "interval_end": request.environment.as_ref().and_then(|env| env.interval_end),
            },
            "record": {
                "enabled": request.record,
                "window_trading_days": request.record_window_trading_days,
            },
            "rows": ranked.len(),
        }),
    )?;
    write_selection_json(
        &paths.candidates_path(),
        &json!({
            "method": request.method.as_str(),
            "artifact_key": artifact_key,
            "rows": candidates,
        }),
    )?;
    write_selection_json(
        &paths.factors_path(),
        &json!({
            "method": request.method.as_str(),
            "artifact_key": artifact_key,
            "rows": factors,
        }),
    )?;
    write_selection_json(
        &paths.ranked_path(),
        &json!({
            "method": request.method.as_str(),
            "artifact_key": artifact_key,
            "rows": ranked,
        }),
    )?;
    if !feature_vectors.is_empty() {
        write_selection_json(
            &paths.feature_vectors_path(),
            &json!({
                "method": request.method.as_str(),
                "artifact_key": artifact_key,
                "rows": feature_vectors,
            }),
        )?;
    }
    write_selection_json(
        &paths.display_path(),
        &json!({
            "method": request.method.as_str(),
            "artifact_key": artifact_key,
            "rows": display,
        }),
    )?;
    eprintln!(
        "[selection] wrote artifacts dir={}",
        paths.run_dir.display()
    );

    Ok(SelectionRunResult {
        artifact_key,
        run_dir: paths.run_dir,
        rows: ranked.len(),
    })
}

fn inject_environment_factor(
    candidates: &mut [SelectionCandidate],
    environment: Option<&ResolvedEnvironment>,
) {
    let Some(environment) = environment else {
        return;
    };
    for candidate in candidates {
        if let Some(object) = candidate.raw_payload.as_object_mut() {
            object.insert("env".to_string(), Value::String(environment.state.clone()));
        }
    }
}

fn read_candidates(
    path: &Path,
    pick_date: NaiveDate,
    method: Method,
) -> anyhow::Result<Vec<SelectionCandidate>> {
    let payload: Value = serde_json::from_slice(&std::fs::read(path)?)?;
    let rows = payload
        .get("rows")
        .and_then(Value::as_array)
        .or_else(|| payload.get("candidates").and_then(Value::as_array))
        .or_else(|| payload.as_array())
        .ok_or_else(|| {
            anyhow::anyhow!("candidate input must be an array or contain rows/candidates")
        })?;

    rows.iter()
        .map(|row| {
            let mut candidate = candidate_from_legacy_json(row, pick_date)?;
            candidate.method = method;
            Ok(candidate)
        })
        .collect()
}

fn display_candidate_source(runtime_root: &Path, candidates_path: &Path) -> String {
    candidates_path
        .strip_prefix(runtime_root)
        .unwrap_or(candidates_path)
        .to_string_lossy()
        .to_string()
}

fn read_model_metadata(path: Option<&Path>) -> anyhow::Result<Option<ModelFeatureMetadata>> {
    path.map(|path| {
        let bytes = std::fs::read(path)?;
        Ok(serde_json::from_slice(&bytes)?)
    })
    .transpose()
}

fn inject_prepared_history_if_available(
    candidates: &mut [SelectionCandidate],
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    intraday: bool,
) -> anyhow::Result<()> {
    if candidates.iter().all(candidate_has_complete_history) {
        return Ok(());
    }

    let start_date = pick_date - Duration::days(366);
    let Some(rows) = load_prepared_cache_for_mode(
        runtime_root,
        method,
        pick_date,
        start_date,
        pick_date,
        intraday,
    )?
    else {
        return Ok(());
    };

    for candidate in candidates {
        if candidate_has_complete_history(candidate) {
            continue;
        }
        let history = history_payload_for_code(&rows, &candidate.code);
        if history.is_empty() {
            continue;
        }
        let Some(object) = candidate.raw_payload.as_object_mut() else {
            continue;
        };
        object.insert("history".to_string(), Value::Array(history));
        object.insert(
            "history_source".to_string(),
            Value::String("prepared_cache".to_string()),
        );
    }

    Ok(())
}

fn factor_rows_from_prepared_cache(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    intraday: bool,
    environment_state: Option<&str>,
    candidates: &[SelectionCandidate],
) -> anyhow::Result<Option<Vec<FactorRow>>> {
    let start_date = pick_date - Duration::days(366);
    let Some(rows) = load_prepared_cache_for_mode(
        runtime_root,
        method,
        pick_date,
        start_date,
        pick_date,
        intraday,
    )?
    else {
        return Ok(None);
    };
    let latest_by_code = rows
        .iter()
        .filter(|row| row.trade_date == pick_date)
        .map(|row| (row.ts_code.as_str(), row))
        .collect::<BTreeMap<_, _>>();
    let Some(model_candidates) = candidates
        .iter()
        .map(|candidate| candidate_from_prepared(candidate, &latest_by_code, pick_date))
        .collect::<Option<Vec<_>>>()
    else {
        return Ok(None);
    };
    let prepared_refs = rows.iter().collect::<Vec<&PreparedRow>>();
    Ok(Some(build_candidate_factor_rows_from_refs(
        &model_candidates,
        &prepared_refs,
        method,
        environment_state,
    )))
}

fn candidate_from_prepared(
    candidate: &SelectionCandidate,
    latest_by_code: &BTreeMap<&str, &PreparedRow>,
    pick_date: NaiveDate,
) -> Option<Candidate> {
    let latest = latest_by_code.get(candidate.code.as_str()).copied();
    Some(Candidate {
        code: candidate.code.clone(),
        pick_date,
        close: candidate.close.or_else(|| latest.map(|row| row.close))?,
        turnover_n: candidate
            .turnover_n
            .or_else(|| latest.map(|row| row.turnover_n))?,
        signal: candidate.signal.clone(),
        yellow_b1: None,
    })
}

fn candidate_has_complete_history(candidate: &SelectionCandidate) -> bool {
    candidate
        .raw_payload
        .get("history")
        .is_some_and(history_payload_is_complete)
}

fn history_payload_is_complete(value: &Value) -> bool {
    let Some(rows) = value.as_array() else {
        return false;
    };
    !rows.is_empty() && rows.iter().all(history_row_is_complete)
}

fn history_row_is_complete(row: &Value) -> bool {
    has_number(row, "open")
        && has_number(row, "high")
        && has_number(row, "low")
        && has_number(row, "close")
        && (has_number(row, "volume") || has_number(row, "vol"))
        && (has_number(row, "turnover_n") || has_number(row, "turnover_rate"))
}

fn has_number(value: &Value, key: &str) -> bool {
    value.get(key).and_then(Value::as_f64).is_some()
}

struct LoadedModel {
    runtime_model: LightGbmRuntimeModel,
    metadata: ModelFeatureMetadata,
}

#[derive(Debug, Clone, PartialEq, serde::Serialize)]
struct FeatureVectorDiagnostic {
    code: String,
    feature_names: Vec<String>,
    values: Vec<f64>,
    missing_numeric_features: Vec<String>,
}

fn load_model(
    model_path: Option<&Path>,
    metadata_path: Option<&Path>,
) -> anyhow::Result<Option<LoadedModel>> {
    match (model_path, metadata_path) {
        (Some(model_path), Some(metadata_path)) => {
            let metadata = read_model_metadata(Some(metadata_path))?
                .ok_or_else(|| anyhow::anyhow!("model metadata was not loaded"))?;
            let model_path_text = model_path.to_str().ok_or_else(|| {
                anyhow::anyhow!("model path is not valid UTF-8: {}", model_path.display())
            })?;
            Ok(Some(LoadedModel {
                runtime_model: LightGbmRuntimeModel::from_file(model_path_text)?,
                metadata,
            }))
        }
        (None, None) => Ok(None),
        _ => anyhow::bail!("incomplete model artifact resolution"),
    }
}

fn rank_candidates(
    candidates: &[SelectionCandidate],
    factors: &[FactorRow],
    model: Option<&LoadedModel>,
) -> anyhow::Result<(Vec<RankedCandidate>, Vec<FeatureVectorDiagnostic>)> {
    let factor_by_code = factors
        .iter()
        .map(|row| (row.code.as_str(), row))
        .collect::<BTreeMap<_, _>>();
    let mut feature_vectors = Vec::new();
    let mut scored = Vec::new();
    for candidate in candidates {
        let row = factor_by_code
            .get(candidate.code.as_str())
            .copied()
            .ok_or_else(|| anyhow::anyhow!("missing factors for {}", candidate.code))?;
        let (score, diagnostic) = score_candidate(&candidate.code, row, model)?;
        if let Some(diagnostic) = diagnostic {
            feature_vectors.push(diagnostic);
        }
        scored.push((candidate.code.clone(), score, row));
    }

    let mut normalized_scores = vec![0.0; scored.len()];
    let mut raw_order = (0..scored.len()).collect::<Vec<_>>();
    raw_order.sort_by(|left, right| {
        scored[*right]
            .1
            .total_cmp(&scored[*left].1)
            .then_with(|| scored[*left].0.cmp(&scored[*right].0))
    });
    let denominator = scored.len().saturating_sub(1).max(1) as f64;
    for (rank_index, scored_index) in raw_order.into_iter().enumerate() {
        let normalized_score = if scored.len() > 1 {
            (denominator - rank_index as f64) / denominator
        } else {
            1.0
        };
        normalized_scores[scored_index] =
            adjust_b2_cyq_post_rerank_score(normalized_score, scored[scored_index].2);
    }

    let mut scored = scored
        .into_iter()
        .enumerate()
        .map(|(index, (code, raw_score, _row))| (code, normalized_scores[index], raw_score))
        .collect::<Vec<_>>();

    scored.sort_by(|left, right| {
        right
            .1
            .total_cmp(&left.1)
            .then_with(|| right.2.total_cmp(&left.2))
            .then_with(|| left.0.cmp(&right.0))
    });

    let ranked = scored
        .into_iter()
        .enumerate()
        .map(|(index, (code, model_score, _raw_score))| RankedCandidate {
            code,
            model_score,
            model_rank: index + 1,
            feature_vector_path: model.map(|_| FEATURE_VECTORS_ARTIFACT.to_string()),
        })
        .collect();
    Ok((ranked, feature_vectors))
}

fn score_candidate(
    code: &str,
    row: &FactorRow,
    model: Option<&LoadedModel>,
) -> anyhow::Result<(f64, Option<FeatureVectorDiagnostic>)> {
    if let Some(model) = model {
        let vector = build_feature_vector(row, &model.metadata)?;
        let score = model.runtime_model.predict(&vector.values)?;
        return Ok((
            score,
            Some(FeatureVectorDiagnostic {
                code: code.to_string(),
                feature_names: vector.feature_names,
                values: vector.values,
                missing_numeric_features: vector.missing_numeric_features,
            }),
        ));
    }
    if let Some(FactorValue::Number(score)) = row.factors.get("model_score") {
        return Ok((*score, None));
    }
    Ok((0.0, None))
}

fn display_rows(
    candidates: &[SelectionCandidate],
    ranked_rows: &[RankedCandidate],
) -> Vec<DisplayRow> {
    let name_by_code = candidates
        .iter()
        .map(|candidate| (candidate.code.as_str(), candidate.name.as_deref()))
        .collect::<BTreeMap<_, _>>();

    ranked_rows
        .iter()
        .map(|ranked| {
            DisplayRow::from_ranked(
                ranked,
                None,
                name_by_code
                    .get(ranked.code.as_str())
                    .and_then(|name| *name),
            )
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::NaiveDate;
    use serde_json::json;

    fn factor_row(code: &str, env: &str, base_score: f64) -> FactorRow {
        let mut row = FactorRow::new(code, Method::B2);
        row.factors
            .insert("env".to_string(), FactorValue::Category(env.to_string()));
        row.factors
            .insert("model_score".to_string(), FactorValue::Number(base_score));
        row
    }

    fn candidate(code: &str) -> SelectionCandidate {
        SelectionCandidate {
            code: code.to_string(),
            name: None,
            method: Method::B2,
            pick_date: NaiveDate::from_ymd_opt(2026, 6, 5).unwrap(),
            close: None,
            turnover_n: None,
            signal: None,
            raw_payload: json!({}),
        }
    }

    #[test]
    fn rank_candidates_applies_cyq_post_rerank_before_sorting() {
        let candidates = (1..=10)
            .map(|index| candidate(&format!("{index:06}.SZ")))
            .collect::<Vec<_>>();
        let mut high_raw = factor_row("000001.SZ", "neutral", 1.0);
        high_raw
            .factors
            .insert("cyq_winner_rate".to_string(), FactorValue::Number(100.0));
        let mut lower_raw = factor_row("000002.SZ", "neutral", 0.95);
        lower_raw
            .factors
            .insert("cyq_winner_rate".to_string(), FactorValue::Number(50.0));
        let mut factors = vec![high_raw, lower_raw];
        for index in 3..=10 {
            let mut row = factor_row(
                &format!("{index:06}.SZ"),
                "neutral",
                0.95 - index as f64 * 0.01,
            );
            row.factors
                .insert("cyq_winner_rate".to_string(), FactorValue::Number(50.0));
            factors.push(row);
        }

        let (ranked, feature_vectors) = rank_candidates(&candidates, &factors, None).unwrap();

        assert!(feature_vectors.is_empty());
        assert_eq!(ranked[0].code, "000002.SZ");
        assert_eq!(ranked[0].model_rank, 1);
        assert!((ranked[1].model_score - 0.86).abs() < 1e-9);
    }
}
