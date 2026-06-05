use std::collections::BTreeMap;

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::model::Method;

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

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct FactorInputRow {
    pub trade_date: Option<NaiveDate>,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub turnover_n: f64,
    pub turnover_rate: Option<f64>,
    pub ma25: Option<f64>,
    pub zxdkx: Option<f64>,
    pub zxdq: Option<f64>,
    pub dif: Option<f64>,
    pub dea: Option<f64>,
    pub macd_hist: Option<f64>,
}
