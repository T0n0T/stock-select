use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::Context;
use chrono::NaiveDate;

use crate::model::Method;

const DEFAULT_PYTHON_PROJECT: &str = "/home/pi/Documents/agents/stock-select";

#[derive(Debug, Clone)]
pub struct PythonBridge {
    project_root: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PythonCommandSpec {
    pub program: String,
    pub args: Vec<String>,
    pub current_dir: PathBuf,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PythonStage {
    Chart,
    Review,
}

#[derive(Debug, Clone)]
pub struct PythonStageArgs<'a> {
    pub method: Method,
    pub pick_date: NaiveDate,
    pub runtime_root: &'a Path,
    pub environment_state: Option<&'a str>,
    pub environment_reason: Option<&'a str>,
}

impl PythonBridge {
    pub fn new(project_root: impl Into<PathBuf>) -> Self {
        Self {
            project_root: project_root.into(),
        }
    }

    pub fn default_project() -> Self {
        Self::new(DEFAULT_PYTHON_PROJECT)
    }

    pub fn command_spec(&self, stage: PythonStage, args: PythonStageArgs<'_>) -> PythonCommandSpec {
        let mut command_args = vec![
            "run".to_string(),
            "stock-select".to_string(),
            stage.as_cli_name().to_string(),
            "--method".to_string(),
            args.method.as_str().to_string(),
            "--pick-date".to_string(),
            args.pick_date.format("%Y-%m-%d").to_string(),
            "--runtime-root".to_string(),
            args.runtime_root.display().to_string(),
        ];

        if stage == PythonStage::Review {
            if let Some(value) = args.environment_state {
                command_args.push("--environment-state".to_string());
                command_args.push(value.to_string());
            }
            if let Some(value) = args.environment_reason {
                command_args.push("--environment-reason".to_string());
                command_args.push(value.to_string());
            }
        }

        PythonCommandSpec {
            program: "uv".to_string(),
            args: command_args,
            current_dir: self.project_root.clone(),
        }
    }

    pub fn run_stage(&self, stage: PythonStage, args: PythonStageArgs<'_>) -> anyhow::Result<()> {
        let spec = self.command_spec(stage, args);
        let status = Command::new(&spec.program)
            .args(&spec.args)
            .current_dir(&spec.current_dir)
            .status()
            .with_context(|| format!("spawn python {} stage", stage.as_cli_name()))?;
        if !status.success() {
            anyhow::bail!(
                "python {} stage failed with status {status}",
                stage.as_cli_name()
            );
        }
        Ok(())
    }
}

impl PythonStage {
    pub fn as_cli_name(self) -> &'static str {
        match self {
            Self::Chart => "chart",
            Self::Review => "review",
        }
    }
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

    use super::*;

    #[test]
    fn chart_command_uses_python_cli_runtime_and_pick_date() {
        let bridge = PythonBridge::new("/tmp/python-stock-select");
        let spec = bridge.command_spec(
            PythonStage::Chart,
            PythonStageArgs {
                method: Method::B1,
                pick_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
                runtime_root: Path::new("/tmp/run-root"),
                environment_state: Some("weak"),
                environment_reason: Some("ignored for chart"),
            },
        );

        assert_eq!(spec.program, "uv");
        assert_eq!(spec.current_dir, PathBuf::from("/tmp/python-stock-select"));
        assert_eq!(
            spec.args,
            vec![
                "run",
                "stock-select",
                "chart",
                "--method",
                "b1",
                "--pick-date",
                "2026-05-25",
                "--runtime-root",
                "/tmp/run-root",
            ]
        );
    }

    #[test]
    fn review_command_forwards_environment_context() {
        let bridge = PythonBridge::new("/tmp/python-stock-select");
        let spec = bridge.command_spec(
            PythonStage::Review,
            PythonStageArgs {
                method: Method::B1,
                pick_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
                runtime_root: Path::new("/tmp/run-root"),
                environment_state: Some("weak"),
                environment_reason: Some("match python scheduled weak env"),
            },
        );

        assert_eq!(
            spec.args,
            vec![
                "run",
                "stock-select",
                "review",
                "--method",
                "b1",
                "--pick-date",
                "2026-05-25",
                "--runtime-root",
                "/tmp/run-root",
                "--environment-state",
                "weak",
                "--environment-reason",
                "match python scheduled weak env",
            ]
        );
    }
}
