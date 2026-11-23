//! 排序模型原始分数的开仓分档。名次归一化分数不参与门槛判断。
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::path::Path;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EntryAction {
    Open,
    Observe,
    Discard,
}

impl EntryAction {
    pub fn label(self) -> &'static str {
        match self {
            Self::Open => "开仓",
            Self::Observe => "观察",
            Self::Discard => "丢弃",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EntryAssessment {
    pub action: EntryAction,
    pub reason: String,
    #[serde(default)]
    pub research: bool,
    #[serde(default)]
    pub gate: Option<ScoreEntryGate>,
}

impl EntryAssessment {
    pub fn observe(reason: impl Into<String>) -> Self {
        Self {
            action: EntryAction::Observe,
            reason: reason.into(),
            research: false,
            gate: None,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScoreEntryGate {
    pub open_min_score: f64,
    pub discard_below_score: f64,
    pub top_n: usize,
    #[serde(default)]
    pub blocked_environments: Vec<String>,
}

impl ScoreEntryGate {
    pub fn validate(&self) -> anyhow::Result<()> {
        if !self.open_min_score.is_finite()
            || !self.discard_below_score.is_finite()
            || self.discard_below_score > self.open_min_score
            || self.top_n == 0
        {
            anyhow::bail!("invalid score entry thresholds or top_n");
        }
        if self
            .blocked_environments
            .iter()
            .any(|env| !matches!(env.as_str(), "weak" | "neutral" | "strong"))
        {
            anyhow::bail!("unknown blocked environment");
        }
        Ok(())
    }

    pub fn decide(
        &self,
        raw_score: Option<f64>,
        rank: Option<usize>,
        environment: Option<&str>,
    ) -> EntryAssessment {
        let (action, reason) = match raw_score.filter(|score| score.is_finite()) {
            None => (EntryAction::Observe, "缺少原始分数"),
            Some(score) if score < self.discard_below_score => {
                (EntryAction::Discard, "低于丢弃门槛")
            }
            Some(_) if !matches!(environment, Some("weak" | "neutral" | "strong")) => {
                (EntryAction::Observe, "缺少环境判断")
            }
            Some(_)
                if self
                    .blocked_environments
                    .iter()
                    .any(|env| Some(env.as_str()) == environment) =>
            {
                (EntryAction::Observe, "当前环境暂停开仓")
            }
            Some(_) if rank.is_none_or(|rank| rank == 0) => (EntryAction::Observe, "缺少有效排名"),
            Some(_) if rank.is_some_and(|rank| rank > self.top_n) => {
                (EntryAction::Observe, "超出开仓名额")
            }
            Some(score) if score < self.open_min_score => (EntryAction::Observe, "未达开仓门槛"),
            Some(_) => (EntryAction::Open, "分数与环境通过"),
        };
        EntryAssessment {
            action,
            reason: reason.into(),
            research: false,
            gate: Some(self.clone()),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ScoreEntryPolicy {
    pub schema_version: usize,
    pub method: String,
    pub model_sha256: String,
    pub calibration_end_date: NaiveDate,
    pub status: String,
    pub gate: ScoreEntryGate,
}

impl ScoreEntryPolicy {
    pub fn validate(&self) -> anyhow::Result<()> {
        self.gate.validate()?;
        if self.schema_version != 1
            || self.method != "scm"
            || !matches!(self.status.as_str(), "research" | "validated")
            || self.model_sha256.len() != 64
            || !self
                .model_sha256
                .bytes()
                .all(|value| value.is_ascii_hexdigit() && !value.is_ascii_uppercase())
        {
            anyhow::bail!("invalid SCM score entry policy binding");
        }
        Ok(())
    }

    pub fn applicability(
        &self,
        actual_model_sha256: &str,
        day: NaiveDate,
        intraday: bool,
    ) -> Option<&'static str> {
        if self.model_sha256 != actual_model_sha256 {
            return Some("模型与门槛不匹配");
        }
        if intraday {
            return Some("门槛仅经盘后校准");
        }
        if day <= self.calibration_end_date {
            return Some("日期早于校准完成");
        }
        None
    }
}

pub fn load_score_entry_policy(
    model: Option<&Path>,
    metadata: Option<&Path>,
) -> anyhow::Result<Option<(ScoreEntryPolicy, bool)>> {
    let Some(metadata) = metadata else {
        return Ok(None);
    };
    let raw: serde_json::Value = serde_json::from_slice(&std::fs::read(metadata)?)?;
    let Some(value) = raw.get("score_entry_policy") else {
        return Ok(None);
    };
    let policy: ScoreEntryPolicy = serde_json::from_value(value.clone())?;
    policy.validate()?;
    let matches = if let Some(path) = model {
        let digest = format!("{:x}", Sha256::digest(std::fs::read(path)?));
        digest == policy.model_sha256
    } else {
        false
    };
    Ok(Some((policy, matches)))
}

pub fn assess_ranked_entries(
    rows: &mut [crate::engine::types::RankedCandidate],
    binding: Option<&(ScoreEntryPolicy, bool)>,
    day: NaiveDate,
    intraday: bool,
    environment: Option<&str>,
) {
    for row in rows {
        let assessment = match binding {
            None => EntryAssessment::observe("模型未校准开仓门槛"),
            Some((_, false)) => EntryAssessment::observe("模型与门槛不匹配"),
            Some((policy, true)) => match policy.applicability(&policy.model_sha256, day, intraday)
            {
                Some(reason) => EntryAssessment::observe(reason),
                None => {
                    let mut assessment =
                        policy
                            .gate
                            .decide(row.raw_model_score, Some(row.model_rank), environment);
                    assessment.research = policy.status == "research";
                    assessment
                }
            },
        };
        row.entry_assessment = Some(assessment);
    }
}

pub fn mark_uncalibrated_display(
    rows: &mut [crate::engine::types::DisplayRow],
    method: crate::model::Method,
) {
    if method != crate::model::Method::Scm {
        return;
    }
    for row in rows {
        if row.entry_assessment.is_none() {
            row.entry_assessment = Some(EntryAssessment::observe("模型未校准开仓门槛"));
        }
    }
}
