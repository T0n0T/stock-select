use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use chrono::{Duration, NaiveDate};
use serde_json::{Value, json};

use crate::cache::{history_payload_for_code, load_prepared_cache_for_mode};
use crate::engine::artifacts::{SelectionRunPaths, write_selection_json};
use crate::engine::b2::{
    B2FactorProvider, CandidatePayloadFactorProvider, artifact_key_for_run,
    candidate_from_legacy_json,
};
use crate::engine::capability::ensure_model_run_supported;
use crate::engine::inference::{
    LightGbmRuntimeModel, ModelFeatureMetadata, build_feature_vector,
    resolve_method_model_artifacts_with_overrides,
};
use crate::engine::types::{
    DisplayRow, FactorRow, FactorValue, RankedCandidate, SelectionCandidate,
};
use crate::environment::ResolvedEnvironment;
use crate::model::Method;

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
    if request.method != Method::B2 {
        anyhow::bail!(
            "{} selection run is not implemented",
            request.method.as_str()
        );
    }

    let artifact_key = artifact_key_for_run(request.pick_date, request.intraday);
    let paths = SelectionRunPaths::new(&request.runtime_root, request.method, &artifact_key);
    eprintln!(
        "[selection] resolve model method={} runtime_root={}",
        request.method,
        request.runtime_root.display()
    );
    let model_artifacts = resolve_method_model_artifacts_with_overrides(
        request.method,
        &request.runtime_root,
        request.model_path.as_deref(),
        request.model_feature_metadata_path.as_deref(),
    )?;
    let model = load_model(
        model_artifacts.model_path.as_deref(),
        model_artifacts.metadata_path.as_deref(),
    )?;
    let mut candidates = read_candidates(&request.candidates_path, request.pick_date)?;
    inject_environment_factor(&mut candidates, request.environment.as_ref());
    eprintln!(
        "[selection] loaded candidates rows={} source={}",
        candidates.len(),
        display_candidate_source(&request.runtime_root, &request.candidates_path)
    );
    inject_prepared_history_if_available(
        &mut candidates,
        &request.runtime_root,
        request.pick_date,
        request.intraday,
    )?;
    eprintln!("[selection] prepared history injection checked");
    let factor_provider = CandidatePayloadFactorProvider;
    let factors = candidates
        .iter()
        .map(|candidate| factor_provider.factor_row(candidate))
        .collect::<anyhow::Result<Vec<_>>>()?;
    eprintln!("[selection] computed factors rows={}", factors.len());
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

fn read_candidates(path: &Path, pick_date: NaiveDate) -> anyhow::Result<Vec<SelectionCandidate>> {
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
        .map(|row| candidate_from_legacy_json(row, pick_date))
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
    pick_date: NaiveDate,
    intraday: bool,
) -> anyhow::Result<()> {
    if candidates
        .iter()
        .all(|candidate| candidate.raw_payload.get("history").is_some())
    {
        return Ok(());
    }

    let start_date = pick_date - Duration::days(366);
    let Some(rows) = load_prepared_cache_for_mode(
        runtime_root,
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        intraday,
    )?
    else {
        return Ok(());
    };

    for candidate in candidates {
        if candidate.raw_payload.get("history").is_some() {
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
        scored.push((candidate.code.clone(), score));
    }

    scored.sort_by(|left, right| {
        right
            .1
            .total_cmp(&left.1)
            .then_with(|| left.0.cmp(&right.0))
    });

    let ranked = scored
        .into_iter()
        .enumerate()
        .map(|(index, (code, model_score))| RankedCandidate {
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
