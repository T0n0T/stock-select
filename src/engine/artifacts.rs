use std::path::{Path, PathBuf};

use serde::Serialize;
use serde_json::Value;

use crate::model::Method;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SelectionRunPaths {
    pub run_dir: PathBuf,
}

impl SelectionRunPaths {
    pub fn new(runtime_root: &Path, method: Method, artifact_key: &str) -> Self {
        Self {
            run_dir: runtime_root.join("select").join(format!(
                "{}.{}",
                artifact_key,
                method.as_str()
            )),
        }
    }

    pub fn run_path(&self) -> PathBuf {
        self.run_dir.join("run.json")
    }

    pub fn candidates_path(&self) -> PathBuf {
        self.run_dir.join("candidates.json")
    }

    pub fn factors_path(&self) -> PathBuf {
        self.run_dir.join("factors.json")
    }

    pub fn ranked_path(&self) -> PathBuf {
        self.run_dir.join("ranked.json")
    }

    pub fn feature_vectors_path(&self) -> PathBuf {
        self.run_dir.join("feature_vectors.json")
    }

    pub fn llm_tasks_path(&self) -> PathBuf {
        self.run_dir.join("llm_tasks.json")
    }

    pub fn llm_annotations_path(&self) -> PathBuf {
        self.run_dir.join("llm_annotations.json")
    }

    pub fn display_path(&self) -> PathBuf {
        self.run_dir.join("display.json")
    }
}

pub fn write_selection_json<T: Serialize>(path: &Path, payload: &T) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let temp_path = path.with_extension("json.tmp");
    std::fs::write(&temp_path, serde_json::to_vec_pretty(payload)?)?;
    std::fs::rename(temp_path, path)?;
    Ok(())
}

pub fn read_selection_json(path: &Path) -> anyhow::Result<Value> {
    let bytes = std::fs::read(path)?;
    Ok(serde_json::from_slice(&bytes)?)
}
