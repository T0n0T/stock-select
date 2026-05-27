use std::str::FromStr;

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Method {
    B1,
    B2,
    Dribull,
}

#[derive(Debug, Error, PartialEq, Eq)]
#[error("unsupported method '{0}', expected one of: b1, b2, dribull")]
pub struct MethodParseError(pub String);

impl Method {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::B1 => "b1",
            Self::B2 => "b2",
            Self::Dribull => "dribull",
        }
    }
}

impl FromStr for Method {
    type Err = MethodParseError;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value.trim().to_ascii_lowercase().as_str() {
            "b1" => Ok(Self::B1),
            "b2" => Ok(Self::B2),
            "dribull" => Ok(Self::Dribull),
            _ => Err(MethodParseError(value.to_string())),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MarketRow {
    pub ts_code: String,
    pub trade_date: NaiveDate,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub vol: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PreparedRow {
    pub ts_code: String,
    pub trade_date: NaiveDate,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub turnover_n: f64,
    pub k: f64,
    pub d: f64,
    pub j: f64,
    pub zxdq: Option<f64>,
    pub zxdkx: Option<f64>,
    pub dif: f64,
    pub dea: f64,
    pub macd_hist: f64,
    pub ma25: Option<f64>,
    pub ma60: Option<f64>,
    pub ma144: Option<f64>,
    pub chg_d: Option<f64>,
    pub weekly_ma_bull: bool,
    pub max_vol_not_bearish: bool,
    pub v_shrink: bool,
    pub safe_mode: bool,
    pub lt_filter: bool,
    pub yellow_b1: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Candidate {
    pub code: String,
    pub pick_date: NaiveDate,
    pub close: f64,
    pub turnover_n: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub signal: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub yellow_b1: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ScreenResult {
    pub method: Method,
    pub pick_date: NaiveDate,
    pub pool_source: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pool_file: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub screen_version: Option<u32>,
    pub candidates: Vec<Candidate>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub generated_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub count: Option<usize>,
    #[serde(skip_serializing_if = "std::collections::BTreeMap::is_empty")]
    pub stats: std::collections::BTreeMap<String, usize>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_supported_methods_case_insensitively() {
        assert_eq!("b1".parse::<Method>().unwrap(), Method::B1);
        assert_eq!("B2".parse::<Method>().unwrap(), Method::B2);
        assert_eq!(" Dribull ".parse::<Method>().unwrap(), Method::Dribull);
    }

    #[test]
    fn rejects_unsupported_method() {
        let err = "hcr".parse::<Method>().unwrap_err();
        assert_eq!(err, MethodParseError("hcr".to_string()));
    }
}
