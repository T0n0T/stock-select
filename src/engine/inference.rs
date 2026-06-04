use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

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
}

pub fn default_model_dir(method: Method) -> Option<&'static str> {
    match method {
        Method::B2 => Some("models/b2"),
        Method::B1 | Method::Dribull => None,
    }
}

pub fn resolve_method_model_artifacts(
    method: Method,
    runtime_root: &Path,
) -> anyhow::Result<ResolvedMethodModelArtifacts> {
    resolve_method_model_artifacts_with_overrides(method, runtime_root, None, None)
}

pub fn resolve_method_model_artifacts_with_overrides(
    method: Method,
    runtime_root: &Path,
    override_model_path: Option<&Path>,
    override_metadata_path: Option<&Path>,
) -> anyhow::Result<ResolvedMethodModelArtifacts> {
    ensure_model_run_supported(method)?;
    match (override_model_path, override_metadata_path) {
        (Some(model_path), Some(metadata_path)) => {
            return Ok(ResolvedMethodModelArtifacts {
                model_path: Some(model_path.to_path_buf()),
                metadata_path: Some(metadata_path.to_path_buf()),
            });
        }
        (None, None) => {}
        _ => anyhow::bail!(
            "--model-path and --model-feature-metadata-path must be provided together"
        ),
    }
    let default_model_dir = default_model_dir(method)
        .ok_or_else(|| anyhow::anyhow!("method has no default model dir"))?;
    let model_dir = runtime_root.join(default_model_dir);
    let model_path = model_dir.join("model.txt");
    let metadata_path = model_dir.join("model_metadata.json");

    match (model_path.exists(), metadata_path.exists()) {
        (true, true) => Ok(ResolvedMethodModelArtifacts {
            model_path: Some(model_path),
            metadata_path: Some(metadata_path),
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

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelFeatureMetadata {
    #[serde(default)]
    pub numeric_columns: Vec<String>,
    #[serde(default)]
    pub categorical_columns: Vec<String>,
    #[serde(default)]
    pub categorical_levels: BTreeMap<String, Vec<String>>,
    #[serde(default)]
    pub feature_names: Vec<String>,
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

    if !metadata.feature_names.is_empty() && metadata.feature_names != feature_names {
        anyhow::bail!("metadata feature_names do not match computed feature order");
    }

    Ok(BuiltFeatureVector {
        feature_names,
        values,
        missing_numeric_features,
    })
}
