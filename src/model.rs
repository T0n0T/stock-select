use std::collections::BTreeMap;
use std::fmt;
use std::str::FromStr;

use chrono::NaiveDate;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Method {
    B1,
    B2,
    B3,
    Lsh,
    Scm,
    Pbm,
    Qianlong,
    Dribull,
}

impl Method {
    pub fn as_str(self) -> &'static str {
        match self {
            Method::B1 => "b1",
            Method::B2 => "b2",
            Method::B3 => "b3",
            Method::Lsh => "lsh",
            Method::Scm => "scm",
            Method::Pbm => "pbm",
            Method::Qianlong => "qianlong",
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
            "scm" => Ok(Method::Scm),
            "pbm" => Ok(Method::Pbm),
            "qianlong" => Ok(Method::Qianlong),
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

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DbDataGapReason {
    MissingTable,
    SchemaMismatch,
    MissingRows,
}

impl DbDataGapReason {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::MissingTable => "missing_table",
            Self::SchemaMismatch => "schema_mismatch",
            Self::MissingRows => "missing_rows",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DbDataGap {
    pub reason: DbDataGapReason,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub missing_columns: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub expected_rows: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub actual_rows: Option<i64>,
}

impl DbDataGap {
    pub fn missing_table() -> Self {
        Self {
            reason: DbDataGapReason::MissingTable,
            missing_columns: Vec::new(),
            expected_rows: None,
            actual_rows: None,
        }
    }

    pub fn schema_mismatch(missing_columns: Vec<String>) -> Self {
        Self {
            reason: DbDataGapReason::SchemaMismatch,
            missing_columns,
            expected_rows: None,
            actual_rows: None,
        }
    }

    pub fn missing_rows(expected_rows: i64, actual_rows: i64) -> Self {
        Self {
            reason: DbDataGapReason::MissingRows,
            missing_columns: Vec::new(),
            expected_rows: Some(expected_rows),
            actual_rows: Some(actual_rows),
        }
    }

    pub fn prevents_table_read(&self) -> bool {
        matches!(
            self.reason,
            DbDataGapReason::MissingTable | DbDataGapReason::SchemaMismatch
        )
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct PreparedDataset {
    pub rows: Vec<PreparedRow>,
    pub db_data_gaps: BTreeMap<String, DbDataGap>,
}

impl PreparedDataset {
    pub fn complete(rows: Vec<PreparedRow>) -> Self {
        Self {
            rows,
            db_data_gaps: BTreeMap::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct MarketDataset {
    pub rows: Vec<MarketRow>,
    pub db_data_gaps: BTreeMap<String, DbDataGap>,
}

impl MarketDataset {
    pub fn complete(rows: Vec<MarketRow>) -> Self {
        Self {
            rows,
            db_data_gaps: BTreeMap::new(),
        }
    }
}

pub trait IntoMarketDataset {
    fn into_market_dataset(self) -> MarketDataset;
}

impl IntoMarketDataset for Vec<MarketRow> {
    fn into_market_dataset(self) -> MarketDataset {
        MarketDataset::complete(self)
    }
}

impl IntoMarketDataset for MarketDataset {
    fn into_market_dataset(self) -> MarketDataset {
        self
    }
}

pub fn db_data_gap_warning_message(
    pick_date: NaiveDate,
    table: &str,
    gap: &DbDataGap,
    source: Option<&str>,
) -> String {
    let mut message = format!(
        "warning: db data gap pick_date={pick_date} table={table} reason={}",
        gap.reason.as_str()
    );
    if !gap.missing_columns.is_empty() {
        message.push_str(&format!(
            " missing_columns={}",
            gap.missing_columns.join(",")
        ));
    }
    if let (Some(expected_rows), Some(actual_rows)) = (gap.expected_rows, gap.actual_rows) {
        message.push_str(&format!(
            " expected_rows={expected_rows} actual_rows={actual_rows}"
        ));
    }
    if let Some(source) = source {
        message.push_str(&format!(" source={source}"));
    }
    message
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
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub adj_factor: Option<f64>,
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
