use std::cell::RefCell;
use std::collections::BTreeMap;
use std::time::Duration;

use anyhow::Context;
use chrono::NaiveDate;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value, json};

use crate::model::MarketRow;

const RT_K_MARKET_WILDCARDS: [&str; 3] = ["*.SH", "*.SZ", "*.BJ"];
const RT_K_VOLUME_TO_DAILY_VOL: f64 = 100.0;
const RT_K_AMOUNT_TO_DAILY_AMOUNT: f64 = 1000.0;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct IntradaySnapshotRow {
    pub ts_code: String,
    pub name: String,
    pub trade_date: NaiveDate,
    pub trade_time: String,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub vol: f64,
    pub amount: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct MacdPeriodState {
    pub ts_code: String,
    pub period_type: String,
    pub ema12: f64,
    pub ema26: f64,
    pub dea: f64,
    pub period_count: i32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct LiveMacdValue {
    pub ts_code: String,
    pub period_type: String,
    pub dif: f64,
    pub dea: f64,
    pub hist: f64,
    pub period_count: i32,
}

pub fn derive_live_macd_from_period_state(
    state: &MacdPeriodState,
    price_live_qfq: f64,
) -> LiveMacdValue {
    let ema12 = state.ema12 * (11.0 / 13.0) + price_live_qfq * (2.0 / 13.0);
    let ema26 = state.ema26 * (25.0 / 27.0) + price_live_qfq * (2.0 / 27.0);
    let dif = ema12 - ema26;
    let dea = state.dea * 0.8 + dif * 0.2;
    LiveMacdValue {
        ts_code: state.ts_code.clone(),
        period_type: state.period_type.clone(),
        dif,
        dea,
        hist: dif - dea,
        period_count: state.period_count + 1,
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RawRtKRow {
    fields: BTreeMap<String, Value>,
}

impl RawRtKRow {
    pub fn from_value(value: Value) -> Self {
        let fields = match value {
            Value::Object(map) => map.into_iter().collect(),
            _ => BTreeMap::new(),
        };
        Self { fields }
    }

    fn value(&self, names: &[&str]) -> Option<&Value> {
        names.iter().find_map(|name| self.fields.get(*name))
    }
}

pub trait IntradaySnapshotProvider {
    fn fetch_rt_k(&self, ts_code: &str) -> anyhow::Result<Vec<RawRtKRow>>;
}

#[derive(Debug)]
pub struct TushareRestProvider {
    token: String,
    endpoint: String,
    client: reqwest::blocking::Client,
}

impl TushareRestProvider {
    pub fn new(token: String) -> anyhow::Result<Self> {
        Self::with_endpoint(token, "https://api.tushare.pro".to_string())
    }

    pub fn with_endpoint(token: String, endpoint: String) -> anyhow::Result<Self> {
        let token = token.trim().to_string();
        if token.is_empty() {
            anyhow::bail!("A Tushare token is required for intraday mode.");
        }
        let client = reqwest::blocking::Client::builder()
            .connect_timeout(Duration::from_secs(10))
            .timeout(Duration::from_secs(60))
            .build()?;
        Ok(Self {
            token,
            endpoint,
            client,
        })
    }
}

impl IntradaySnapshotProvider for TushareRestProvider {
    fn fetch_rt_k(&self, ts_code: &str) -> anyhow::Result<Vec<RawRtKRow>> {
        let response = self
            .client
            .post(&self.endpoint)
            .json(&tushare_rt_k_request_payload(&self.token, ts_code))
            .send()
            .with_context(|| format!("Failed to fetch Tushare rt_k snapshot for {ts_code}"))?
            .error_for_status()
            .with_context(|| format!("Tushare rt_k HTTP error for {ts_code}"))?
            .json::<TushareRtKResponse>()
            .with_context(|| format!("Failed to parse Tushare rt_k response for {ts_code}"))?;
        parse_tushare_rt_k_response(response)
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct TushareRtKResponse {
    pub code: i64,
    #[serde(default)]
    pub msg: String,
    pub data: Option<TushareRtKData>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct TushareRtKData {
    pub fields: Vec<String>,
    pub items: Vec<Vec<Value>>,
}

#[derive(Debug, Default)]
pub struct StaticRtKProvider {
    responses: BTreeMap<String, Vec<RawRtKRow>>,
    calls: RefCell<Vec<String>>,
}

impl StaticRtKProvider {
    pub fn new<const N: usize>(responses: [(&str, Vec<RawRtKRow>); N]) -> Self {
        Self {
            responses: responses
                .into_iter()
                .map(|(key, rows)| (key.to_string(), rows))
                .collect(),
            calls: RefCell::new(Vec::new()),
        }
    }

    pub fn calls(&self) -> Vec<String> {
        self.calls.borrow().clone()
    }
}

impl IntradaySnapshotProvider for StaticRtKProvider {
    fn fetch_rt_k(&self, ts_code: &str) -> anyhow::Result<Vec<RawRtKRow>> {
        self.calls.borrow_mut().push(ts_code.to_string());
        Ok(self.responses.get(ts_code).cloned().unwrap_or_default())
    }
}

pub fn fetch_rt_k_snapshot<P: IntradaySnapshotProvider>(
    provider: &P,
    trade_date: NaiveDate,
    fallback_trade_time: &str,
) -> anyhow::Result<Vec<IntradaySnapshotRow>> {
    let mut raw_rows = Vec::new();
    for ts_code in RT_K_MARKET_WILDCARDS {
        raw_rows.extend(provider.fetch_rt_k(ts_code)?);
    }
    if raw_rows.is_empty() {
        anyhow::bail!("Tushare rt_k returned no usable rows.");
    }
    normalize_rt_k_rows(raw_rows, trade_date, fallback_trade_time)
}

pub fn tushare_rt_k_request_payload(token: &str, ts_code: &str) -> Value {
    json!({
        "api_name": "rt_k",
        "token": token,
        "params": {
            "ts_code": ts_code
        },
        "fields": [
            "ts_code",
            "name",
            "open",
            "high",
            "low",
            "close",
            "vol",
            "amount",
            "trade_time"
        ]
    })
}

pub fn parse_tushare_rt_k_response(response: TushareRtKResponse) -> anyhow::Result<Vec<RawRtKRow>> {
    if response.code != 0 {
        anyhow::bail!("Tushare rt_k API error {}: {}", response.code, response.msg);
    }
    let Some(data) = response.data else {
        return Ok(Vec::new());
    };
    Ok(data
        .items
        .into_iter()
        .map(|item| {
            let mut object = Map::new();
            for (field, value) in data.fields.iter().zip(item) {
                object.insert(field.clone(), value);
            }
            RawRtKRow::from_value(Value::Object(object))
        })
        .collect())
}

pub fn normalize_rt_k_rows(
    raw_rows: Vec<RawRtKRow>,
    trade_date: NaiveDate,
    fallback_trade_time: &str,
) -> anyhow::Result<Vec<IntradaySnapshotRow>> {
    let mut rows = raw_rows
        .into_iter()
        .map(|row| normalize_rt_k_row(&row, trade_date, fallback_trade_time))
        .collect::<anyhow::Result<Vec<_>>>()?;
    rows.sort_by(|left, right| left.ts_code.cmp(&right.ts_code));
    Ok(rows)
}

pub fn build_intraday_market_rows(
    history: Vec<MarketRow>,
    snapshot: &[IntradaySnapshotRow],
    trade_date: NaiveDate,
) -> Vec<MarketRow> {
    build_intraday_market_rows_with_macd_states(history, snapshot, trade_date, &[])
}

pub fn build_intraday_market_rows_with_macd_states(
    history: Vec<MarketRow>,
    snapshot: &[IntradaySnapshotRow],
    trade_date: NaiveDate,
    macd_states: &[MacdPeriodState],
) -> Vec<MarketRow> {
    let snapshot_codes = snapshot
        .iter()
        .map(|row| row.ts_code.as_str())
        .collect::<std::collections::BTreeSet<_>>();
    let latest_adj_factor_by_code = history
        .iter()
        .filter(|row| row.trade_date <= trade_date)
        .filter_map(|row| {
            row.adj_factor
                .filter(|value| value.is_finite() && *value > 0.0)
                .map(|value| (row.ts_code.clone(), (row.trade_date, value)))
        })
        .fold(
            BTreeMap::<String, (NaiveDate, f64)>::new(),
            |mut acc, item| {
                let (code, (date, value)) = item;
                if acc
                    .get(code.as_str())
                    .is_none_or(|(current_date, _)| date > *current_date)
                {
                    acc.insert(code, (date, value));
                }
                acc
            },
        );
    let latest_structure_factors_by_code = history
        .iter()
        .filter(|row| row.trade_date < trade_date)
        .fold(
            BTreeMap::<String, (NaiveDate, BTreeMap<String, f64>)>::new(),
            |mut acc, row| {
                let structure_factors = previous_eod_structure_factors(row);
                if structure_factors.is_empty() {
                    return acc;
                }
                if acc
                    .get(row.ts_code.as_str())
                    .is_none_or(|(current_date, _)| row.trade_date > *current_date)
                {
                    acc.insert(row.ts_code.clone(), (row.trade_date, structure_factors));
                }
                acc
            },
        );
    let macd_states_by_code = macd_states.iter().fold(
        BTreeMap::<&str, Vec<&MacdPeriodState>>::new(),
        |mut acc, state| {
            acc.entry(state.ts_code.as_str()).or_default().push(state);
            acc
        },
    );
    let mut rows = history
        .into_iter()
        .filter(|row| {
            !(row.trade_date == trade_date && snapshot_codes.contains(row.ts_code.as_str()))
        })
        .collect::<Vec<_>>();
    rows.extend(snapshot.iter().map(|row| {
        let mut db_factors = latest_structure_factors_by_code
            .get(row.ts_code.as_str())
            .map(|(_date, factors)| factors.clone())
            .unwrap_or_default();
        if !db_factors.is_empty() {
            db_factors.insert("intraday_structure_source_previous_eod".to_string(), 1.0);
        }
        if row.vol != 0.0 {
            db_factors.insert("chip_vwap".to_string(), row.amount * 10.0 / row.vol);
        }
        let adj_factor = latest_adj_factor_by_code
            .get(row.ts_code.as_str())
            .map(|(_date, value)| *value);
        if let Some(adj_factor) = adj_factor.filter(|value| value.is_finite() && *value > 0.0) {
            let price_live_qfq = row.close * adj_factor;
            db_factors.insert("intraday_price_live_qfq".to_string(), price_live_qfq);
            if let Some(states) = macd_states_by_code.get(row.ts_code.as_str()) {
                for state in states {
                    let live = derive_live_macd_from_period_state(state, price_live_qfq);
                    db_factors.insert(format!("macd_{}_dif", live.period_type), live.dif);
                    db_factors.insert(format!("macd_{}_dea", live.period_type), live.dea);
                    db_factors.insert(format!("macd_{}_hist", live.period_type), live.hist);
                    db_factors.insert(
                        format!("macd_{}_period_count", live.period_type),
                        f64::from(live.period_count),
                    );
                }
            }
        }
        MarketRow {
            ts_code: row.ts_code.clone(),
            trade_date,
            open: row.open,
            high: row.high,
            low: row.low,
            close: row.close,
            vol: row.vol,
            turnover_rate: None,
            adj_factor,
            db_factors,
        }
    }));
    rows.sort_by(|left, right| {
        left.ts_code
            .cmp(&right.ts_code)
            .then(left.trade_date.cmp(&right.trade_date))
    });
    rows
}

fn previous_eod_structure_factors(row: &MarketRow) -> BTreeMap<String, f64> {
    row.db_factors
        .iter()
        .filter(|(key, value)| {
            value.is_finite()
                && (key.starts_with("rolling_")
                    || key.starts_with("left_peak_")
                    || key.starts_with("ths_")
                    || key.starts_with("stock_vs_ths_")
                    || key.starts_with("stock_env_"))
        })
        .map(|(key, value)| (key.clone(), *value))
        .collect()
}

fn normalize_rt_k_row(
    raw: &RawRtKRow,
    trade_date: NaiveDate,
    fallback_trade_time: &str,
) -> anyhow::Result<IntradaySnapshotRow> {
    Ok(IntradaySnapshotRow {
        ts_code: normalize_ts_code(required_string(raw, &["code", "ts_code", "代码"])?.as_str())?,
        name: required_string(raw, &["name", "名称"])?,
        trade_date,
        trade_time: optional_string(raw, &["trade_time", "更新时间"])
            .filter(|value| !value.trim().is_empty())
            .unwrap_or_else(|| fallback_trade_time.to_string()),
        open: required_f64(raw, &["open", "开盘价"])?,
        high: required_f64(raw, &["high", "最高价"])?,
        low: required_f64(raw, &["low", "最低价"])?,
        close: required_f64(raw, &["close", "最新价"])?,
        vol: required_f64(raw, &["vol", "成交量"])? / RT_K_VOLUME_TO_DAILY_VOL,
        amount: required_f64(raw, &["amount", "成交额"])? / RT_K_AMOUNT_TO_DAILY_AMOUNT,
    })
}

fn normalize_ts_code(code: &str) -> anyhow::Result<String> {
    let stripped = code.trim().to_ascii_uppercase();
    if stripped.ends_with(".SZ") || stripped.ends_with(".SH") || stripped.ends_with(".BJ") {
        return Ok(stripped);
    }
    if stripped.starts_with('0') || stripped.starts_with('2') || stripped.starts_with('3') {
        return Ok(format!("{stripped}.SZ"));
    }
    if stripped.starts_with('6') || stripped.starts_with('9') {
        return Ok(format!("{stripped}.SH"));
    }
    if stripped.starts_with('4') || stripped.starts_with('8') {
        return Ok(format!("{stripped}.BJ"));
    }
    anyhow::bail!("Unsupported ts_code: {code}")
}

fn required_string(raw: &RawRtKRow, names: &[&str]) -> anyhow::Result<String> {
    optional_string(raw, names)
        .with_context(|| format!("rt_k snapshot missing column: {}", names[0]))
}

fn optional_string(raw: &RawRtKRow, names: &[&str]) -> Option<String> {
    raw.value(names).and_then(|value| match value {
        Value::String(value) => Some(value.clone()),
        Value::Number(value) => Some(value.to_string()),
        _ => None,
    })
}

fn required_f64(raw: &RawRtKRow, names: &[&str]) -> anyhow::Result<f64> {
    let value = raw
        .value(names)
        .with_context(|| format!("rt_k snapshot missing column: {}", names[0]))?;
    match value {
        Value::Number(number) => number
            .as_f64()
            .with_context(|| format!("rt_k snapshot invalid number: {}", names[0])),
        Value::String(value) => value
            .trim()
            .parse::<f64>()
            .with_context(|| format!("rt_k snapshot invalid number: {}", names[0])),
        _ => anyhow::bail!("rt_k snapshot invalid number: {}", names[0]),
    }
}
