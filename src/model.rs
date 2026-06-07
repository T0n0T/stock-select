use std::collections::BTreeMap;
use std::fmt;
use std::str::FromStr;

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Method {
    B1,
    B2,
    B3,
    Lsh,
    Dribull,
}

impl Method {
    pub fn as_str(self) -> &'static str {
        match self {
            Method::B1 => "b1",
            Method::B2 => "b2",
            Method::B3 => "b3",
            Method::Lsh => "lsh",
            Method::Dribull => "dribull",
        }
    }
}

impl fmt::Display for Method {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for Method {
    type Err = anyhow::Error;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "b1" => Ok(Method::B1),
            "b2" => Ok(Method::B2),
            "b3" => Ok(Method::B3),
            "lsh" => Ok(Method::Lsh),
            "dribull" => Ok(Method::Dribull),
            _ => anyhow::bail!("unsupported method: {value}"),
        }
    }
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
    pub turnover_rate: Option<f64>,
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
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub db_factors: BTreeMap<String, f64>,
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
    pub turnover_rate: Option<f64>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub db_factors: BTreeMap<String, f64>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct InstrumentInfo {
    pub name: Option<String>,
    pub industry: Option<String>,
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
    #[serde(skip_serializing_if = "Option::is_none")]
    pub mode: Option<String>,
    pub method: Method,
    pub pick_date: NaiveDate,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub trade_date: Option<NaiveDate>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fetched_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub run_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source: Option<String>,
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
