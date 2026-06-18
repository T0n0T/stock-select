use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::engine::capability::ensure_model_run_supported;
use crate::engine::types::{FactorRow, FactorValue};
use crate::model::Method;

pub struct LightGbmRuntimeModel {
    booster: lightgbm3::Booster,
}

impl LightGbmRuntimeModel {
    pub fn from_file(path: &str) -> anyhow::Result<Self> {
        Ok(Self {
            booster: lightgbm3::Booster::from_file(path)?,
        })
    }

    pub fn num_features(&self) -> i32 {
        self.booster.num_features()
    }

    pub fn predict(&self, values: &[f64]) -> anyhow::Result<f64> {
        if values.is_empty() {
            anyhow::bail!("LightGBM feature vector is empty");
        }
        let prediction =
            self.booster
                .predict_with_params(values, values.len() as i32, true, "num_threads=1")?;
        prediction
            .first()
            .copied()
            .ok_or_else(|| anyhow::anyhow!("LightGBM returned no prediction"))
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedMethodModelArtifacts {
    pub model_path: Option<PathBuf>,
    pub metadata_path: Option<PathBuf>,
    pub model_dir: Option<PathBuf>,
    pub routing_path: Option<PathBuf>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
struct ModelRoutingState {
    #[serde(default)]
    eod: ModelModeState,
    #[serde(default)]
    intraday: ModelModeState,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
struct ModelModeState {
    #[serde(default = "default_model_status")]
    status: String,
    #[serde(default)]
    model_dir: Option<String>,
    #[serde(default)]
    reason: Option<String>,
}

impl Default for ModelModeState {
    fn default() -> Self {
        Self {
            status: default_model_status(),
            model_dir: None,
            reason: None,
        }
    }
}

fn default_model_status() -> String {
    "ready".to_string()
}

pub fn default_model_dir(method: Method) -> Option<&'static str> {
    match method {
        Method::B2 => Some("models/b2"),
        Method::B3 => Some("models/b3"),
        Method::Lsh => Some("models/lsh"),
        Method::B1 | Method::Dribull => None,
    }
}

pub fn resolve_method_model_artifacts(
    method: Method,
    runtime_root: &Path,
) -> anyhow::Result<ResolvedMethodModelArtifacts> {
    resolve_method_model_artifacts_for_mode(method, runtime_root, false)
}

pub fn resolve_method_model_artifacts_for_mode(
    method: Method,
    runtime_root: &Path,
    intraday: bool,
) -> anyhow::Result<ResolvedMethodModelArtifacts> {
    resolve_method_model_artifacts_for_mode_with_overrides(
        method,
        runtime_root,
        intraday,
        None,
        None,
    )
}

pub fn resolve_method_model_artifacts_with_overrides(
    method: Method,
    runtime_root: &Path,
    override_model_path: Option<&Path>,
    override_metadata_path: Option<&Path>,
) -> anyhow::Result<ResolvedMethodModelArtifacts> {
    resolve_method_model_artifacts_for_mode_with_overrides(
        method,
        runtime_root,
        false,
        override_model_path,
        override_metadata_path,
    )
}

pub fn resolve_method_model_artifacts_for_mode_with_overrides(
    method: Method,
    runtime_root: &Path,
    intraday: bool,
    override_model_path: Option<&Path>,
    override_metadata_path: Option<&Path>,
) -> anyhow::Result<ResolvedMethodModelArtifacts> {
    ensure_model_run_supported(method)?;
    match (override_model_path, override_metadata_path) {
        (Some(model_path), Some(metadata_path)) => {
            return Ok(ResolvedMethodModelArtifacts {
                model_path: Some(model_path.to_path_buf()),
                metadata_path: Some(metadata_path.to_path_buf()),
                model_dir: None,
                routing_path: None,
            });
        }
        (None, None) => {}
        _ => anyhow::bail!(
            "--model-path and --model-feature-metadata-path must be provided together"
        ),
    }
    let default_model_dir = default_model_dir(method)
        .ok_or_else(|| anyhow::anyhow!("method has no default model dir"))?;
    let model_dir = resolve_model_dir_for_mode(method, runtime_root, default_model_dir, intraday)?;
    resolve_complete_model_dir(method, &model_dir)
}

pub fn resolve_method_model_artifacts_for_route<'a, I>(
    method: Method,
    runtime_root: &Path,
    intraday: bool,
    route_values: I,
) -> anyhow::Result<ResolvedMethodModelArtifacts>
where
    I: IntoIterator<Item = (&'a str, Option<&'a str>)>,
{
    ensure_model_run_supported(method)?;
    let default_model_dir = default_model_dir(method)
        .ok_or_else(|| anyhow::anyhow!("method has no default model dir"))?;
    let model_dir = resolve_model_dir_for_mode(method, runtime_root, default_model_dir, intraday)?;
    let routing_path = model_dir.join("model_routing.json");
    if !routing_path.exists() {
        return resolve_complete_model_dir(method, &model_dir);
    }

    let manifest = read_model_routing_manifest(&routing_path)?;
    let mut context = BTreeMap::<String, Option<String>>::new();
    context.insert("intraday".to_string(), Some(intraday.to_string()));
    for (key, value) in route_values {
        context.insert(key.to_string(), value.map(str::to_string));
    }
    let model_key = select_routed_model_key(&manifest, &context);
    let relative_dir = manifest.models.get(model_key).ok_or_else(|| {
        anyhow::anyhow!(
            "model_routing.json selected unknown model '{model_key}' under {}",
            model_dir.display()
        )
    })?;
    resolve_complete_model_dir(method, &model_dir.join(relative_dir))
}

fn resolve_model_dir_for_mode(
    method: Method,
    runtime_root: &Path,
    default_model_dir: &str,
    intraday: bool,
) -> anyhow::Result<PathBuf> {
    let default_dir = runtime_root.join(default_model_dir);
    let state_path = default_dir.join("model_state.json");
    if !state_path.exists() {
        if intraday {
            anyhow::bail!(
                "WARNING: {} intraday model is not ready: intraday model state is missing under {}; publish an intraday model and update model_state.json before using --intraday",
                method.as_str(),
                state_path.display()
            );
        }
        return Ok(default_dir);
    }
    let state: ModelRoutingState = serde_json::from_slice(&std::fs::read(&state_path)?)?;
    let mode_state = if intraday {
        &state.intraday
    } else {
        &state.eod
    };
    if mode_state.status != "ready" {
        let reason = mode_state
            .reason
            .as_deref()
            .unwrap_or("model mode is not ready");
        anyhow::bail!(
            "WARNING: {} {} model is not ready: {reason}",
            method.as_str(),
            if intraday { "intraday" } else { "eod" }
        );
    }
    let dir = mode_state
        .model_dir
        .as_deref()
        .map(|path| runtime_root.join(path))
        .unwrap_or(default_dir);
    Ok(dir)
}

fn resolve_complete_model_dir(
    method: Method,
    model_dir: &Path,
) -> anyhow::Result<ResolvedMethodModelArtifacts> {
    let routing_path = model_dir.join("model_routing.json");
    if routing_path.exists() {
        let _manifest = read_model_routing_manifest(&routing_path)?;
        return Ok(ResolvedMethodModelArtifacts {
            model_path: None,
            metadata_path: None,
            model_dir: Some(model_dir.to_path_buf()),
            routing_path: Some(routing_path),
        });
    }

    let model_path = model_dir.join("model.txt");
    let metadata_path = model_dir.join("model_metadata.json");

    match (model_path.exists(), metadata_path.exists()) {
        (true, true) => Ok(ResolvedMethodModelArtifacts {
            model_path: Some(model_path),
            metadata_path: Some(metadata_path),
            model_dir: Some(model_dir.to_path_buf()),
            routing_path: None,
        }),
        (false, false) => {
            anyhow::bail!(
                "missing default {} model artifacts under {}: expected model.txt and model_metadata.json",
                method.as_str(),
                model_dir.display()
            )
        }
        _ => anyhow::bail!(
            "incomplete default {} model artifacts under {}: expected model.txt and model_metadata.json",
            method.as_str(),
            model_dir.display()
        ),
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ModelRoutingManifest {
    #[serde(default)]
    pub version: u64,
    pub default_model: String,
    #[serde(default)]
    pub models: BTreeMap<String, String>,
    #[serde(default)]
    pub routes: Vec<ModelRouteManifest>,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub struct ModelRouteManifest {
    #[serde(default)]
    pub when: BTreeMap<String, Value>,
    pub model: String,
}

pub fn read_model_routing_manifest(path: &Path) -> anyhow::Result<ModelRoutingManifest> {
    let manifest: ModelRoutingManifest = serde_json::from_slice(&std::fs::read(path)?)?;
    if manifest.default_model.is_empty() {
        anyhow::bail!("model_routing.json default_model cannot be empty");
    }
    if !manifest.models.contains_key(&manifest.default_model) {
        anyhow::bail!(
            "model_routing.json default_model '{}' is not listed in models",
            manifest.default_model
        );
    }
    for route in &manifest.routes {
        if !manifest.models.contains_key(&route.model) {
            anyhow::bail!(
                "model_routing.json route references unknown model '{}'",
                route.model
            );
        }
    }
    Ok(manifest)
}

pub fn select_routed_model_key<'a>(
    manifest: &'a ModelRoutingManifest,
    context: &BTreeMap<String, Option<String>>,
) -> &'a str {
    manifest
        .routes
        .iter()
        .find(|route| route_matches(route, context))
        .map(|route| route.model.as_str())
        .unwrap_or(manifest.default_model.as_str())
}

fn route_matches(route: &ModelRouteManifest, context: &BTreeMap<String, Option<String>>) -> bool {
    route
        .when
        .iter()
        .all(|(key, expected)| route_value_matches(context.get(key), expected))
}

fn route_value_matches(actual: Option<&Option<String>>, expected: &Value) -> bool {
    match expected {
        Value::Array(values) => values
            .iter()
            .any(|candidate| route_value_matches(actual, candidate)),
        Value::Null => actual.is_none_or(Option::is_none),
        Value::Bool(expected_bool) => actual
            .and_then(|value| value.as_deref())
            .is_some_and(|value| value == expected_bool.to_string()),
        Value::String(expected_string) => actual
            .and_then(|value| value.as_deref())
            .is_some_and(|value| value == expected_string),
        Value::Number(expected_number) => actual
            .and_then(|value| value.as_deref())
            .is_some_and(|value| value == expected_number.to_string()),
        Value::Object(_) => false,
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelFeatureMetadata {
    #[serde(default)]
    pub numeric_columns: Vec<String>,
    #[serde(default)]
    pub categorical_columns: Vec<String>,
    #[serde(default)]
    pub categorical_levels: BTreeMap<String, Vec<String>>,
    #[serde(default = "default_categorical_encoding")]
    pub categorical_encoding: String,
    #[serde(default)]
    pub categorical_code_maps: BTreeMap<String, BTreeMap<String, i64>>,
    #[serde(default)]
    pub feature_names: Vec<String>,
}

fn default_categorical_encoding() -> String {
    "one_hot".to_string()
}

#[derive(Debug, Clone, PartialEq)]
pub struct BuiltFeatureVector {
    pub feature_names: Vec<String>,
    pub values: Vec<f64>,
    pub missing_numeric_features: Vec<String>,
}

pub fn build_feature_vector(
    row: &FactorRow,
    metadata: &ModelFeatureMetadata,
) -> anyhow::Result<BuiltFeatureVector> {
    let mut values = Vec::new();
    let mut feature_names = Vec::new();
    let mut missing_numeric_features = Vec::new();

    for column in &metadata.numeric_columns {
        feature_names.push(column.clone());
        match row.factors.get(column) {
            Some(FactorValue::Number(value)) => values.push(*value),
            Some(FactorValue::Bool(value)) => values.push(if *value { 1.0 } else { 0.0 }),
            _ => {
                values.push(0.0);
                missing_numeric_features.push(column.clone());
            }
        }
    }

    for column in &metadata.categorical_columns {
        let current = match row.factors.get(column) {
            Some(FactorValue::Category(value)) => value.as_str(),
            Some(FactorValue::Bool(true)) => "true",
            Some(FactorValue::Bool(false)) => "false",
            _ => "unknown",
        };

        match metadata.categorical_encoding.as_str() {
            "one_hot" => {
                for level in metadata
                    .categorical_levels
                    .get(column)
                    .cloned()
                    .unwrap_or_default()
                {
                    feature_names.push(format!("{column}={level}"));
                    values.push(if current == level { 1.0 } else { 0.0 });
                }
            }
            "native" => {
                feature_names.push(column.clone());
                let code = metadata
                    .categorical_code_maps
                    .get(column)
                    .and_then(|code_map| code_map.get(current))
                    .copied()
                    .unwrap_or(-1);
                values.push(code as f64);
            }
            other => anyhow::bail!("unsupported categorical_encoding: {other}"),
        }
    }

    if !metadata.feature_names.is_empty() && metadata.feature_names != feature_names {
        anyhow::bail!("metadata feature_names do not match computed feature order");
    }

    Ok(BuiltFeatureVector {
        feature_names,
        values,
        missing_numeric_features,
    })
}
