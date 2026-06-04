use std::collections::BTreeMap;

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::Value;

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
#[serde(untagged)]
pub enum FactorValue {
    Number(f64),
    Category(String),
    Bool(bool),
    Missing,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FactorRow {
    pub code: String,
    pub method: Method,
    pub factors: BTreeMap<String, FactorValue>,
    pub diagnostics: BTreeMap<String, Value>,
}

impl FactorRow {
    pub fn new(code: impl Into<String>, method: Method) -> Self {
        Self {
            code: code.into(),
            method,
            factors: BTreeMap::new(),
            diagnostics: BTreeMap::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct RankedCandidate {
    pub code: String,
    pub model_score: f64,
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
    pub llm_action: Option<String>,
    pub llm_risk_flags: Vec<String>,
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
            llm_action: annotation.map(|item| item.llm_action.clone()),
            llm_risk_flags: annotation
                .map(|item| item.llm_risk_flags.clone())
                .unwrap_or_default(),
        }
    }
}
