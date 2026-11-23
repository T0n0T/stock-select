use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::engine::entry::EntryAssessment;
pub use crate::factors::types::{FactorRow, FactorValue};
use crate::model::Method;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SelectionCandidate {
    pub code: String,
    pub name: Option<String>,
    pub method: Method,
    pub pick_date: NaiveDate,
    pub close: Option<f64>,
    pub turnover_n: Option<f64>,
    pub signal: Option<String>,
    pub raw_payload: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RankedCandidate {
    pub code: String,
    pub model_score: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub raw_model_score: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub entry_assessment: Option<EntryAssessment>,
    pub model_rank: usize,
    pub feature_vector_path: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct LlmAnnotation {
    pub code: String,
    pub llm_action: String,
    pub llm_confidence: Option<f64>,
    pub llm_risk_flags: Vec<String>,
    pub llm_comment: Option<String>,
    pub raw_response_path: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct DisplayRow {
    pub code: String,
    pub name: Option<String>,
    #[serde(default)]
    pub industry: Option<String>,
    pub model_rank: Option<usize>,
    pub model_score: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub raw_model_score: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub entry_assessment: Option<EntryAssessment>,
    pub llm_action: Option<String>,
    pub llm_risk_flags: Vec<String>,
    #[serde(default)]
    pub llm_comment: Option<String>,
}

impl DisplayRow {
    pub fn from_ranked(
        ranked: &RankedCandidate,
        annotation: Option<&LlmAnnotation>,
        name: Option<&str>,
    ) -> Self {
        Self {
            code: ranked.code.clone(),
            name: name.map(str::to_string),
            industry: None,
            model_rank: Some(ranked.model_rank),
            model_score: Some(ranked.model_score),
            raw_model_score: ranked.raw_model_score,
            entry_assessment: ranked.entry_assessment.clone(),
            llm_action: annotation.map(|item| item.llm_action.clone()),
            llm_risk_flags: annotation
                .map(|item| item.llm_risk_flags.clone())
                .unwrap_or_default(),
            llm_comment: annotation.and_then(|item| item.llm_comment.clone()),
        }
    }
}
