use std::collections::BTreeMap;
use std::path::PathBuf;

use chrono::NaiveDate;
use duckdb_neo::{
    Parameters, QueryParameter, ToValue,
    connection::Connection,
    environment::{Environment, StorageLocation},
    instance::{AttachBuilder, Instance},
    types::DateValue,
    value::Value as NativeValue,
    vector::Unknown,
};
use serde_json::Value;

use crate::config::resolve_db_check_tables;
use crate::db_check::preflight_db_native_load;
use crate::factors::stk_factor_pro::SOURCE_COLUMNS;
use crate::intraday::MacdPeriodState;
use crate::model::{DbDataGap, InstrumentInfo, MarketDataset, MarketRow};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DuckDbLocation {
    Memory,
    File(PathBuf),
    Quack(String),
}

impl DuckDbLocation {
    pub fn parse(value: &str) -> anyhow::Result<Self> {
        let value = value.trim();
        if value.is_empty() {
            anyhow::bail!("DuckDB path is empty");
        }
        if value == ":memory:" {
            return Ok(Self::Memory);
        }
        if value.starts_with("quack://") {
            return Ok(Self::Quack(value.to_string()));
        }
        if value.starts_with("quack:") {
            return Ok(Self::Quack(value.to_string()));
        }
        if value.starts_with("postgres://") || value.starts_with("postgresql://") {
            anyhow::bail!("PostgreSQL connection strings are no longer supported; set DUCKDB_PATH");
        }
        Ok(Self::File(PathBuf::from(value)))
    }
}

pub struct DuckDbConnection {
    connection: Connection,
    is_quack: bool,
}

#[derive(Debug, Clone)]
pub(crate) enum DuckDbParameter {
    Text(String),
    TextList(Vec<String>),
    Date(NaiveDate),
}

fn quack_text_literal(value: &str) -> anyhow::Result<String> {
    if value.contains('\0') {
        anyhow::bail!("DuckDB query text parameters cannot contain NUL");
    }
    Ok(format!("'{}'", value.replace('\'', "''")))
}

fn quack_parameter_literal(parameter: &DuckDbParameter) -> anyhow::Result<String> {
    match parameter {
        DuckDbParameter::Text(value) => quack_text_literal(value),
        DuckDbParameter::TextList(values) => {
            let values = values
                .iter()
                .map(|value| quack_text_literal(value))
                .collect::<anyhow::Result<Vec<_>>>()?;
            Ok(format!("CAST([{}] AS VARCHAR[])", values.join(", ")))
        }
        DuckDbParameter::Date(value) => Ok(format!("DATE '{}'", value.format("%Y-%m-%d"))),
    }
}

fn is_sql_identifier_byte(value: u8) -> bool {
    value.is_ascii_alphanumeric() || value == b'_' || value == b'$' || !value.is_ascii()
}

/// Quack currently forwards the query but not DuckDB's positional bindings.
/// Render only parameter tokens; literals, quoted identifiers and comments are opaque.
fn inline_quack_parameters(sql: &str, parameters: &[DuckDbParameter]) -> anyhow::Result<String> {
    let bytes = sql.as_bytes();
    let mut output = String::with_capacity(sql.len());
    let mut copied = 0;
    let mut index = 0;
    while index < bytes.len() {
        match bytes[index] {
            b'\'' | b'"' => {
                let quote = bytes[index];
                let escaped = quote == b'\''
                    && index > 0
                    && matches!(bytes[index - 1], b'E' | b'e')
                    && (index < 2 || !is_sql_identifier_byte(bytes[index - 2]));
                index += 1;
                while index < bytes.len() {
                    if escaped && bytes[index] == b'\\' {
                        index = (index + 2).min(bytes.len());
                    } else if bytes[index] == quote {
                        index += 1;
                        if index < bytes.len() && bytes[index] == quote {
                            index += 1;
                        } else {
                            break;
                        }
                    } else {
                        index += 1;
                    }
                }
            }
            b'-' if bytes.get(index + 1) == Some(&b'-') => {
                index += 2;
                while index < bytes.len() && bytes[index] != b'\n' {
                    index += 1;
                }
            }
            b'/' if bytes.get(index + 1) == Some(&b'*') => {
                index += 2;
                let mut depth = 1usize;
                while index < bytes.len() && depth > 0 {
                    if bytes[index..].starts_with(b"/*") {
                        depth += 1;
                        index += 2;
                    } else if bytes[index..].starts_with(b"*/") {
                        depth -= 1;
                        index += 2;
                    } else {
                        index += 1;
                    }
                }
            }
            b'$' if index == 0 || !is_sql_identifier_byte(bytes[index - 1]) => {
                let start = index;
                index += 1;
                if bytes.get(index).is_some_and(u8::is_ascii_digit) {
                    while bytes.get(index).is_some_and(u8::is_ascii_digit) {
                        index += 1;
                    }
                    let number = sql[start + 1..index].parse::<usize>()?;
                    let parameter = number
                        .checked_sub(1)
                        .and_then(|offset| parameters.get(offset))
                        .ok_or_else(|| {
                            anyhow::anyhow!("missing DuckDB query parameter {}", number)
                        })?;
                    output.push_str(&sql[copied..start]);
                    output.push_str(&quack_parameter_literal(parameter)?);
                    copied = index;
                } else {
                    let mut end = index;
                    if bytes
                        .get(end)
                        .is_some_and(|b| b.is_ascii_alphabetic() || *b == b'_')
                    {
                        end += 1;
                        while bytes
                            .get(end)
                            .is_some_and(|b| b.is_ascii_alphanumeric() || *b == b'_')
                        {
                            end += 1;
                        }
                    }
                    if bytes.get(end) == Some(&b'$') {
                        let delimiter = &bytes[start..=end];
                        index = end + 1;
                        if let Some(offset) = bytes[index..]
                            .windows(delimiter.len())
                            .position(|candidate| candidate == delimiter)
                        {
                            index += offset + delimiter.len();
                        } else {
                            index = bytes.len();
                        }
                    }
                }
            }
            _ => index += 1,
        }
    }
    output.push_str(&sql[copied..]);
    Ok(output)
}

#[derive(Debug)]
pub(crate) enum DuckDbCell {
    Native(NativeValue),
}

#[derive(Debug)]
pub(crate) struct DuckDbRow {
    values: Vec<DuckDbCell>,
    columns: std::sync::Arc<BTreeMap<String, usize>>,
}

pub(crate) trait DuckDbDecode: Sized {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self>;
}

impl DuckDbRow {
    pub(crate) fn try_get<T: DuckDbDecode>(&self, column: &str) -> anyhow::Result<T> {
        let index = self
            .columns
            .get(column)
            .ok_or_else(|| anyhow::anyhow!("DuckDB query did not return column {column}"))?;
        T::decode(&self.values[*index])
    }
}

impl DuckDbDecode for String {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self> {
        let DuckDbCell::Native(value) = value;
        value
            .get::<String>()?
            .ok_or_else(|| anyhow::anyhow!("DuckDB returned NULL for required text"))
    }
}
impl DuckDbDecode for Option<String> {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self> {
        let DuckDbCell::Native(value) = value;
        Ok(value.get::<String>()?)
    }
}
impl DuckDbDecode for NaiveDate {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self> {
        let DuckDbCell::Native(value) = value;
        value
            .get::<DateValue>()?
            .and_then(|date| NaiveDate::from_epoch_days(date.0))
            .ok_or_else(|| anyhow::anyhow!("DuckDB returned NULL or out-of-range DATE"))
    }
}
impl DuckDbDecode for Option<NaiveDate> {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self> {
        let DuckDbCell::Native(value) = value;
        Ok(value
            .get::<DateValue>()?
            .and_then(|date| NaiveDate::from_epoch_days(date.0)))
    }
}
impl DuckDbDecode for f64 {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self> {
        let DuckDbCell::Native(value) = value;
        value
            .get::<f64>()?
            .ok_or_else(|| anyhow::anyhow!("DuckDB returned NULL for required DOUBLE"))
    }
}
impl DuckDbDecode for Option<f64> {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self> {
        let DuckDbCell::Native(value) = value;
        Ok(value.get::<f64>()?)
    }
}
impl DuckDbDecode for i64 {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self> {
        let DuckDbCell::Native(value) = value;
        value
            .get::<i64>()?
            .ok_or_else(|| anyhow::anyhow!("DuckDB returned NULL for required BIGINT"))
    }
}
impl DuckDbDecode for i32 {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self> {
        let DuckDbCell::Native(value) = value;
        Ok(value
            .get::<i64>()?
            .ok_or_else(|| anyhow::anyhow!("DuckDB returned NULL for required INTEGER"))?
            .try_into()?)
    }
}
impl DuckDbDecode for bool {
    fn decode(value: &DuckDbCell) -> anyhow::Result<Self> {
        let DuckDbCell::Native(value) = value;
        value
            .get::<bool>()?
            .ok_or_else(|| anyhow::anyhow!("DuckDB returned NULL for required BOOLEAN"))
    }
}

impl DuckDbConnection {
    pub fn execute(&self, sql: &str) -> anyhow::Result<()> {
        self.connection.execute(sql, Parameters::None)?;
        Ok(())
    }

    pub fn execute_batch(&self, sql: &str) -> anyhow::Result<()> {
        for statement in sql
            .split(';')
            .map(str::trim)
            .filter(|part| !part.is_empty())
        {
            self.execute(statement)?;
        }
        Ok(())
    }

    pub(crate) fn query_rows(
        &self,
        sql: &str,
        parameters: &[DuckDbParameter],
    ) -> anyhow::Result<Vec<DuckDbRow>> {
        self.query_map(sql, parameters, Ok)
    }

    pub(crate) fn query_map<T>(
        &self,
        sql: &str,
        parameters: &[DuckDbParameter],
        map: impl FnMut(DuckDbRow) -> anyhow::Result<T>,
    ) -> anyhow::Result<Vec<T>> {
        let mut rows: Vec<T> = Vec::new();
        self.query_for_each(sql, parameters, map, |row| {
            rows.push(row);
            Ok(())
        })?;
        Ok(rows)
    }

    pub(crate) fn query_for_each<T>(
        &self,
        sql: &str,
        parameters: &[DuckDbParameter],
        mut map: impl FnMut(DuckDbRow) -> anyhow::Result<T>,
        mut consume: impl FnMut(T) -> anyhow::Result<()>,
    ) -> anyhow::Result<()> {
        let connection = &self.connection;
        let quack_sql = if self.is_quack && !parameters.is_empty() {
            Some(inline_quack_parameters(sql, parameters)?)
        } else {
            None
        };
        let sql = quack_sql.as_deref().unwrap_or(sql);
        let bind_parameters = if self.is_quack { &[][..] } else { parameters };
        let values = bind_parameters
            .iter()
            .map(|parameter| match parameter {
                DuckDbParameter::Text(value) => value.value(connection),
                DuckDbParameter::TextList(values) => {
                    duckdb_neo::types::List(values.iter().cloned().map(Some).collect())
                        .value(connection)
                }
                DuckDbParameter::Date(value) => DateValue(value.to_epoch_days()).value(connection),
            })
            .collect::<duckdb_neo::Result<Vec<_>>>()?;
        let parameter_refs = values
            .iter()
            .map(|value| value as &dyn QueryParameter)
            .collect::<Vec<_>>();
        let mut result = if parameter_refs.is_empty() {
            connection.query(sql, Parameters::None)?
        } else {
            connection.query(sql, Parameters::positional(&parameter_refs))?
        };
        let schema = result.schema()?;
        let column_count = schema.len()?;
        let columns: std::sync::Arc<BTreeMap<String, usize>> = std::sync::Arc::new(
            (0..column_count)
                .map(|index| schema.name(index).map(str::to_owned))
                .collect::<duckdb_neo::Result<Vec<String>>>()?
                .into_iter()
                .enumerate()
                .map(|(index, name)| (name, index))
                .collect(),
        );
        while let Some(chunk) = result.next_chunk()? {
            let vectors = (0..column_count)
                .map(|column_index| chunk.get_vector_at::<Unknown>(column_index))
                .collect::<duckdb_neo::Result<Vec<_>>>()?;
            for row_index in 0..chunk.row_count()? {
                let values = vectors
                    .iter()
                    .map(|vector| vector.get_value_slow(row_index).map(DuckDbCell::Native))
                    .collect::<duckdb_neo::Result<Vec<_>>>()?;
                consume(map(DuckDbRow {
                    values,
                    columns: columns.clone(),
                })?)?;
            }
        }
        Ok(())
    }
}

/// Execute a parameterized read query for the Python training CLI.
pub fn query_json(
    source: &str,
    sql: &str,
    parameters: &[serde_json::Value],
) -> anyhow::Result<Vec<serde_json::Value>> {
    let parameters = parameters
        .iter()
        .map(|parameter| match parameter {
            serde_json::Value::String(value) => Ok(DuckDbParameter::Text(value.clone())),
            serde_json::Value::Array(values) => Ok(DuckDbParameter::TextList(
                values
                    .iter()
                    .map(|value| {
                        value.as_str().map(str::to_owned).ok_or_else(|| {
                            anyhow::anyhow!("query list parameters must contain strings")
                        })
                    })
                    .collect::<anyhow::Result<Vec<_>>>()?,
            )),
            _ => anyhow::bail!("query parameters must be strings or lists of strings"),
        })
        .collect::<anyhow::Result<Vec<_>>>()?;
    let sql =
        format!("SELECT CAST(to_json(result_row) AS VARCHAR) AS row_json FROM ({sql}) result_row");
    open_duckdb(source)?.query_map(&sql, &parameters, |row| {
        Ok(serde_json::from_str(&row.try_get::<String>("row_json")?)?)
    })
}

pub fn open_duckdb(source: &str) -> anyhow::Result<DuckDbConnection> {
    let token = crate::config::resolve_config_value(None, "QUACK_AUTH_TOKEN");
    let fingerprint = crate::config::resolve_config_value(None, "QUACK_SSL_FINGERPRINT");
    open_duckdb_with_auth(source, token.as_deref(), fingerprint.as_deref())
}

/// Open stock-cache read-only through duckdb-neo for both files and native Quack.
pub fn open_duckdb_with_auth(
    source: &str,
    token: Option<&str>,
    fingerprint: Option<&str>,
) -> anyhow::Result<DuckDbConnection> {
    let is_quack = matches!(DuckDbLocation::parse(source)?, DuckDbLocation::Quack(_));
    let environment = Environment::new()?;
    let instance = match DuckDbLocation::parse(source)? {
        DuckDbLocation::Memory => environment.open(StorageLocation::InMemory)?,
        DuckDbLocation::File(path) => {
            if !path.is_file() {
                anyhow::bail!("DuckDB database file does not exist: {}", path.display());
            }
            let path = path
                .to_str()
                .ok_or_else(|| anyhow::anyhow!("DuckDB path must be valid UTF-8"))?;
            let instance = Instance::new(&environment)?;
            instance.attach(
                AttachBuilder::new(StorageLocation::OnDisk(path.to_owned()))
                    .options([("read_only", "true")])
                    .make_default(),
            )?;
            instance
        }
        DuckDbLocation::Quack(_) => environment.open(StorageLocation::InMemory)?,
    };
    let connection = instance.connect()?;
    if let DuckDbLocation::Quack(uri) = DuckDbLocation::parse(source)? {
        let token = token
            .filter(|value| !value.is_empty())
            .ok_or_else(|| anyhow::anyhow!("QUACK_AUTH_TOKEN is required for Quack"))?;
        let uri = uri
            .strip_prefix("quack://")
            .map(|rest| format!("quack:{rest}"))
            .unwrap_or(uri);
        let literal = |value: &str| format!("'{}'", value.replace('\'', "''"));
        let mut options = vec![format!("TOKEN {}", literal(token)), "READ_ONLY".to_string()];
        if let Some(fingerprint) = fingerprint.filter(|value| !value.is_empty()) {
            options.push(format!("SSL_FINGERPRINT {}", literal(fingerprint)));
        }
        let sql = format!(
            "ATTACH {} AS market ({})",
            literal(&uri),
            options.join(", ")
        );
        connection.execute(sql, Parameters::None).map_err(|_| {
            anyhow::anyhow!(
                "failed to attach Quack server; check address, token and TLS fingerprint"
            )
        })?;
        connection.execute("USE market", Parameters::None)?;
    }
    Ok(DuckDbConnection {
        connection,
        is_quack,
    })
}

const DAILY_WINDOW_SESSION_SETTINGS_SQL: &str = "
    SET threads = 4;
    SET memory_limit = '1GB';
";

const DB_NATIVE_DAILY_WINDOW_QUERY: &str = "
        WITH query_params AS (
            SELECT $1::date AS start_date, $2::date AS end_date
        ),
        market_placeholder AS (
            SELECT 1
        )
        SELECT
            s.ts_code,
            s.trade_date,
            s.open::double precision AS open,
            s.high::double precision AS high,
            s.low::double precision AS low,
            s.close::double precision AS close,
            s.close_qfq::double precision AS _source_close_qfq,
            s.adj_factor::double precision AS adj_factor,
            s.vol::double precision AS vol,
            s.amount::double precision AS amount,
            s.turnover_rate::double precision AS turnover_rate,
            CASE WHEN c.ts_code IS NOT NULL THEN 1.0 ELSE 0.0 END::double precision AS _czsc_snapshot_available,
            CASE WHEN c.daily_source_bar_valid THEN 1.0 WHEN c.daily_source_bar_valid = false THEN 0.0 END::double precision AS _czsc_source_bar_valid,
            CASE c.daily_status
                WHEN 'invalid_source_bar' THEN 0.0
                WHEN 'no_finished_bi' THEN 1.0
                WHEN 'insufficient_bis_for_zs' THEN 2.0
                WHEN 'no_valid_zs' THEN 3.0
                WHEN 'ok' THEN 4.0
            END::double precision AS _czsc_status_code,
            c.daily_available_finished_bi_count::double precision AS _czsc_available_finished_bi_count,
            c.daily_recent_bi_count::double precision AS _czsc_recent_bi_count,
            CASE c.daily_last_bi_direction WHEN 'up' THEN 1.0 WHEN 'down' THEN -1.0 END::double precision AS _czsc_last_bi_direction_code,
            (c.daily_last_bi_start_date - DATE '1970-01-01')::double precision AS _czsc_last_bi_start_day,
            (c.daily_last_bi_end_date - DATE '1970-01-01')::double precision AS _czsc_last_bi_end_day,
            c.daily_last_bi_high::double precision AS _czsc_last_bi_high,
            c.daily_last_bi_low::double precision AS _czsc_last_bi_low,
            c.daily_last_bi_mid::double precision AS _czsc_last_bi_mid,
            (c.daily_latest_zs_start_date - DATE '1970-01-01')::double precision AS _czsc_latest_zs_start_day,
            (c.daily_latest_zs_end_date - DATE '1970-01-01')::double precision AS _czsc_latest_zs_end_day,
            c.daily_latest_zs_bi_count::double precision AS _czsc_latest_zs_bi_count,
            c.daily_latest_zs_zg::double precision AS _czsc_latest_zs_zg,
            c.daily_latest_zs_zd::double precision AS _czsc_latest_zs_zd,
            c.daily_latest_zs_zz::double precision AS _czsc_latest_zs_zz,
            (c.daily_recent_peak_date - DATE '1970-01-01')::double precision AS _czsc_recent_peak_day,
            c.daily_recent_peak_high::double precision AS _czsc_recent_peak_high,
            (c.daily_post_peak_first_bear_date - DATE '1970-01-01')::double precision AS _czsc_post_peak_first_bear_day,
            c.daily_post_peak_first_bear_open::double precision AS _czsc_post_peak_first_bear_open,
            c.daily_post_peak_first_bear_high::double precision AS _czsc_post_peak_first_bear_high,
            c.daily_post_peak_first_bear_low::double precision AS _czsc_post_peak_first_bear_low,
            c.daily_post_peak_first_bear_close::double precision AS _czsc_post_peak_first_bear_close,
            CASE WHEN c.daily_post_peak_first_bear_missing THEN 1.0 WHEN c.daily_post_peak_first_bear_missing = false THEN 0.0 END::double precision AS _czsc_post_peak_first_bear_missing
        FROM {{stock_stk_factor_pro}} s
        LEFT JOIN {{calc_daily_czsc_structure}} c
          ON c.ts_code = s.ts_code
         AND c.trade_date = s.trade_date
         AND c.source_dataset = 'stock_stk_factor_pro'
         AND c.calc_version = 'v3-macd-kdj-czsc-1'
        WHERE s.trade_date BETWEEN (SELECT start_date FROM query_params) AND (SELECT end_date FROM query_params)
        ";

const DB_NATIVE_PICK_DATE_EXTRAS_QUERY: &str = "
        WITH recent_trade_dates AS (
            SELECT trade_date
            FROM (
                SELECT DISTINCT trade_date
                FROM {{stock_stk_factor_pro}}
                WHERE trade_date <= $1
                ORDER BY trade_date DESC
                LIMIT 252
            ) d
        ),
        stock_moneyflow_recent AS (
            SELECT
                f.ts_code,
                max(f.net_mf_amount::double precision) FILTER (WHERE f.trade_date = $1) AS net_mf_amount,
                sum(f.net_mf_amount::double precision) FILTER (
                    WHERE f.trade_date >= (
                        SELECT min(trade_date)
                        FROM (SELECT trade_date FROM recent_trade_dates ORDER BY trade_date DESC LIMIT 5) recent5
                    )
                ) AS net_mf_d5_amount,
                max((f.buy_lg_amount - f.sell_lg_amount)::double precision) FILTER (WHERE f.trade_date = $1) AS buy_lg_amount,
                max((f.buy_md_amount - f.sell_md_amount)::double precision) FILTER (WHERE f.trade_date = $1) AS buy_md_amount,
                max((f.buy_sm_amount - f.sell_sm_amount)::double precision) FILTER (WHERE f.trade_date = $1) AS buy_sm_amount
            FROM {{stock_moneyflow}} f
            WHERE f.trade_date <= $1
              AND f.trade_date >= (SELECT min(trade_date) FROM recent_trade_dates)
            GROUP BY f.ts_code
        )
        SELECT
            s.ts_code,
            s.trade_date,
            -- czsc multiperiod begin
            c.daily_period_complete::double precision AS _czsc_period_complete,
            CASE WHEN c.ts_code IS NOT NULL THEN 1.0 ELSE 0.0 END::double precision AS _czsc_weekly_snapshot_available,
            c.weekly_period_complete::double precision AS _czsc_weekly_period_complete,
            CASE WHEN c.weekly_source_bar_valid THEN 1.0 WHEN c.weekly_source_bar_valid = false THEN 0.0 END::double precision AS _czsc_weekly_source_bar_valid,
            CASE c.weekly_status
                WHEN 'invalid_source_bar' THEN 0.0
                WHEN 'no_finished_bi' THEN 1.0
                WHEN 'insufficient_bis_for_zs' THEN 2.0
                WHEN 'no_valid_zs' THEN 3.0
                WHEN 'ok' THEN 4.0
            END::double precision AS _czsc_weekly_status_code,
            c.weekly_available_finished_bi_count::double precision AS _czsc_weekly_available_finished_bi_count,
            c.weekly_recent_bi_count::double precision AS _czsc_weekly_recent_bi_count,
            CASE c.weekly_last_bi_direction WHEN 'up' THEN 1.0 WHEN 'down' THEN -1.0 END::double precision AS _czsc_weekly_last_bi_direction_code,
            (c.weekly_last_bi_start_date - DATE '1970-01-01')::double precision AS _czsc_weekly_last_bi_start_day,
            (c.weekly_last_bi_end_date - DATE '1970-01-01')::double precision AS _czsc_weekly_last_bi_end_day,
            c.weekly_last_bi_high::double precision AS _czsc_weekly_last_bi_high,
            c.weekly_last_bi_low::double precision AS _czsc_weekly_last_bi_low,
            c.weekly_last_bi_mid::double precision AS _czsc_weekly_last_bi_mid,
            (c.weekly_latest_zs_start_date - DATE '1970-01-01')::double precision AS _czsc_weekly_latest_zs_start_day,
            (c.weekly_latest_zs_end_date - DATE '1970-01-01')::double precision AS _czsc_weekly_latest_zs_end_day,
            c.weekly_latest_zs_bi_count::double precision AS _czsc_weekly_latest_zs_bi_count,
            c.weekly_latest_zs_zg::double precision AS _czsc_weekly_latest_zs_zg,
            c.weekly_latest_zs_zd::double precision AS _czsc_weekly_latest_zs_zd,
            c.weekly_latest_zs_zz::double precision AS _czsc_weekly_latest_zs_zz,
            (c.weekly_recent_peak_date - DATE '1970-01-01')::double precision AS _czsc_weekly_recent_peak_day,
            c.weekly_recent_peak_high::double precision AS _czsc_weekly_recent_peak_high,
            (c.weekly_post_peak_first_bear_date - DATE '1970-01-01')::double precision AS _czsc_weekly_post_peak_first_bear_day,
            c.weekly_post_peak_first_bear_open::double precision AS _czsc_weekly_post_peak_first_bear_open,
            c.weekly_post_peak_first_bear_high::double precision AS _czsc_weekly_post_peak_first_bear_high,
            c.weekly_post_peak_first_bear_low::double precision AS _czsc_weekly_post_peak_first_bear_low,
            c.weekly_post_peak_first_bear_close::double precision AS _czsc_weekly_post_peak_first_bear_close,
            CASE WHEN c.weekly_post_peak_first_bear_missing THEN 1.0 WHEN c.weekly_post_peak_first_bear_missing = false THEN 0.0 END::double precision AS _czsc_weekly_post_peak_first_bear_missing,
            CASE WHEN c.ts_code IS NOT NULL THEN 1.0 ELSE 0.0 END::double precision AS _czsc_monthly_snapshot_available,
            c.monthly_period_complete::double precision AS _czsc_monthly_period_complete,
            CASE WHEN c.monthly_source_bar_valid THEN 1.0 WHEN c.monthly_source_bar_valid = false THEN 0.0 END::double precision AS _czsc_monthly_source_bar_valid,
            CASE c.monthly_status
                WHEN 'invalid_source_bar' THEN 0.0
                WHEN 'no_finished_bi' THEN 1.0
                WHEN 'insufficient_bis_for_zs' THEN 2.0
                WHEN 'no_valid_zs' THEN 3.0
                WHEN 'ok' THEN 4.0
            END::double precision AS _czsc_monthly_status_code,
            c.monthly_available_finished_bi_count::double precision AS _czsc_monthly_available_finished_bi_count,
            c.monthly_recent_bi_count::double precision AS _czsc_monthly_recent_bi_count,
            CASE c.monthly_last_bi_direction WHEN 'up' THEN 1.0 WHEN 'down' THEN -1.0 END::double precision AS _czsc_monthly_last_bi_direction_code,
            (c.monthly_last_bi_start_date - DATE '1970-01-01')::double precision AS _czsc_monthly_last_bi_start_day,
            (c.monthly_last_bi_end_date - DATE '1970-01-01')::double precision AS _czsc_monthly_last_bi_end_day,
            c.monthly_last_bi_high::double precision AS _czsc_monthly_last_bi_high,
            c.monthly_last_bi_low::double precision AS _czsc_monthly_last_bi_low,
            c.monthly_last_bi_mid::double precision AS _czsc_monthly_last_bi_mid,
            (c.monthly_latest_zs_start_date - DATE '1970-01-01')::double precision AS _czsc_monthly_latest_zs_start_day,
            (c.monthly_latest_zs_end_date - DATE '1970-01-01')::double precision AS _czsc_monthly_latest_zs_end_day,
            c.monthly_latest_zs_bi_count::double precision AS _czsc_monthly_latest_zs_bi_count,
            c.monthly_latest_zs_zg::double precision AS _czsc_monthly_latest_zs_zg,
            c.monthly_latest_zs_zd::double precision AS _czsc_monthly_latest_zs_zd,
            c.monthly_latest_zs_zz::double precision AS _czsc_monthly_latest_zs_zz,
            (c.monthly_recent_peak_date - DATE '1970-01-01')::double precision AS _czsc_monthly_recent_peak_day,
            c.monthly_recent_peak_high::double precision AS _czsc_monthly_recent_peak_high,
            (c.monthly_post_peak_first_bear_date - DATE '1970-01-01')::double precision AS _czsc_monthly_post_peak_first_bear_day,
            c.monthly_post_peak_first_bear_open::double precision AS _czsc_monthly_post_peak_first_bear_open,
            c.monthly_post_peak_first_bear_high::double precision AS _czsc_monthly_post_peak_first_bear_high,
            c.monthly_post_peak_first_bear_low::double precision AS _czsc_monthly_post_peak_first_bear_low,
            c.monthly_post_peak_first_bear_close::double precision AS _czsc_monthly_post_peak_first_bear_close,
            CASE WHEN c.monthly_post_peak_first_bear_missing THEN 1.0 WHEN c.monthly_post_peak_first_bear_missing = false THEN 0.0 END::double precision AS _czsc_monthly_post_peak_first_bear_missing,
            -- czsc multiperiod end
            -- stk_factor_pro begin
            s.close_qfq::double precision AS _stk_close_qfq,
            s.asi_qfq::double precision AS _stk_asi_qfq,
            s.asit_qfq::double precision AS _stk_asit_qfq,
            s.bias2_qfq::double precision AS _stk_bias2_qfq,
            s.bias3_qfq::double precision AS _stk_bias3_qfq,
            s.brar_ar_qfq::double precision AS _stk_brar_ar_qfq,
            s.brar_br_qfq::double precision AS _stk_brar_br_qfq,
            s.cci_qfq::double precision AS _stk_cci_qfq,
            s.cr_qfq::double precision AS _stk_cr_qfq,
            s.emv_qfq::double precision AS _stk_emv_qfq,
            s.maemv_qfq::double precision AS _stk_maemv_qfq,
            s.mass_qfq::double precision AS _stk_mass_qfq,
            s.ma_mass_qfq::double precision AS _stk_ma_mass_qfq,
            s.mfi_qfq::double precision AS _stk_mfi_qfq,
            s.psyma_qfq::double precision AS _stk_psyma_qfq,
            s.maroc_qfq::double precision AS _stk_maroc_qfq,
            s.trma_qfq::double precision AS _stk_trma_qfq,
            s.wr1_qfq::double precision AS _stk_wr1_qfq,
            s.updays::double precision AS _stk_updays,
            s.downdays::double precision AS _stk_downdays,
            s.lowdays::double precision AS _stk_lowdays,
            s.topdays::double precision AS _stk_topdays,
            s.dv_ttm::double precision AS _stk_dv_ttm,
            s.turnover_rate::double precision AS _stk_turnover_rate,
            s.volume_ratio::double precision AS _stk_volume_ratio,
            s.float_share::double precision AS _stk_float_share,
            s.bbi_qfq::double precision AS _stk_bbi_qfq,
            s.ma_qfq_5::double precision AS _stk_ma_qfq_5,
            s.ma_qfq_10::double precision AS _stk_ma_qfq_10,
            s.ma_qfq_20::double precision AS _stk_ma_qfq_20,
            s.ma_qfq_30::double precision AS _stk_ma_qfq_30,
            s.ma_qfq_60::double precision AS _stk_ma_qfq_60,
            s.ma_qfq_90::double precision AS _stk_ma_qfq_90,
            s.ma_qfq_250::double precision AS _stk_ma_qfq_250,
            s.ema_qfq_5::double precision AS _stk_ema_qfq_5,
            s.ema_qfq_10::double precision AS _stk_ema_qfq_10,
            s.ema_qfq_20::double precision AS _stk_ema_qfq_20,
            s.ema_qfq_30::double precision AS _stk_ema_qfq_30,
            s.ema_qfq_60::double precision AS _stk_ema_qfq_60,
            s.ema_qfq_90::double precision AS _stk_ema_qfq_90,
            s.ema_qfq_250::double precision AS _stk_ema_qfq_250,
            s.expma_12_qfq::double precision AS _stk_expma_12_qfq,
            s.expma_50_qfq::double precision AS _stk_expma_50_qfq,
            s.boll_upper_qfq::double precision AS _stk_boll_upper_qfq,
            s.boll_mid_qfq::double precision AS _stk_boll_mid_qfq,
            s.boll_lower_qfq::double precision AS _stk_boll_lower_qfq,
            s.ktn_upper_qfq::double precision AS _stk_ktn_upper_qfq,
            s.ktn_mid_qfq::double precision AS _stk_ktn_mid_qfq,
            s.ktn_down_qfq::double precision AS _stk_ktn_down_qfq,
            s.taq_up_qfq::double precision AS _stk_taq_up_qfq,
            s.taq_mid_qfq::double precision AS _stk_taq_mid_qfq,
            s.taq_down_qfq::double precision AS _stk_taq_down_qfq,
            s.xsii_td1_qfq::double precision AS _stk_xsii_td1_qfq,
            s.xsii_td2_qfq::double precision AS _stk_xsii_td2_qfq,
            s.xsii_td3_qfq::double precision AS _stk_xsii_td3_qfq,
            s.xsii_td4_qfq::double precision AS _stk_xsii_td4_qfq,
            s.atr_qfq::double precision AS _stk_atr_qfq,
            s.dfma_dif_qfq::double precision AS _stk_dfma_dif_qfq,
            s.dfma_difma_qfq::double precision AS _stk_dfma_difma_qfq,
            s.dpo_qfq::double precision AS _stk_dpo_qfq,
            s.madpo_qfq::double precision AS _stk_madpo_qfq,
            s.mtmma_qfq::double precision AS _stk_mtmma_qfq,
            s.free_share::double precision AS _stk_free_share,
            -- stk_factor_pro end
            s.amount::double precision AS amount,
            s.turnover_rate_f::double precision AS turnover_rate_f,
            s.volume_ratio::double precision AS volume_ratio,
            s.kdj_k_qfq::double precision AS kdj_k_qfq,
            s.kdj_d_qfq::double precision AS kdj_d_qfq,
            CASE
                WHEN s.kdj_k_qfq IS NOT NULL AND s.kdj_d_qfq IS NOT NULL
                THEN 3.0 * s.kdj_k_qfq::double precision - 2.0 * s.kdj_d_qfq::double precision
            END AS kdj_j_qfq,
            s.rsi_qfq_6::double precision AS rsi_qfq_6,
            s.rsi_qfq_12::double precision AS rsi_qfq_12,
            s.rsi_qfq_24::double precision AS rsi_qfq_24,
            s.boll_upper_qfq::double precision AS boll_upper_qfq,
            s.boll_mid_qfq::double precision AS boll_mid_qfq,
            s.boll_lower_qfq::double precision AS boll_lower_qfq,
            s.dmi_adxr_qfq::double precision AS dmi_adxr_qfq,
            s.dmi_adx_qfq::double precision AS dmi_adx_qfq,
            s.dmi_pdi_qfq::double precision AS dmi_pdi_qfq,
            s.dmi_mdi_qfq::double precision AS dmi_mdi_qfq,
            s.dmi_pdi_qfq::double precision - s.dmi_mdi_qfq::double precision AS dmi_pdi_mdi_spread_qfq,
            s.dmi_adx_qfq::double precision - s.dmi_adxr_qfq::double precision AS dmi_adx_adxr_gap_qfq,
            s.wr_qfq::double precision AS wr_qfq,
            s.mtm_qfq::double precision AS mtm_qfq,
            s.roc_qfq::double precision AS roc_qfq,
            s.trix_qfq::double precision AS trix_qfq,
            s.obv_qfq::double precision AS obv_qfq,
            s.vr_qfq::double precision AS vr_qfq,
            s.psy_qfq::double precision AS psy_qfq,
            s.bias1_qfq::double precision AS bias1_qfq,
            s.macd_dif_qfq::double precision AS tushare_macd_dif_qfq,
            s.macd_dea_qfq::double precision AS tushare_macd_dea_qfq,
            s.macd_qfq::double precision AS tushare_macd_qfq,
            s.pe::double precision AS pe,
            s.pe_ttm::double precision AS pe_ttm,
            s.pb::double precision AS pb,
            s.ps::double precision AS ps,
            s.ps_ttm::double precision AS ps_ttm,
            s.dv_ratio::double precision AS dv_ratio,
            s.total_mv::double precision AS total_mv,
            s.circ_mv::double precision AS circ_mv,
            s.total_share::double precision AS total_share,
            s.free_share::double precision AS free_share,
            a.daily_macd_dif_asof::double precision AS macd_daily_dif,
            a.daily_macd_dea_asof::double precision AS macd_daily_dea,
            a.daily_macd_hist_x2_asof::double precision / 2.0 AS macd_daily_hist,
            a.daily_macd_dea_pctile_asof::double precision AS macd_daily_dea_pctile,
            a.daily_macd_period_count::double precision AS macd_daily_period_count,
            a.weekly_macd_dif_asof::double precision AS macd_weekly_dif,
            a.weekly_macd_dea_asof::double precision AS macd_weekly_dea,
            a.weekly_macd_hist_x2_asof::double precision / 2.0 AS macd_weekly_hist,
            a.weekly_macd_dea_pctile_asof::double precision AS macd_weekly_dea_pctile,
            a.weekly_macd_period_count::double precision AS macd_weekly_period_count,
            a.monthly_macd_dif_asof::double precision AS macd_monthly_dif,
            a.monthly_macd_dea_asof::double precision AS macd_monthly_dea,
            a.monthly_macd_hist_x2_asof::double precision / 2.0 AS macd_monthly_hist,
            a.monthly_macd_dea_pctile_asof::double precision AS macd_monthly_dea_pctile,
            a.monthly_macd_period_count::double precision AS macd_monthly_period_count,
            a.weekly_kdj_k_asof::double precision AS kdj_weekly_k,
            a.weekly_kdj_d_asof::double precision AS kdj_weekly_d,
            a.weekly_kdj_j_asof::double precision AS kdj_weekly_j,
            a.monthly_kdj_k_asof::double precision AS kdj_monthly_k,
            a.monthly_kdj_d_asof::double precision AS kdj_monthly_d,
            a.monthly_kdj_j_asof::double precision AS kdj_monthly_j,
            r.ma25_qfq::double precision AS rolling_ma25_qfq,
            r.ma144_qfq::double precision AS rolling_ma144_qfq,
            r.ma220_qfq::double precision AS rolling_ma220_qfq,
            r.high_20_qfq::double precision AS rolling_high_20_qfq,
            r.close_to_20d_max_close_pct::double precision AS close_to_20d_max_close_pct,
            r.high_90_qfq::double precision AS rolling_high_90_qfq,
            r.low_90_qfq::double precision AS rolling_low_90_qfq,
            r.high_120_qfq::double precision AS rolling_high_120_qfq,
            r.low_120_qfq::double precision AS rolling_low_120_qfq,
            r.position_90d::double precision AS rolling_position_90d,
            r.position_120d::double precision AS rolling_position_120d,
            r.volume_ma5::double precision AS rolling_volume_ma5,
            r.volume_ma20::double precision AS rolling_volume_ma20,
            r.volume_to_ma5_ratio::double precision AS rolling_volume_to_ma5_ratio,
            r.volume_to_ma20_ratio::double precision AS rolling_volume_to_ma20_ratio,
            r.volume_ma5_to_ma20_ratio::double precision AS rolling_volume_ma5_to_ma20_ratio,
            r.turnover_rate_ma5::double precision AS rolling_turnover_rate_ma5,
            r.turnover_to_ma5_ratio::double precision AS rolling_turnover_to_ma5_ratio,
            r.range_compression_20d::double precision AS rolling_range_compression_20d,
            r.range_compression_40d::double precision AS rolling_range_compression_40d,
            smf.net_mf_amount AS stock_mf_net_amount,
            smf.net_mf_d5_amount AS stock_mf_net_d5_amount,
            smf.buy_lg_amount AS stock_mf_buy_lg_amount,
            CASE WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.buy_lg_amount IS NOT NULL
                 THEN smf.buy_lg_amount / (s.amount / 10.0) * 100.0 END AS stock_mf_buy_lg_amount_rate,
            smf.buy_md_amount AS stock_mf_buy_md_amount,
            CASE WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.buy_md_amount IS NOT NULL
                 THEN smf.buy_md_amount / (s.amount / 10.0) * 100.0 END AS stock_mf_buy_md_amount_rate,
            smf.buy_sm_amount AS stock_mf_buy_sm_amount,
            CASE WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.buy_sm_amount IS NOT NULL
                 THEN smf.buy_sm_amount / (s.amount / 10.0) * 100.0 END AS stock_mf_buy_sm_amount_rate,
            CASE
                WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.buy_lg_amount IS NOT NULL
                THEN smf.buy_lg_amount / (s.amount / 10.0) * 100.0
            END AS large_net_amount_to_amount_pct,
            CASE
                WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.buy_md_amount IS NOT NULL
                THEN smf.buy_md_amount / (s.amount / 10.0) * 100.0
            END AS mid_net_amount_to_amount_pct,
            CASE
                WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.buy_sm_amount IS NOT NULL
                THEN smf.buy_sm_amount / (s.amount / 10.0) * 100.0
            END AS small_net_amount_to_amount_pct,
            CASE
                WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.net_mf_amount IS NOT NULL
                THEN smf.net_mf_amount / (s.amount / 10.0) * 100.0
            END AS net_mf_amount_to_amount_pct
        FROM {{stock_stk_factor_pro}} s
        LEFT JOIN {{calc_daily_indicators}} a
          ON a.ts_code = s.ts_code
         AND a.trade_date = s.trade_date
         AND a.source_dataset = 'stock_stk_factor_pro'
         AND a.calc_version = 'v3-macd-kdj-czsc-1'
        LEFT JOIN {{calc_daily_rolling_factors}} r
          ON r.ts_code = s.ts_code
         AND r.trade_date = s.trade_date
         AND r.source_dataset = 'stock_stk_factor_pro'
         AND r.calc_version = 'v3-macd-kdj-czsc-1'
        LEFT JOIN {{calc_daily_czsc_structure}} c
          ON c.ts_code = s.ts_code
         AND c.trade_date = s.trade_date
         AND c.source_dataset = 'stock_stk_factor_pro'
         AND c.calc_version = 'v3-macd-kdj-czsc-1'
        LEFT JOIN stock_moneyflow_recent smf
          ON smf.ts_code = s.ts_code
        WHERE s.trade_date = $1
        ";

const DB_NATIVE_PREVIOUS_MONTH_MACD_QUERY: &str = "
        SELECT DISTINCT ON (a.ts_code)
            a.ts_code,
            a.trade_date,
            a.monthly_macd_hist_x2_asof::double precision / 2.0 AS macd_monthly_hist
        FROM {{calc_daily_indicators}} a
        WHERE a.trade_date >= (date_trunc('month', $1::date) - INTERVAL '1 month')::date
          AND a.trade_date < date_trunc('month', $1::date)::date
          AND a.source_dataset = 'stock_stk_factor_pro'
          AND a.calc_version = 'v3-macd-kdj-czsc-1'
        ORDER BY a.ts_code, a.trade_date DESC
        ";

const DB_NATIVE_SW_L2_EXTRAS_QUERY: &str = "
        WITH sample_stocks AS (
            SELECT DISTINCT
                ts_code,
                trade_date,
                pct_chg::double precision AS stock_pct_change
            FROM {{stock_stk_factor_pro}}
            WHERE trade_date = $1
        ),
        benchmark_definitions AS (
            SELECT * FROM (VALUES
                ('000016.SH', 'sse50'),
                ('000905.SH', 'csi500'),
                ('000688.SH', 'sci50'),
                ('930050.CSI', 'csi_a50'),
                ('000922.CSI', 'csi_dividend'),
                ('000300.SH', 'csi300'),
                ('399303.SZ', 'guozheng2000'),
                ('399006.SZ', 'chinext'),
                ('899050.BJ', 'bse50')
            ) AS definitions(index_code, context_alias)
        ),
        latest_weight_dates AS (
            SELECT
                w.index_code,
                max(w.trade_date) AS snapshot_date
            FROM {{index_weight}} w
            JOIN benchmark_definitions d
              ON d.index_code = w.index_code
            WHERE w.trade_date <= $1
            GROUP BY w.index_code
        ),
        weights_asof AS (
            SELECT
                w.index_code,
                w.con_code,
                max(w.weight)::double precision AS weight_pct
            FROM {{index_weight}} w
            JOIN latest_weight_dates d
              ON d.index_code = w.index_code
             AND d.snapshot_date = w.trade_date
            GROUP BY w.index_code, w.con_code
        ),
        market_context AS (
            SELECT
                s.ts_code,
                s.trade_date,
                'market'::text AS context_type,
                d.context_alias,
                CASE WHEN w.con_code IS NOT NULL THEN 1.0 ELSE 0.0 END::double precision AS member_flag,
                CASE WHEN w.con_code IS NOT NULL THEN coalesce(w.weight_pct, 0.0) ELSE 0.0 END::double precision AS weight_pct,
                coalesce(to_json(i), '{}')::text AS index_payload,
                coalesce(to_json(a), '{}')::text AS indicators_payload,
                coalesce(to_json(r), '{}')::text AS rolling_payload,
                coalesce(to_json(c), '{}')::text AS czsc_payload,
                '{}'::text AS moneyflow_payload,
                NULL::double precision AS industry_pct_change,
                NULL::double precision AS industry_net_amount,
                NULL::double precision AS stock_vs_industry_pct_change
            FROM sample_stocks s
            CROSS JOIN benchmark_definitions d
            LEFT JOIN weights_asof w
              ON w.index_code = d.index_code
             AND w.con_code = s.ts_code
            LEFT JOIN {{index_idx_factor_pro}} i
              ON i.ts_code = d.index_code
             AND i.trade_date = s.trade_date
            LEFT JOIN {{calc_daily_indicators}} a
              ON a.ts_code = d.index_code
             AND a.trade_date = s.trade_date
             AND a.source_dataset = 'index_idx_factor_pro'
             AND a.calc_version = 'v3-macd-kdj-czsc-1'
            LEFT JOIN {{calc_daily_rolling_factors}} r
              ON r.ts_code = d.index_code
             AND r.trade_date = s.trade_date
             AND r.source_dataset = 'index_idx_factor_pro'
             AND r.calc_version = 'v3-macd-kdj-czsc-1'
            LEFT JOIN {{calc_daily_czsc_structure}} c
              ON c.ts_code = d.index_code
             AND c.trade_date = s.trade_date
             AND c.source_dataset = 'index_idx_factor_pro'
             AND c.calc_version = 'v3-macd-kdj-czsc-1'
        ),
        sw_membership_candidates AS (
            SELECT
                s.ts_code,
                s.trade_date,
                s.stock_pct_change,
                m.l2_code AS industry_code,
                row_number() OVER (
                    PARTITION BY s.ts_code
                    ORDER BY m.in_date DESC NULLS LAST, m.l2_code ASC NULLS LAST
                ) AS member_rank
            FROM sample_stocks s
            LEFT JOIN {{index_sw_member}} m
              ON m.ts_code = s.ts_code
             AND m.l2_code IS NOT NULL
             AND s.trade_date >= m.in_date
             AND (m.out_date IS NULL OR s.trade_date < m.out_date)
        ),
        sw_membership AS (
            SELECT *
            FROM sw_membership_candidates
            WHERE member_rank = 1
        ),
        industry_context AS (
            SELECT
                s.ts_code,
                s.trade_date,
                'industry'::text AS context_type,
                'sw_l2_main'::text AS context_alias,
                CASE WHEN m.industry_code IS NOT NULL THEN 1.0 ELSE 0.0 END::double precision AS member_flag,
                0.0::double precision AS weight_pct,
                coalesce(to_json(i), '{}')::text AS index_payload,
                coalesce(to_json(a), '{}')::text AS indicators_payload,
                coalesce(to_json(r), '{}')::text AS rolling_payload,
                coalesce(to_json(c), '{}')::text AS czsc_payload,
                coalesce(to_json(mf), '{}')::text AS moneyflow_payload,
                i.pct_change::double precision AS industry_pct_change,
                mf.main_net_amount::double precision AS industry_net_amount,
                CASE
                    WHEN m.industry_code IS NOT NULL
                     AND s.stock_pct_change IS NOT NULL
                     AND i.pct_change IS NOT NULL
                    THEN s.stock_pct_change - i.pct_change
                END::double precision AS stock_vs_industry_pct_change
            FROM sw_membership m
            JOIN sample_stocks s
              ON s.ts_code = m.ts_code
             AND s.trade_date = m.trade_date
            LEFT JOIN {{index_idx_factor_pro}} i
              ON i.ts_code = m.industry_code
             AND i.trade_date = s.trade_date
            LEFT JOIN {{calc_daily_indicators}} a
              ON a.ts_code = m.industry_code
             AND a.trade_date = s.trade_date
             AND a.source_dataset = 'index_idx_factor_pro'
             AND a.calc_version = 'v3-macd-kdj-czsc-1'
            LEFT JOIN {{calc_daily_rolling_factors}} r
              ON r.ts_code = m.industry_code
             AND r.trade_date = s.trade_date
             AND r.source_dataset = 'index_idx_factor_pro'
             AND r.calc_version = 'v3-macd-kdj-czsc-1'
            LEFT JOIN {{calc_daily_czsc_structure}} c
              ON c.ts_code = m.industry_code
             AND c.trade_date = s.trade_date
             AND c.source_dataset = 'index_idx_factor_pro'
             AND c.calc_version = 'v3-macd-kdj-czsc-1'
            LEFT JOIN {{calc_daily_industry_moneyflow}} mf
              ON mf.industry_code = m.industry_code
             AND mf.trade_date = s.trade_date
             AND mf.source_dataset = 'stock_moneyflow'
             AND mf.calc_version = 'sw2021-l2-v1'
        )
        SELECT * FROM market_context
        UNION ALL
        SELECT * FROM industry_context
        ORDER BY ts_code, trade_date, context_type, context_alias
        ";

const PREVIOUS_TRADE_DATE_QUERY: &str = "
        SELECT max(trade_date) AS trade_date
        FROM stock_stk_factor_pro
        WHERE trade_date < $1
        ";

const STOCK_PERIOD_MACD_STATE_QUERY: &str = "
        SELECT DISTINCT ON (p.ts_code, p.period_type)
            p.ts_code,
            p.period_type,
            p.macd_ema12::double precision AS ema12,
            p.macd_ema26::double precision AS ema26,
            p.macd_dea::double precision AS dea,
            p.macd_period_count::integer AS period_count
        FROM calc_indicator_state p
        WHERE p.source_dataset = 'stock_stk_factor_pro'
          AND p.ts_code = ANY($1)
          AND (
              (p.period_type = 'daily' AND p.period_end_date < $2)
              OR (p.period_type = 'weekly' AND p.period_end_date < date_trunc('week', $2::date)::date)
              OR (p.period_type = 'monthly' AND p.period_end_date < date_trunc('month', $2::date)::date)
          )
          AND p.calc_version = 'v3-macd-kdj-czsc-1'
          AND p.macd_period_count IS NOT NULL
        ORDER BY p.ts_code, p.period_type, p.period_end_date DESC
        ";

const STOCK_BASIC_INFO_QUERY: &str = "
        WITH requested AS (
            SELECT unnest($1::text[]) AS ts_code
        )
        SELECT
            r.ts_code,
            NULLIF(trim(s.name), '') AS name
        FROM requested r
        LEFT JOIN stock_basic s ON s.ts_code = r.ts_code
        ORDER BY r.ts_code ASC
        ";

const SW_L2_INDUSTRY_QUERY: &str = "
        WITH requested AS (
            SELECT unnest($1::text[]) AS ts_code
        )
        SELECT DISTINCT ON (r.ts_code)
            r.ts_code,
            m.l2_name AS industry
        FROM requested r
        JOIN index_sw_member m ON m.ts_code = r.ts_code
        WHERE m.in_date <= CURRENT_DATE
          AND (m.out_date IS NULL OR CURRENT_DATE < m.out_date)
          AND NULLIF(trim(m.l2_name), '') IS NOT NULL
        ORDER BY r.ts_code, m.in_date DESC NULLS LAST
        ";

#[derive(Debug, Clone, PartialEq)]
struct DbNativeDailyRow {
    ts_code: String,
    trade_date: NaiveDate,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    adj_factor: Option<f64>,
    vol: f64,
    turnover_rate: Option<f64>,
    db_factors: BTreeMap<String, Option<f64>>,
}

pub(crate) const DB_NATIVE_FACTOR_COLUMNS: &[&str] = &[
    "_source_close_qfq",
    "amount",
    "_czsc_snapshot_available",
    "_czsc_source_bar_valid",
    "_czsc_status_code",
    "_czsc_available_finished_bi_count",
    "_czsc_recent_bi_count",
    "_czsc_last_bi_direction_code",
    "_czsc_last_bi_start_day",
    "_czsc_last_bi_end_day",
    "_czsc_last_bi_high",
    "_czsc_last_bi_low",
    "_czsc_last_bi_mid",
    "_czsc_latest_zs_start_day",
    "_czsc_latest_zs_end_day",
    "_czsc_latest_zs_bi_count",
    "_czsc_latest_zs_zg",
    "_czsc_latest_zs_zd",
    "_czsc_latest_zs_zz",
    "_czsc_recent_peak_day",
    "_czsc_recent_peak_high",
    "_czsc_post_peak_first_bear_day",
    "_czsc_post_peak_first_bear_open",
    "_czsc_post_peak_first_bear_high",
    "_czsc_post_peak_first_bear_low",
    "_czsc_post_peak_first_bear_close",
    "_czsc_post_peak_first_bear_missing",
];

pub(crate) const DB_NATIVE_PICK_DATE_FACTOR_COLUMNS: &[&str] = &[
    "_czsc_period_complete",
    "_czsc_weekly_snapshot_available",
    "_czsc_weekly_period_complete",
    "_czsc_weekly_source_bar_valid",
    "_czsc_weekly_status_code",
    "_czsc_weekly_available_finished_bi_count",
    "_czsc_weekly_recent_bi_count",
    "_czsc_weekly_last_bi_direction_code",
    "_czsc_weekly_last_bi_start_day",
    "_czsc_weekly_last_bi_end_day",
    "_czsc_weekly_last_bi_high",
    "_czsc_weekly_last_bi_low",
    "_czsc_weekly_last_bi_mid",
    "_czsc_weekly_latest_zs_start_day",
    "_czsc_weekly_latest_zs_end_day",
    "_czsc_weekly_latest_zs_bi_count",
    "_czsc_weekly_latest_zs_zg",
    "_czsc_weekly_latest_zs_zd",
    "_czsc_weekly_latest_zs_zz",
    "_czsc_weekly_recent_peak_day",
    "_czsc_weekly_recent_peak_high",
    "_czsc_weekly_post_peak_first_bear_day",
    "_czsc_weekly_post_peak_first_bear_open",
    "_czsc_weekly_post_peak_first_bear_high",
    "_czsc_weekly_post_peak_first_bear_low",
    "_czsc_weekly_post_peak_first_bear_close",
    "_czsc_weekly_post_peak_first_bear_missing",
    "_czsc_monthly_snapshot_available",
    "_czsc_monthly_period_complete",
    "_czsc_monthly_source_bar_valid",
    "_czsc_monthly_status_code",
    "_czsc_monthly_available_finished_bi_count",
    "_czsc_monthly_recent_bi_count",
    "_czsc_monthly_last_bi_direction_code",
    "_czsc_monthly_last_bi_start_day",
    "_czsc_monthly_last_bi_end_day",
    "_czsc_monthly_last_bi_high",
    "_czsc_monthly_last_bi_low",
    "_czsc_monthly_last_bi_mid",
    "_czsc_monthly_latest_zs_start_day",
    "_czsc_monthly_latest_zs_end_day",
    "_czsc_monthly_latest_zs_bi_count",
    "_czsc_monthly_latest_zs_zg",
    "_czsc_monthly_latest_zs_zd",
    "_czsc_monthly_latest_zs_zz",
    "_czsc_monthly_recent_peak_day",
    "_czsc_monthly_recent_peak_high",
    "_czsc_monthly_post_peak_first_bear_day",
    "_czsc_monthly_post_peak_first_bear_open",
    "_czsc_monthly_post_peak_first_bear_high",
    "_czsc_monthly_post_peak_first_bear_low",
    "_czsc_monthly_post_peak_first_bear_close",
    "_czsc_monthly_post_peak_first_bear_missing",
    "kdj_weekly_k",
    "kdj_weekly_d",
    "kdj_weekly_j",
    "kdj_monthly_k",
    "kdj_monthly_d",
    "kdj_monthly_j",
    "amount",
    "turnover_rate_f",
    "volume_ratio",
    "kdj_k_qfq",
    "kdj_d_qfq",
    "kdj_j_qfq",
    "rsi_qfq_6",
    "rsi_qfq_12",
    "rsi_qfq_24",
    "boll_upper_qfq",
    "boll_mid_qfq",
    "boll_lower_qfq",
    "dmi_adxr_qfq",
    "dmi_adx_qfq",
    "dmi_pdi_qfq",
    "dmi_mdi_qfq",
    "dmi_pdi_mdi_spread_qfq",
    "dmi_adx_adxr_gap_qfq",
    "wr_qfq",
    "mtm_qfq",
    "roc_qfq",
    "trix_qfq",
    "obv_qfq",
    "vr_qfq",
    "psy_qfq",
    "bias1_qfq",
    "tushare_macd_dif_qfq",
    "tushare_macd_dea_qfq",
    "tushare_macd_qfq",
    "pe",
    "pe_ttm",
    "pb",
    "ps",
    "ps_ttm",
    "dv_ratio",
    "total_mv",
    "circ_mv",
    "total_share",
    "free_share",
    "macd_daily_dif",
    "macd_daily_dea",
    "macd_daily_hist",
    "macd_daily_dea_pctile",
    "macd_daily_period_count",
    "macd_weekly_dif",
    "macd_weekly_dea",
    "macd_weekly_hist",
    "macd_weekly_dea_pctile",
    "macd_weekly_period_count",
    "macd_monthly_dif",
    "macd_monthly_dea",
    "macd_monthly_hist",
    "macd_monthly_dea_pctile",
    "macd_monthly_period_count",
    "rolling_ma25_qfq",
    "rolling_ma144_qfq",
    "rolling_ma220_qfq",
    "rolling_high_20_qfq",
    "close_to_20d_max_close_pct",
    "rolling_high_90_qfq",
    "rolling_low_90_qfq",
    "rolling_high_120_qfq",
    "rolling_low_120_qfq",
    "rolling_position_90d",
    "rolling_position_120d",
    "rolling_volume_ma5",
    "rolling_volume_ma20",
    "rolling_volume_to_ma5_ratio",
    "rolling_volume_to_ma20_ratio",
    "rolling_volume_ma5_to_ma20_ratio",
    "rolling_turnover_rate_ma5",
    "rolling_turnover_to_ma5_ratio",
    "rolling_range_compression_20d",
    "rolling_range_compression_40d",
    "stock_mf_net_amount",
    "stock_mf_net_d5_amount",
    "stock_mf_buy_lg_amount",
    "stock_mf_buy_lg_amount_rate",
    "stock_mf_buy_md_amount",
    "stock_mf_buy_md_amount_rate",
    "stock_mf_buy_sm_amount",
    "stock_mf_buy_sm_amount_rate",
    "large_net_amount_to_amount_pct",
    "mid_net_amount_to_amount_pct",
    "small_net_amount_to_amount_pct",
    "net_mf_amount_to_amount_pct",
];

pub(crate) fn db_native_pick_date_factor_columns() -> Vec<String> {
    DB_NATIVE_PICK_DATE_FACTOR_COLUMNS
        .iter()
        .map(|column| (*column).to_string())
        .chain(SOURCE_COLUMNS.iter().map(|column| format!("_stk_{column}")))
        .collect()
}

pub(crate) const DB_NATIVE_SW_L2_FACTOR_COLUMNS: &[&str] = &[
    "sw_l2_membership_current_flag",
    "sw_l2_main_pct_change",
    "sw_l2_main_net_amount_per_stock",
    "stock_vs_sw_l2_main_pct_change",
];

const INDEX_BENCHMARKS: [(&str, &str); 9] = [
    ("000016.SH", "sse50"),
    ("000905.SH", "csi500"),
    ("000688.SH", "sci50"),
    ("930050.CSI", "csi_a50"),
    ("000922.CSI", "csi_dividend"),
    ("000300.SH", "csi300"),
    ("399303.SZ", "guozheng2000"),
    ("399006.SZ", "chinext"),
    ("899050.BJ", "bse50"),
];

const INDEX_FACTOR_SOURCES: [(&str, &str); 4] = [
    ("idx", "index_idx_factor_pro"),
    ("calc_daily_indicators", "calc_daily_indicators"),
    ("calc_daily_rolling_factors", "calc_daily_rolling_factors"),
    ("calc_daily_czsc_structure", "calc_daily_czsc_structure"),
];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ContextFactorTransform {
    Raw,
    ToClosePct,
    PerStock,
    StatusCode,
    DirectionCode,
    AgeCalendarDays,
}

#[derive(Debug, Clone, Copy)]
struct ContextFactorPolicy {
    transform: ContextFactorTransform,
    weighted: bool,
}

fn context_factor_policy(source: &str, field: &str) -> Option<ContextFactorPolicy> {
    let policy = |transform, weighted| {
        Some(ContextFactorPolicy {
            transform,
            weighted,
        })
    };
    match source {
        "idx" => {
            if field == "pct_change" {
                return policy(ContextFactorTransform::Raw, true);
            }
            if matches!(
                field,
                "emv_bfq"
                    | "maemv_bfq"
                    | "obv_bfq"
                    | "bias1_bfq"
                    | "bias2_bfq"
                    | "bias3_bfq"
                    | "brar_ar_bfq"
                    | "brar_br_bfq"
                    | "cci_bfq"
                    | "cr_bfq"
                    | "dmi_adx_bfq"
                    | "dmi_adxr_bfq"
                    | "dmi_mdi_bfq"
                    | "dmi_pdi_bfq"
                    | "downdays"
                    | "updays"
                    | "lowdays"
                    | "topdays"
                    | "kdj_bfq"
                    | "kdj_d_bfq"
                    | "kdj_k_bfq"
                    | "mass_bfq"
                    | "ma_mass_bfq"
                    | "mfi_bfq"
                    | "psy_bfq"
                    | "psyma_bfq"
                    | "roc_bfq"
                    | "maroc_bfq"
                    | "rsi_bfq_6"
                    | "rsi_bfq_12"
                    | "rsi_bfq_24"
                    | "trix_bfq"
                    | "vr_bfq"
                    | "wr_bfq"
                    | "wr1_bfq"
            ) {
                return policy(ContextFactorTransform::Raw, false);
            }
            if matches!(
                field,
                "asi_bfq"
                    | "asit_bfq"
                    | "atr_bfq"
                    | "bbi_bfq"
                    | "dfma_dif_bfq"
                    | "dfma_difma_bfq"
                    | "dpo_bfq"
                    | "madpo_bfq"
                    | "macd_bfq"
                    | "macd_dea_bfq"
                    | "macd_dif_bfq"
                    | "mtm_bfq"
                    | "mtmma_bfq"
                    | "trma_bfq"
                    | "xsii_td1_bfq"
                    | "xsii_td2_bfq"
                    | "xsii_td3_bfq"
                    | "xsii_td4_bfq"
            ) || field.starts_with("boll_")
                || field.starts_with("ema_bfq_")
                || field.starts_with("expma_")
                || field.starts_with("ktn_")
                || field.starts_with("ma_bfq_")
                || field.starts_with("taq_")
            {
                return policy(ContextFactorTransform::ToClosePct, field == "macd_bfq");
            }
            None
        }
        "calc_daily_indicators" => {
            if field.ends_with("_macd_period_count")
                || field.ends_with("_dea_pctile_asof")
                || field.starts_with("weekly_kdj_")
                || field.starts_with("monthly_kdj_")
            {
                return policy(ContextFactorTransform::Raw, false);
            }
            if field.ends_with("_macd_dif_asof")
                || field.ends_with("_macd_dea_asof")
                || field.ends_with("_macd_hist_x2_asof")
            {
                return policy(
                    ContextFactorTransform::ToClosePct,
                    field == "daily_macd_hist_x2_asof",
                );
            }
            None
        }
        "calc_daily_rolling_factors" => {
            if matches!(
                field,
                "ma25_qfq"
                    | "ma144_qfq"
                    | "ma220_qfq"
                    | "high_20_qfq"
                    | "high_90_qfq"
                    | "low_90_qfq"
                    | "high_120_qfq"
                    | "low_120_qfq"
            ) {
                return policy(ContextFactorTransform::ToClosePct, false);
            }
            if matches!(
                field,
                "close_to_20d_max_close_pct"
                    | "position_90d"
                    | "position_120d"
                    | "volume_to_ma5_ratio"
                    | "volume_to_ma20_ratio"
                    | "volume_ma5_to_ma20_ratio"
                    | "turnover_rate_ma5"
                    | "turnover_to_ma5_ratio"
                    | "range_compression_20d"
                    | "range_compression_40d"
            ) {
                return policy(ContextFactorTransform::Raw, field == "position_90d");
            }
            None
        }
        "calc_daily_czsc_structure" => {
            if field.ends_with("_status") {
                return policy(ContextFactorTransform::StatusCode, false);
            }
            if field.ends_with("_last_bi_direction") {
                return policy(ContextFactorTransform::DirectionCode, false);
            }
            if field != "trade_date" && field.ends_with("_date") {
                return policy(ContextFactorTransform::AgeCalendarDays, false);
            }

            if field.ends_with("_count")
                || field.ends_with("_period_complete")
                || field.ends_with("_source_bar_valid")
                || field.ends_with("_missing")
                || field.ends_with("_duration_calendar_days")
            {
                return policy(ContextFactorTransform::Raw, false);
            }
            if [
                "_high", "_low", "_mid", "_zg", "_zd", "_zz", "_open", "_close",
            ]
            .iter()
            .any(|suffix| field.ends_with(suffix))
            {
                return policy(ContextFactorTransform::ToClosePct, false);
            }
            None
        }
        "moneyflow" => {
            if matches!(
                field,
                "net_sm_amount"
                    | "net_md_amount"
                    | "net_lg_amount"
                    | "net_elg_amount"
                    | "net_mf_vol"
                    | "net_mf_amount"
            ) {
                return policy(ContextFactorTransform::PerStock, false);
            }
            None
        }
        _ => None,
    }
}

fn context_factor_output_field(
    source: &str,
    field: &str,
    transform: ContextFactorTransform,
) -> String {
    match transform {
        ContextFactorTransform::Raw => field.to_string(),
        ContextFactorTransform::ToClosePct
            if source == "calc_daily_indicators" && field.ends_with("_macd_hist_x2_asof") =>
        {
            format!("{}_asof_to_close_pct", field.trim_end_matches("_x2_asof"))
        }
        ContextFactorTransform::ToClosePct => format!("{field}_to_close_pct"),
        ContextFactorTransform::PerStock => format!("{field}_per_stock"),
        ContextFactorTransform::StatusCode | ContextFactorTransform::DirectionCode => {
            format!("{field}_code")
        }
        ContextFactorTransform::AgeCalendarDays => {
            format!("{}_age_calendar_days", field.trim_end_matches("_date"))
        }
    }
}

fn context_source_factor_columns(source: &str, table: &str) -> Vec<&'static str> {
    if source == "calc_daily_czsc_structure" {
        crate::db_check::db_native_factor_source_columns(table)
            .into_iter()
            .chain(CZSC_CONTEXT_DURATIONS)
            .collect()
    } else {
        crate::db_check::db_native_numeric_factor_columns(table)
    }
}

const CZSC_CONTEXT_DURATIONS: [&str; 6] = [
    "daily_last_bi_duration_calendar_days",
    "daily_latest_zs_duration_calendar_days",
    "weekly_last_bi_duration_calendar_days",
    "weekly_latest_zs_duration_calendar_days",
    "monthly_last_bi_duration_calendar_days",
    "monthly_latest_zs_duration_calendar_days",
];

pub(crate) fn db_native_index_context_factor_columns() -> Vec<String> {
    let mut columns = Vec::new();
    for (_, alias) in INDEX_BENCHMARKS {
        columns.push(format!("market_index_{alias}_member_flag"));
        columns.push(format!("market_index_{alias}_weight_pct"));
        for (source, table) in INDEX_FACTOR_SOURCES {
            for field in context_source_factor_columns(source, table) {
                if let Some(policy) = context_factor_policy(source, field) {
                    let output_field = context_factor_output_field(source, field, policy.transform);
                    columns.push(format!("market_index_{alias}_{source}_{output_field}"));
                    if policy.weighted {
                        columns.push(format!(
                            "market_index_{alias}_weighted_{source}_{output_field}"
                        ));
                    }
                }
            }
        }
    }
    for (source, table) in INDEX_FACTOR_SOURCES {
        for field in context_source_factor_columns(source, table) {
            if let Some(policy) = context_factor_policy(source, field) {
                let output_field = context_factor_output_field(source, field, policy.transform);
                columns.push(format!("sw_l2_main_index_{source}_{output_field}"));
            }
        }
    }
    for field in crate::db_check::db_native_numeric_factor_columns("calc_daily_industry_moneyflow")
    {
        if let Some(policy) = context_factor_policy("moneyflow", field) {
            let output_field = context_factor_output_field("moneyflow", field, policy.transform);
            columns.push(format!("sw_l2_main_moneyflow_{output_field}"));
        }
    }
    columns
}

pub fn fetch_db_native_daily_window(
    duckdb_path: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Vec<MarketRow>> {
    Ok(fetch_db_native_daily_dataset(duckdb_path, start_date, end_date)?.rows)
}

pub fn fetch_db_native_daily_dataset(
    duckdb_path: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<MarketDataset> {
    fetch_db_native_daily_dataset_with_preflight(duckdb_path, start_date, end_date)
}

pub fn fetch_db_native_daily_rows_stream(
    duckdb_path: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
    consume: &mut dyn FnMut(MarketRow) -> anyhow::Result<()>,
) -> anyhow::Result<BTreeMap<String, DbDataGap>> {
    fetch_db_native_daily_rows_stream_with_order(duckdb_path, start_date, end_date, true, consume)
}

pub fn fetch_db_native_daily_rows_unordered_stream(
    duckdb_path: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
    consume: &mut dyn FnMut(MarketRow) -> anyhow::Result<()>,
) -> anyhow::Result<BTreeMap<String, DbDataGap>> {
    fetch_db_native_daily_rows_stream_with_order(duckdb_path, start_date, end_date, false, consume)
}

// 身份核验 SQL 与 Python dataset/标签共用；不按尾号改码，也不拼接不同前复权基准。
fn canonical_daily_window_query(client: &DuckDbConnection, query: &str) -> anyhow::Result<String> {
    let old_codes = client.query_map(include_str!("../ml/security_aliases.sql"), &[], |row| {
        row.try_get::<String>("old_code")
    })?;
    let query = query.trim_end().trim_end_matches(';');
    if old_codes.is_empty() {
        return Ok(query.to_string());
    }
    let literals = old_codes
        .iter()
        .map(|code| quack_text_literal(code))
        .collect::<anyhow::Result<Vec<_>>>()?;
    Ok(format!(
        "{query} AND s.ts_code NOT IN ({})",
        literals.join(", ")
    ))
}

fn fetch_db_native_daily_rows_stream_with_order(
    duckdb_path: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
    order_by_symbol: bool,
    consume: &mut dyn FnMut(MarketRow) -> anyhow::Result<()>,
) -> anyhow::Result<BTreeMap<String, DbDataGap>> {
    let strict_tables = resolve_db_check_tables()?;
    let client = open_duckdb(duckdb_path)?;
    configure_daily_window_session(&client)?;
    let plan = preflight_db_native_load(&client, start_date, end_date, &strict_tables)?;
    let mut pick_date_extras = BTreeMap::new();
    let pick_date_extras_query = plan.adapt_query(DB_NATIVE_PICK_DATE_EXTRAS_QUERY);
    let pick_date_factor_columns = db_native_pick_date_factor_columns();
    client.query_for_each(
        &pick_date_extras_query,
        &[DuckDbParameter::Date(end_date)],
        |row| {
            let ts_code = row.try_get("ts_code")?;
            let trade_date = row.try_get("trade_date")?;
            let mut factors = BTreeMap::new();
            for column in &pick_date_factor_columns {
                if let Some(value) = optional_option_f64(&row, column.as_str())?
                    && value.is_finite()
                {
                    factors.insert(column.clone(), value);
                }
            }
            Ok((ts_code, trade_date, factors))
        },
        |(ts_code, trade_date, factors)| {
            if !factors.is_empty() {
                pick_date_extras.insert((ts_code, trade_date), factors);
            }
            Ok(())
        },
    )?;

    let mut previous_month_macd = BTreeMap::new();
    let previous_month_macd_query = plan.adapt_query(DB_NATIVE_PREVIOUS_MONTH_MACD_QUERY);
    client.query_for_each(
        &previous_month_macd_query,
        &[DuckDbParameter::Date(end_date)],
        |row| {
            Ok((
                row.try_get::<String>("ts_code")?,
                row.try_get::<NaiveDate>("trade_date")?,
                optional_option_f64(&row, "macd_monthly_hist")?.filter(|value| value.is_finite()),
            ))
        },
        |(ts_code, trade_date, histogram)| {
            if let Some(histogram) = histogram {
                previous_month_macd.insert(ts_code, (trade_date, histogram));
            }
            Ok(())
        },
    )?;

    let mut sw_l2_sector_extras: BTreeMap<(String, NaiveDate), BTreeMap<String, f64>> =
        BTreeMap::new();
    let sw_l2_sector_extras_query = plan.adapt_query(DB_NATIVE_SW_L2_EXTRAS_QUERY);
    client.query_for_each(
        &sw_l2_sector_extras_query,
        &[DuckDbParameter::Date(end_date)],
        |row| context_extras_from_row(&row),
        |(ts_code, trade_date, factors)| {
            if !factors.is_empty() {
                sw_l2_sector_extras
                    .entry((ts_code, trade_date))
                    .or_default()
                    .extend(factors);
            }
            Ok(())
        },
    )?;

    let base_query =
        canonical_daily_window_query(&client, &plan.adapt_query(DB_NATIVE_DAILY_WINDOW_QUERY))?;
    let query = base_query.trim_end().trim_end_matches(';');
    let ordered_query;
    let query = if order_by_symbol {
        ordered_query = format!("{query} ORDER BY s.ts_code ASC, s.trade_date ASC");
        ordered_query.as_str()
    } else {
        query
    };
    client.query_for_each(
        &query,
        &[
            DuckDbParameter::Date(start_date),
            DuckDbParameter::Date(end_date),
        ],
        db_native_market_row_from_db_row,
        |mut row| {
            if row.trade_date == end_date
                && let Some(extras) =
                    pick_date_extras.remove(&(row.ts_code.clone(), row.trade_date))
            {
                row.db_factors.extend(extras);
            }
            if let Some(&(trade_date, histogram)) = previous_month_macd.get(row.ts_code.as_str())
                && row.trade_date == trade_date
            {
                row.db_factors
                    .insert("macd_monthly_hist".to_string(), histogram);
            }
            if let Some(extras) = sw_l2_sector_extras.remove(&(row.ts_code.clone(), row.trade_date))
            {
                row.db_factors.extend(extras);
            }
            consume(row)
        },
    )?;
    Ok(plan.db_data_gaps)
}

pub fn fetch_db_native_daily_window_for_intraday(
    duckdb_path: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Vec<MarketRow>> {
    Ok(fetch_db_native_daily_dataset_for_intraday(duckdb_path, start_date, end_date)?.rows)
}

pub fn fetch_db_native_daily_dataset_for_intraday(
    duckdb_path: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<MarketDataset> {
    fetch_db_native_daily_dataset_with_preflight(duckdb_path, start_date, end_date)
}

fn fetch_db_native_daily_dataset_with_preflight(
    duckdb_path: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<MarketDataset> {
    let strict_tables = resolve_db_check_tables()?;
    let client = open_duckdb(duckdb_path)?;
    configure_daily_window_session(&client)?;
    let plan = preflight_db_native_load(&client, start_date, end_date, &strict_tables)?;
    let query =
        canonical_daily_window_query(&client, &plan.adapt_query(DB_NATIVE_DAILY_WINDOW_QUERY))?;
    let mut market_rows = client.query_map(
        &query,
        &[
            DuckDbParameter::Date(start_date),
            DuckDbParameter::Date(end_date),
        ],
        db_native_market_row_from_db_row,
    )?;
    let pick_date_extras_query = plan.adapt_query(DB_NATIVE_PICK_DATE_EXTRAS_QUERY);
    merge_pick_date_extras(&client, &pick_date_extras_query, end_date, &mut market_rows)?;
    let previous_month_macd_query = plan.adapt_query(DB_NATIVE_PREVIOUS_MONTH_MACD_QUERY);
    merge_previous_month_macd(
        &client,
        &previous_month_macd_query,
        end_date,
        &mut market_rows,
    )?;
    let sw_l2_sector_extras_query = plan.adapt_query(DB_NATIVE_SW_L2_EXTRAS_QUERY);
    merge_sw_l2_extras(
        &client,
        &sw_l2_sector_extras_query,
        end_date,
        &mut market_rows,
    )?;
    Ok(MarketDataset {
        rows: market_rows,
        db_data_gaps: plan.db_data_gaps,
    })
}

pub fn fetch_stock_period_macd_states(
    duckdb_path: &str,
    symbols: &[String],
    pick_date: NaiveDate,
) -> anyhow::Result<Vec<MacdPeriodState>> {
    if symbols.is_empty() {
        return Ok(Vec::new());
    }
    let client = open_duckdb(duckdb_path)?;
    client.query_map(
        STOCK_PERIOD_MACD_STATE_QUERY,
        &[
            DuckDbParameter::TextList(symbols.to_vec()),
            DuckDbParameter::Date(pick_date),
        ],
        |row| {
            Ok(MacdPeriodState {
                ts_code: row.try_get("ts_code")?,
                period_type: row.try_get("period_type")?,
                ema12: optional_f64(&row, "ema12")?,
                ema26: optional_f64(&row, "ema26")?,
                dea: optional_f64(&row, "dea")?,
                period_count: row.try_get("period_count")?,
            })
        },
    )
}

fn db_native_market_row_from_db_row(row: DuckDbRow) -> anyhow::Result<MarketRow> {
    let mut db_factors = BTreeMap::new();
    for column in DB_NATIVE_FACTOR_COLUMNS {
        db_factors.insert((*column).to_string(), optional_option_f64(&row, column)?);
    }
    db_native_market_row_from_values(DbNativeDailyRow {
        ts_code: row.try_get("ts_code")?,
        trade_date: row.try_get("trade_date")?,
        open: optional_f64(&row, "open")?,
        high: optional_f64(&row, "high")?,
        low: optional_f64(&row, "low")?,
        close: optional_f64(&row, "close")?,
        adj_factor: optional_option_f64(&row, "adj_factor")?,
        vol: optional_f64(&row, "vol")?,
        turnover_rate: optional_option_f64(&row, "turnover_rate")?,
        db_factors,
    })
}

fn merge_pick_date_extras(
    client: &DuckDbConnection,
    query: &str,
    end_date: NaiveDate,
    market_rows: &mut [MarketRow],
) -> anyhow::Result<()> {
    let mut extras_by_key: BTreeMap<(String, NaiveDate), BTreeMap<String, f64>> = BTreeMap::new();
    let rows = client.query_rows(query, &[DuckDbParameter::Date(end_date)])?;
    let pick_date_factor_columns = db_native_pick_date_factor_columns();
    for row in rows {
        let ts_code: String = row.try_get("ts_code")?;
        let trade_date: NaiveDate = row.try_get("trade_date")?;
        let mut factors = BTreeMap::new();
        for column in &pick_date_factor_columns {
            if let Some(value) = optional_option_f64(&row, column.as_str())?
                && value.is_finite()
            {
                factors.insert(column.clone(), value);
            }
        }
        if !factors.is_empty() {
            extras_by_key.insert((ts_code, trade_date), factors);
        }
    }
    for row in market_rows
        .iter_mut()
        .filter(|row| row.trade_date == end_date)
    {
        if let Some(extras) = extras_by_key.remove(&(row.ts_code.clone(), row.trade_date)) {
            row.db_factors.extend(extras);
        }
    }
    Ok(())
}

fn merge_previous_month_macd(
    client: &DuckDbConnection,
    query: &str,
    end_date: NaiveDate,
    market_rows: &mut [MarketRow],
) -> anyhow::Result<()> {
    let mut previous_by_code = BTreeMap::new();
    for row in client.query_rows(query, &[DuckDbParameter::Date(end_date)])? {
        let ts_code: String = row.try_get("ts_code")?;
        let trade_date: NaiveDate = row.try_get("trade_date")?;
        if let Some(histogram) =
            optional_option_f64(&row, "macd_monthly_hist")?.filter(|value| value.is_finite())
        {
            previous_by_code.insert(ts_code, (trade_date, histogram));
        }
    }
    // 挂在原日期上，由 prepare_rows 与本月柱一起换算到选股日的前复权基准。
    for row in market_rows {
        if let Some(&(trade_date, histogram)) = previous_by_code.get(row.ts_code.as_str())
            && row.trade_date == trade_date
        {
            row.db_factors
                .insert("macd_monthly_hist".to_string(), histogram);
        }
    }
    Ok(())
}

fn merge_sw_l2_extras(
    client: &DuckDbConnection,
    query: &str,
    end_date: NaiveDate,
    market_rows: &mut [MarketRow],
) -> anyhow::Result<()> {
    let mut extras_by_key: BTreeMap<(String, NaiveDate), BTreeMap<String, f64>> = BTreeMap::new();
    let rows = client.query_rows(query, &[DuckDbParameter::Date(end_date)])?;
    for row in rows {
        let (ts_code, trade_date, factors) = context_extras_from_row(&row)?;
        extras_by_key
            .entry((ts_code, trade_date))
            .or_default()
            .extend(factors);
    }
    for row in market_rows {
        if let Some(extras) = extras_by_key.remove(&(row.ts_code.clone(), row.trade_date)) {
            row.db_factors.extend(extras);
        }
    }
    Ok(())
}

fn context_extras_from_row(
    row: &DuckDbRow,
) -> anyhow::Result<(String, NaiveDate, BTreeMap<String, f64>)> {
    let ts_code: String = row.try_get("ts_code")?;
    let trade_date: NaiveDate = row.try_get("trade_date")?;
    let context_type: String = row.try_get("context_type")?;
    let context_alias: String = row.try_get("context_alias")?;
    let member_flag: f64 = row.try_get("member_flag")?;
    let weight_pct: f64 = row.try_get("weight_pct")?;
    let index_payload: String = row.try_get("index_payload")?;
    let indicators_payload: String = row.try_get("indicators_payload")?;
    let rolling_payload: String = row.try_get("rolling_payload")?;
    let czsc_payload: String = row.try_get("czsc_payload")?;
    let moneyflow_payload: String = row.try_get("moneyflow_payload")?;
    let index_close = numeric_payload_field(&index_payload, "close")?;
    let stock_count = numeric_payload_field(&moneyflow_payload, "stock_count")?;
    let industry_net_amount = optional_option_f64(row, "industry_net_amount")?;
    let mut factors = BTreeMap::new();

    match context_type.as_str() {
        "market" => {
            if !INDEX_BENCHMARKS
                .iter()
                .any(|(_, alias)| *alias == context_alias.as_str())
            {
                anyhow::bail!("unknown index context alias: {context_alias}");
            }
            let prefix = format!("market_index_{context_alias}");
            let is_member = member_flag > 0.0;
            factors.insert(
                format!("{prefix}_member_flag"),
                if is_member { 1.0 } else { 0.0 },
            );
            factors.insert(
                format!("{prefix}_weight_pct"),
                if is_member && weight_pct.is_finite() {
                    weight_pct
                } else {
                    0.0
                },
            );
            for (source, payload) in [
                ("idx", index_payload.as_str()),
                ("calc_daily_indicators", indicators_payload.as_str()),
                ("calc_daily_rolling_factors", rolling_payload.as_str()),
                ("calc_daily_czsc_structure", czsc_payload.as_str()),
            ] {
                add_numeric_context_payload(
                    &mut factors,
                    &prefix,
                    source,
                    payload,
                    is_member,
                    weight_pct,
                    index_close,
                    stock_count,
                )?;
            }
        }
        "industry" => {
            let is_member = member_flag > 0.0;
            factors.insert(
                "sw_l2_membership_current_flag".to_string(),
                if is_member { 1.0 } else { 0.0 },
            );
            if is_member {
                for (source, payload) in [
                    ("idx", index_payload.as_str()),
                    ("calc_daily_indicators", indicators_payload.as_str()),
                    ("calc_daily_rolling_factors", rolling_payload.as_str()),
                    ("calc_daily_czsc_structure", czsc_payload.as_str()),
                    ("moneyflow", moneyflow_payload.as_str()),
                ] {
                    let (prefix, source) = if source == "moneyflow" {
                        ("sw_l2_main", "moneyflow")
                    } else {
                        ("sw_l2_main_index", source)
                    };
                    add_numeric_context_payload(
                        &mut factors,
                        prefix,
                        source,
                        payload,
                        true,
                        0.0,
                        index_close,
                        stock_count,
                    )?;
                }
                for (column, query_column) in [
                    ("sw_l2_main_pct_change", "industry_pct_change"),
                    (
                        "stock_vs_sw_l2_main_pct_change",
                        "stock_vs_industry_pct_change",
                    ),
                ] {
                    if let Some(value) = optional_option_f64(row, query_column)?
                        && value.is_finite()
                    {
                        factors.insert(column.to_string(), value);
                    }
                }
                if let (Some(amount), Some(stock_count)) = (
                    industry_net_amount.filter(|value| value.is_finite()),
                    stock_count.filter(|value| value.is_finite() && *value > 0.0),
                ) {
                    factors.insert(
                        "sw_l2_main_net_amount_per_stock".to_string(),
                        amount / stock_count,
                    );
                }
            }
        }
        value => anyhow::bail!("unknown index context type: {value}"),
    }
    Ok((ts_code, trade_date, factors))
}

fn add_numeric_context_payload(
    factors: &mut BTreeMap<String, f64>,
    prefix: &str,
    source: &str,
    payload: &str,
    is_member: bool,
    weight_pct: f64,
    index_close: Option<f64>,
    stock_count: Option<f64>,
) -> anyhow::Result<()> {
    let payload: Value = serde_json::from_str(payload)?;
    let Some(fields) = payload.as_object() else {
        return Ok(());
    };
    for (field, value) in fields {
        if !field
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'_')
        {
            continue;
        }
        let Some(policy) = context_factor_policy(source, field) else {
            continue;
        };
        let numeric = match policy.transform {
            ContextFactorTransform::StatusCode => value.as_str().and_then(|status| match status {
                "invalid_source_bar" => Some(0.0),
                "no_finished_bi" => Some(1.0),
                "insufficient_bis_for_zs" => Some(2.0),
                "no_valid_zs" => Some(3.0),
                "ok" => Some(4.0),
                _ => None,
            }),
            ContextFactorTransform::DirectionCode => {
                value.as_str().and_then(|direction| match direction {
                    "up" => Some(1.0),
                    "down" => Some(-1.0),
                    _ => None,
                })
            }
            ContextFactorTransform::AgeCalendarDays => payload_date(&payload, "trade_date")
                .zip(payload_date(&payload, field))
                .filter(|(asof, event)| event <= asof)
                .map(|(asof, event)| (asof - event).num_days() as f64),
            _ => value
                .as_f64()
                .or_else(|| value.as_bool().map(|value| if value { 1.0 } else { 0.0 })),
        }
        .filter(|value| value.is_finite());
        let Some(numeric) = numeric else {
            continue;
        };
        let output_field = context_factor_output_field(source, field, policy.transform);
        let transformed = if !is_member {
            0.0
        } else {
            // The cache stores MACD histogram values doubled; export the conventional histogram.
            let value =
                if source == "calc_daily_indicators" && field.ends_with("_macd_hist_x2_asof") {
                    numeric / 2.0
                } else {
                    numeric
                };
            match policy.transform {
                ContextFactorTransform::Raw
                | ContextFactorTransform::StatusCode
                | ContextFactorTransform::DirectionCode
                | ContextFactorTransform::AgeCalendarDays => value,
                ContextFactorTransform::ToClosePct => {
                    let Some(close) = index_close.filter(|close| close.is_finite() && *close > 0.0)
                    else {
                        continue;
                    };
                    value / close * 100.0
                }
                ContextFactorTransform::PerStock => {
                    let Some(stock_count) =
                        stock_count.filter(|count| count.is_finite() && *count > 0.0)
                    else {
                        continue;
                    };
                    value / stock_count
                }
            }
        };
        if !transformed.is_finite() {
            continue;
        }
        factors.insert(format!("{prefix}_{source}_{output_field}"), transformed);
        if policy.weighted {
            factors.insert(
                format!("{prefix}_weighted_{source}_{output_field}"),
                if is_member {
                    transformed
                        * if weight_pct.is_finite() {
                            weight_pct / 100.0
                        } else {
                            0.0
                        }
                } else {
                    0.0
                },
            );
        }
    }
    if source == "calc_daily_czsc_structure" {
        for period in ["daily", "weekly", "monthly"] {
            for structure in ["last_bi", "latest_zs"] {
                let dates = payload_date(&payload, &format!("{period}_{structure}_start_date"))
                    .zip(payload_date(
                        &payload,
                        &format!("{period}_{structure}_end_date"),
                    ))
                    .zip(payload_date(&payload, "trade_date"));
                if let Some(((start, end), _)) =
                    dates.filter(|((start, end), asof)| start <= end && end <= asof)
                {
                    factors.insert(
                        format!("{prefix}_{source}_{period}_{structure}_duration_calendar_days"),
                        if is_member {
                            (end - start).num_days() as f64
                        } else {
                            0.0
                        },
                    );
                }
            }
        }
    }

    Ok(())
}

fn payload_date(payload: &Value, field: &str) -> Option<NaiveDate> {
    NaiveDate::parse_from_str(payload.get(field)?.as_str()?, "%Y-%m-%d").ok()
}

fn numeric_payload_field(payload: &str, field: &str) -> anyhow::Result<Option<f64>> {
    let value: Value = serde_json::from_str(payload)?;
    Ok(value
        .get(field)
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite()))
}

fn db_native_market_row_from_values(row: DbNativeDailyRow) -> anyhow::Result<MarketRow> {
    let db_factors = db_factor_values_iter(row.db_factors);
    Ok(MarketRow {
        ts_code: row.ts_code,
        trade_date: row.trade_date,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
        vol: row.vol,
        turnover_rate: row.turnover_rate,
        adj_factor: row.adj_factor,
        db_factors,
    })
}

fn configure_daily_window_session(client: &DuckDbConnection) -> anyhow::Result<()> {
    client.execute_batch(DAILY_WINDOW_SESSION_SETTINGS_SQL)
}

pub fn fetch_index_history(
    duckdb_path: &str,
    ts_code: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Vec<MarketRow>> {
    let client = open_duckdb(duckdb_path)?;
    client.query_map(
        "
        SELECT
            ts_code,
            trade_date,
            open::double precision AS open,
            high::double precision AS high,
            low::double precision AS low,
            close::double precision AS close,
            vol::double precision AS vol
        FROM daily_index
        WHERE ts_code = $1
          AND trade_date BETWEEN $2 AND $3
        ORDER BY trade_date ASC
        ",
        &[
            DuckDbParameter::Text(ts_code.to_string()),
            DuckDbParameter::Date(start_date),
            DuckDbParameter::Date(end_date),
        ],
        |row| {
            Ok(MarketRow {
                ts_code: row.try_get("ts_code")?,
                trade_date: row.try_get("trade_date")?,
                open: optional_f64(&row, "open")?,
                high: optional_f64(&row, "high")?,
                low: optional_f64(&row, "low")?,
                close: optional_f64(&row, "close")?,
                vol: optional_f64(&row, "vol")?,
                turnover_rate: None,
                adj_factor: None,
                db_factors: BTreeMap::new(),
            })
        },
    )
}

pub fn resolve_previous_trade_date(
    duckdb_path: &str,
    trade_date: NaiveDate,
) -> anyhow::Result<NaiveDate> {
    let client = open_duckdb(duckdb_path)?;
    let row = client
        .query_rows(
            PREVIOUS_TRADE_DATE_QUERY,
            &[DuckDbParameter::Date(trade_date)],
        )?
        .into_iter()
        .next()
        .ok_or_else(|| anyhow::anyhow!("No previous trade date found before {trade_date}."))?;
    row.try_get::<Option<NaiveDate>>("trade_date")?
        .ok_or_else(|| anyhow::anyhow!("No previous trade date found before {trade_date}."))
}

pub fn fetch_instrument_info(
    duckdb_path: &str,
    symbols: &[String],
) -> anyhow::Result<BTreeMap<String, InstrumentInfo>> {
    if symbols.is_empty() {
        return Ok(BTreeMap::new());
    }

    let client = open_duckdb(duckdb_path)?;
    let mut instruments = BTreeMap::new();
    let parameters = [DuckDbParameter::TextList(symbols.to_vec())];
    for row in client.query_rows(STOCK_BASIC_INFO_QUERY, &parameters)? {
        let code: String = row.try_get("ts_code")?;
        let name: Option<String> = row.try_get("name")?;
        if let Some(name) = clean_optional_text(name) {
            instruments
                .entry(code)
                .or_insert_with(|| InstrumentInfo {
                    name: None,
                    industry: None,
                })
                .name = Some(name);
        }
    }
    for row in client.query_rows(SW_L2_INDUSTRY_QUERY, &parameters)? {
        let code: String = row.try_get("ts_code")?;
        let industry: Option<String> = row.try_get("industry")?;
        if let Some(industry) = clean_optional_text(industry) {
            instruments
                .entry(code)
                .or_insert_with(|| InstrumentInfo {
                    name: None,
                    industry: None,
                })
                .industry = Some(industry);
        }
    }
    Ok(instruments)
}

fn clean_optional_text(value: Option<String>) -> Option<String> {
    value
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
}

fn optional_f64(row: &DuckDbRow, column: &str) -> anyhow::Result<f64> {
    Ok(row.try_get::<Option<f64>>(column)?.unwrap_or(f64::NAN))
}

fn optional_option_f64(row: &DuckDbRow, column: &str) -> anyhow::Result<Option<f64>> {
    row.try_get::<Option<f64>>(column)
}

fn db_factor_values_iter<I, K>(values: I) -> BTreeMap<String, f64>
where
    I: IntoIterator<Item = (K, Option<f64>)>,
    K: Into<String>,
{
    values
        .into_iter()
        .filter_map(|(key, value)| {
            value
                .filter(|value| value.is_finite())
                .map(|value| (key.into(), value))
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn index_source_contract_covers_every_technical_and_asof_field() {
        for (source, table, expected_excluded) in [
            (
                "idx",
                "index_idx_factor_pro",
                vec![
                    "ts_code",
                    "trade_date",
                    "open",
                    "high",
                    "low",
                    "close",
                    "pre_close",
                    "change",
                    "vol",
                    "amount",
                ],
            ),
            (
                "calc_daily_indicators",
                "calc_daily_indicators",
                vec!["source_dataset", "ts_code", "trade_date", "calc_version"],
            ),
            (
                "calc_daily_czsc_structure",
                "calc_daily_czsc_structure",
                vec!["source_dataset", "ts_code", "trade_date", "calc_version"],
            ),
            (
                "calc_daily_rolling_factors",
                "calc_daily_rolling_factors",
                vec![
                    "source_dataset",
                    "ts_code",
                    "trade_date",
                    "calc_version",
                    "volume_ma5",
                    "volume_ma20",
                ],
            ),
        ] {
            let mut excluded = crate::db_check::db_native_factor_source_columns(table)
                .into_iter()
                .filter(|field| context_factor_policy(source, field).is_none())
                .collect::<Vec<_>>();
            excluded.sort();
            let mut expected = expected_excluded;
            expected.sort();
            assert_eq!(excluded, expected, "unreviewed source fields in {table}");
        }
        assert_eq!(
            context_factor_policy("idx", "xsii_td1_bfq")
                .unwrap()
                .transform,
            ContextFactorTransform::ToClosePct
        );
    }

    #[test]
    fn czsc_context_keeps_direction_status_and_dates_without_future_information() {
        let mut factors = BTreeMap::new();
        let payload = r#"{"trade_date":"2026-11-20","weekly_status":"ok","weekly_last_bi_direction":"down","weekly_last_bi_start_date":"2026-11-02","weekly_last_bi_end_date":"2026-11-13","weekly_recent_peak_date":"2026-11-23","monthly_status":null}"#;
        add_numeric_context_payload(
            &mut factors,
            "sw_l2_main_index",
            "calc_daily_czsc_structure",
            payload,
            true,
            0.0,
            Some(100.0),
            None,
        )
        .unwrap();
        let key = |field: &str| format!("sw_l2_main_index_calc_daily_czsc_structure_{field}");
        assert_eq!(factors.get(&key("weekly_status_code")), Some(&4.0));
        assert_eq!(
            factors.get(&key("weekly_last_bi_direction_code")),
            Some(&-1.0)
        );
        assert_eq!(
            factors.get(&key("weekly_last_bi_start_age_calendar_days")),
            Some(&18.0)
        );
        assert_eq!(
            factors.get(&key("weekly_last_bi_duration_calendar_days")),
            Some(&11.0)
        );
        assert!(!factors.contains_key(&key("weekly_recent_peak_age_calendar_days")));
        assert!(!factors.contains_key(&key("monthly_status_code")));
        let columns = db_native_index_context_factor_columns();
        assert!(factors.keys().all(|key| columns.contains(key)));
        let mut nonmember = BTreeMap::new();
        add_numeric_context_payload(
            &mut nonmember,
            "market_index_sse50",
            "calc_daily_czsc_structure",
            payload,
            false,
            0.0,
            Some(100.0),
            None,
        )
        .unwrap();
        assert!(nonmember.values().all(|value| *value == 0.0));
    }

    #[test]
    fn stock_czsc_multiperiod_projection_executes_every_source_field_and_preserves_nulls() {
        let projection = DB_NATIVE_PICK_DATE_EXTRAS_QUERY
            .split("-- czsc multiperiod begin")
            .nth(1)
            .unwrap()
            .split("-- czsc multiperiod end")
            .next()
            .unwrap()
            .trim()
            .trim_end_matches(',');
        let client = open_duckdb(":memory:").unwrap();
        for present in [true, false] {
            let source =
                crate::db_check::db_native_factor_source_columns("calc_daily_czsc_structure")
                    .into_iter()
                    .map(|field| {
                        let value = if field.ends_with("_date") {
                            "DATE '2026-11-02'"
                        } else if field.ends_with("_status") {
                            "'ok'::VARCHAR"
                        } else if field.ends_with("_direction") {
                            "'down'::VARCHAR"
                        } else if field.ends_with("_complete")
                            || field.ends_with("_valid")
                            || field.ends_with("_missing")
                        {
                            "false"
                        } else if field.ends_with("_count")
                            || [
                                "_high", "_low", "_mid", "_zg", "_zd", "_zz", "_open", "_close",
                            ]
                            .iter()
                            .any(|suffix| field.ends_with(suffix))
                        {
                            "10.0"
                        } else {
                            "'fixture'::VARCHAR"
                        };
                        if present {
                            format!("{value} AS {field}")
                        } else {
                            format!("CASE WHEN false THEN {value} END AS {field}")
                        }
                    })
                    .collect::<Vec<_>>()
                    .join(", ");
            let query = format!("SELECT {projection} FROM (SELECT {source}) c");
            let rows = client.query_rows(&query, &[]).unwrap();
            for period in ["weekly", "monthly"] {
                let get = |field: &str| {
                    optional_option_f64(&rows[0], &format!("_czsc_{period}_{field}")).unwrap()
                };
                assert_eq!(
                    get("snapshot_available"),
                    Some(if present { 1.0 } else { 0.0 })
                );
                assert_eq!(get("period_complete"), present.then_some(0.0));
                assert_eq!(get("status_code"), present.then_some(4.0));
                assert_eq!(get("last_bi_direction_code"), present.then_some(-1.0));
                for (field, _) in rows[0]
                    .columns
                    .iter()
                    .filter(|(field, _)| field.starts_with(&format!("_czsc_{period}_")))
                {
                    if !field.ends_with("snapshot_available") {
                        assert_eq!(
                            optional_option_f64(&rows[0], field).unwrap().is_some(),
                            present,
                            "{field}"
                        );
                    }
                }
            }
        }
    }

    #[test]
    fn stock_multiperiod_projection_and_training_inputs_are_not_silently_dropped() {
        let columns = db_native_pick_date_factor_columns();
        for period in ["weekly", "monthly"] {
            for field in [
                "snapshot_available",
                "period_complete",
                "status_code",
                "last_bi_start_day",
                "post_peak_first_bear_close",
            ] {
                let key = format!("_czsc_{period}_{field}");
                assert!(columns.contains(&key), "{key}");
                assert!(
                    DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains(&format!("AS {key}")),
                    "{key}"
                );
            }
            for component in ["k", "d", "j"] {
                let key = format!("kdj_{period}_{component}");
                assert!(columns.contains(&key), "{key}");
            }
        }
        assert!(columns.contains(&"_czsc_period_complete".to_string()));
    }

    #[test]
    fn quack_parameters_preserve_sql_literals_comments_and_identifiers() {
        let sql = concat!(
            r#"SELECT $1, $2, $3, '$1', "ident$2", $$ $3 $$, "#,
            r#"$body$ $1 $body$, E'escaped \' $1', foo$1, "#,
            "/* $1 /* $2 */ $3 */ -- $2\n$1"
        );
        let parameters = [
            DuckDbParameter::Text("汉字 O'Brien".into()),
            DuckDbParameter::TextList(vec!["a'b".into(), "x".into()]),
            DuckDbParameter::Date(NaiveDate::from_ymd_opt(2026, 6, 1).unwrap()),
        ];
        let expected = concat!(
            r#"SELECT '汉字 O''Brien', CAST(['a''b', 'x'] AS VARCHAR[]), DATE '2026-06-01', "#,
            r#"'$1', "ident$2", $$ $3 $$, $body$ $1 $body$, "#,
            r#"E'escaped \' $1', foo$1, /* $1 /* $2 */ $3 */ -- $2"#,
            "\n'汉字 O''Brien'"
        );
        assert_eq!(inline_quack_parameters(sql, &parameters).unwrap(), expected);
    }

    #[test]
    fn quack_parameters_validate_missing_null_and_empty_list_values() {
        assert!(
            inline_quack_parameters("SELECT $2", &[DuckDbParameter::Text("x".into())]).is_err()
        );
        assert!(
            inline_quack_parameters("SELECT $0", &[DuckDbParameter::Text("x".into())]).is_err()
        );
        assert!(
            inline_quack_parameters("SELECT $1", &[DuckDbParameter::Text("a\0b".into())]).is_err()
        );
        assert_eq!(
            inline_quack_parameters("SELECT $1", &[DuckDbParameter::TextList(vec![])]).unwrap(),
            "SELECT CAST([] AS VARCHAR[])"
        );
    }

    fn security_identity_fixture() -> DuckDbConnection {
        let client = open_duckdb(":memory:").unwrap();
        client
            .query_rows(
                "CREATE TABLE stock_stk_factor_pro AS
             SELECT code AS ts_code, DATE '2023-02-01' + i::INTEGER AS trade_date,
                    10.0 + i AS open, 11.0 + i AS high, 9.0 + i AS low,
                    10.5 + i AS close, 1000.0 + i AS vol
             FROM range(25) t(i), (VALUES ('831445.BJ'), ('920445.BJ')) c(code)",
                &[],
            )
            .unwrap();
        client
    }

    #[test]
    fn security_identity_filters_verified_old_codes_before_screening() {
        let client = security_identity_fixture();
        // A suffix collision is a different security and must survive.
        client
            .query_rows(
                "INSERT INTO stock_stk_factor_pro
             SELECT '834445.BJ', trade_date, open + 1, high + 1, low + 1, close + 1, vol
             FROM stock_stk_factor_pro WHERE ts_code = '831445.BJ'",
                &[],
            )
            .unwrap();
        let query = canonical_daily_window_query(
            &client,
            "SELECT s.ts_code FROM stock_stk_factor_pro s WHERE true",
        )
        .unwrap();
        let rows = client
            .query_map(&query, &[], |row| row.try_get::<String>("ts_code"))
            .unwrap();
        assert_eq!(rows.len(), 50);
        assert!(!rows.iter().any(|code| code == "831445.BJ"));
        assert!(rows.iter().any(|code| code == "834445.BJ"));
    }

    #[test]
    fn security_identity_accepts_volume_precision_rounding_after_exact_bar_verification() {
        let client = security_identity_fixture();
        client.query_rows(
            "UPDATE stock_stk_factor_pro SET vol = vol + 0.25 WHERE ts_code = '831445.BJ' AND trade_date = DATE '2023-02-01'", &[],
        ).unwrap();
        assert!(
            canonical_daily_window_query(
                &client,
                "SELECT s.ts_code FROM stock_stk_factor_pro s WHERE true"
            )
            .is_ok()
        );
    }

    #[test]
    fn security_identity_rejects_ambiguity_and_inconsistent_or_incomplete_history() {
        for mutation in [
            "INSERT INTO stock_stk_factor_pro SELECT '920999.BJ', trade_date, open, high, low, close, vol FROM stock_stk_factor_pro WHERE ts_code = '920445.BJ'",
            "UPDATE stock_stk_factor_pro SET close = close + 1 WHERE ts_code = '920445.BJ' AND trade_date = DATE '2023-02-01'",
            "DELETE FROM stock_stk_factor_pro WHERE ts_code = '920445.BJ' AND trade_date = DATE '2023-02-01'",
            "UPDATE stock_stk_factor_pro SET vol = vol + 2 WHERE ts_code = '920445.BJ' AND trade_date = DATE '2023-02-01'",
        ] {
            let client = security_identity_fixture();
            client.query_rows(mutation, &[]).unwrap();
            assert!(
                canonical_daily_window_query(
                    &client,
                    "SELECT s.ts_code FROM stock_stk_factor_pro s WHERE true"
                )
                .is_err(),
                "{mutation}"
            );
        }
    }

    #[test]
    fn db_native_daily_window_query_maps_stock_cache_contract_fields() {
        for fragment in [
            "SELECT $1::date AS start_date, $2::date AS end_date",
            "FROM {{stock_stk_factor_pro}} s",
            "s.close_qfq::double precision AS _source_close_qfq",
            "s.adj_factor::double precision AS adj_factor",
            "s.trade_date BETWEEN (SELECT start_date FROM query_params) AND (SELECT end_date FROM query_params)",
            "s.open::double precision AS open",
            "s.high::double precision AS high",
            "s.low::double precision AS low",
            "s.close::double precision AS close",
            "s.vol::double precision AS vol",
            "s.amount::double precision AS amount",
            "s.turnover_rate::double precision AS turnover_rate",
            "LEFT JOIN {{calc_daily_czsc_structure}} c",
            "c.ts_code = s.ts_code",
            "c.trade_date = s.trade_date",
            "c.calc_version = 'v3-macd-kdj-czsc-1'",
            "c.daily_source_bar_valid",
            "c.daily_available_finished_bi_count",
            "c.daily_last_bi_direction",
            "c.daily_latest_zs_zg",
            "c.daily_latest_zs_zd",
            "c.daily_latest_zs_zz",
            "c.daily_recent_peak_high",
            "c.daily_post_peak_first_bear_open",
        ] {
            assert!(
                DB_NATIVE_DAILY_WINDOW_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        for fragment in [
            "stock_moneyflow_recent",
            "index_market_base AS",
            "calc_daily_indicators",
            "calc_daily_rolling_factors",
            "stock_daily_left_peak",
            "kdj_k_qfq",
            "large_net_amount_to_amount_pct",
            "market_sse_ret5_pct",
        ] {
            assert!(
                !DB_NATIVE_DAILY_WINDOW_QUERY.contains(fragment),
                "main prepared stock window should not contain pick-date extra fragment {fragment}"
            );
        }
        assert!(!DB_NATIVE_DAILY_WINDOW_QUERY.contains("left_peak_qfq_v1"));
        assert!(
            !DB_NATIVE_DAILY_WINDOW_QUERY.contains("ORDER BY s.ts_code"),
            "main DB-native window should not force a database sort; Rust prepare_rows sorts per symbol"
        );
        for fragment in [
            "s.open_qfq::double precision AS open",
            "s.high_qfq::double precision AS high",
            "s.low_qfq::double precision AS low",
            "s.close_qfq::double precision AS close",
        ] {
            assert!(
                !DB_NATIVE_DAILY_WINDOW_QUERY.contains(fragment),
                "the source query should keep raw OHLC and use close_qfq only as a reference: {fragment}"
            );
        }
    }

    #[test]
    fn db_native_daily_window_keeps_raw_ohlc_and_qfq_reference_for_alignment() {
        assert!(DB_NATIVE_DAILY_WINDOW_QUERY.contains("s.close::double precision AS close"));
        assert!(
            DB_NATIVE_DAILY_WINDOW_QUERY
                .contains("s.close_qfq::double precision AS _source_close_qfq")
        );
        assert!(DB_NATIVE_FACTOR_COLUMNS.contains(&"_source_close_qfq"));
    }

    #[test]
    fn db_native_row_keeps_only_a_finite_qfq_close_reference() {
        for source_close_qfq in [None, Some(f64::NAN), Some(12.5)] {
            let mapped = db_native_market_row_from_values(DbNativeDailyRow {
                ts_code: "000001.SZ".to_string(),
                trade_date: NaiveDate::from_ymd_opt(2026, 1, 30).unwrap(),
                open: 10.0,
                high: 11.0,
                low: 9.0,
                close: 10.0,
                adj_factor: Some(1.0),
                vol: 100.0,
                turnover_rate: None,
                db_factors: BTreeMap::from([("_source_close_qfq".to_string(), source_close_qfq)]),
            })
            .unwrap();
            if source_close_qfq.is_some_and(f64::is_finite) {
                assert_eq!(
                    mapped.db_factors.get("_source_close_qfq"),
                    source_close_qfq.as_ref()
                );
            } else {
                assert!(!mapped.db_factors.contains_key("_source_close_qfq"));
            }
        }
    }

    #[test]
    fn stk_factor_pro_projection_reads_nullable_qfq_source_values() {
        use crate::factors::stk_factor_pro::SOURCE_COLUMNS;
        let projection = DB_NATIVE_PICK_DATE_EXTRAS_QUERY
            .split("-- stk_factor_pro begin")
            .nth(1)
            .expect("pick-date query must load the extended snapshot")
            .split("-- stk_factor_pro end")
            .next()
            .unwrap()
            .trim()
            .trim_end_matches(',');
        let client = open_duckdb(":memory:").unwrap();
        let fixture = SOURCE_COLUMNS
            .iter()
            .map(|name| {
                let value = match *name {
                    "close_qfq" => "20.0",
                    "atr_qfq" => "1.0",
                    "mfi_qfq" => "62.5",
                    _ => "NULL",
                };
                format!("{value}::DOUBLE AS {name}")
            })
            .collect::<Vec<_>>()
            .join(", ");
        let query = format!("SELECT {projection} FROM (SELECT {fixture}) s");
        let rows = client.query_rows(&query, &[]).unwrap();
        assert_eq!(rows.len(), 1);
        for name in SOURCE_COLUMNS {
            let value = optional_option_f64(&rows[0], &format!("_stk_{name}")).unwrap();
            let expected = match *name {
                "close_qfq" => Some(20.0),
                "atr_qfq" => Some(1.0),
                "mfi_qfq" => Some(62.5),
                _ => None,
            };
            assert_eq!(value, expected, "{name}");
        }
    }

    #[test]
    fn db_native_pick_date_extras_query_maps_wide_db_native_factors() {
        for fragment in [
            "WHERE s.trade_date = $1",
            "s.kdj_k_qfq::double precision AS kdj_k_qfq",
            "s.kdj_d_qfq::double precision AS kdj_d_qfq",
            "s.dmi_adxr_qfq::double precision AS dmi_adxr_qfq",
            "s.dmi_pdi_qfq::double precision - s.dmi_mdi_qfq::double precision AS dmi_pdi_mdi_spread_qfq",
            "s.dmi_adx_qfq::double precision - s.dmi_adxr_qfq::double precision AS dmi_adx_adxr_gap_qfq",
            "s.trix_qfq::double precision AS trix_qfq",
            "FROM {{stock_moneyflow}} f",
            "LEFT JOIN stock_moneyflow_recent smf",
            "smf.net_mf_amount AS stock_mf_net_amount",
            "smf.buy_lg_amount AS stock_mf_buy_lg_amount",
            "THEN smf.buy_lg_amount / (s.amount / 10.0) * 100.0",
            "THEN smf.buy_md_amount / (s.amount / 10.0) * 100.0",
            "THEN smf.buy_sm_amount / (s.amount / 10.0) * 100.0",
            "WHEN s.amount IS NOT NULL AND s.amount != 0 AND smf.net_mf_amount IS NOT NULL",
            "THEN smf.net_mf_amount / (s.amount / 10.0) * 100.0",
            "LEFT JOIN {{calc_daily_indicators}} a",
            "LEFT JOIN {{calc_daily_rolling_factors}} r",
            "a.calc_version = 'v3-macd-kdj-czsc-1'",
            "a.daily_macd_hist_x2_asof::double precision / 2.0 AS macd_daily_hist",
            "a.weekly_macd_hist_x2_asof::double precision / 2.0 AS macd_weekly_hist",
            "a.monthly_macd_hist_x2_asof::double precision / 2.0 AS macd_monthly_hist",
            "r.calc_version = 'v3-macd-kdj-czsc-1'",
            "r.position_90d::double precision AS rolling_position_90d",
            "r.close_to_20d_max_close_pct::double precision AS close_to_20d_max_close_pct",
        ] {
            assert!(
                DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        for legacy_fragment in [
            "index_market_base",
            "market_sse_ret5_pct",
            "market_cn2000_ret5_pct",
            "market_broad_ret5_pct",
            "000001.SH",
            "399303.SZ",
            "stock_moneyflow_ths",
        ] {
            assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains(legacy_fragment));
        }
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("stock_daily_left_peak"));
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("left_peak_"));
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("prev_hist"));
        assert!(
            !DB_NATIVE_PICK_DATE_FACTOR_COLUMNS
                .iter()
                .any(|column| column.ends_with("_prev_hist"))
        );
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("s.kdj_j_qfq"));
        assert!(DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("CASE"));
        assert!(
            DB_NATIVE_PICK_DATE_EXTRAS_QUERY
                .contains("WHEN s.kdj_k_qfq IS NOT NULL AND s.kdj_d_qfq IS NOT NULL")
        );
        assert!(DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains(
            "THEN 3.0 * s.kdj_k_qfq::double precision - 2.0 * s.kdj_d_qfq::double precision"
        ));
        for factor in [
            "amount",
            "kdj_k_qfq",
            "dmi_adx_qfq",
            "trix_qfq",
            "stock_mf_net_amount",
            "large_net_amount_to_amount_pct",
            "mid_net_amount_to_amount_pct",
            "small_net_amount_to_amount_pct",
            "net_mf_amount_to_amount_pct",
            "tushare_macd_qfq",
            "macd_weekly_hist",
            "close_to_20d_max_close_pct",
        ] {
            assert!(
                DB_NATIVE_PICK_DATE_FACTOR_COLUMNS.contains(&factor),
                "missing pick-date factor column {factor}"
            );
        }
    }

    #[test]
    fn db_native_daily_window_query_uses_requested_prepared_range() {
        let query_head = DB_NATIVE_DAILY_WINDOW_QUERY
            .split("current_sw_membership AS")
            .next()
            .expect("query should define main stock window first");

        assert!(query_head.contains("SELECT $1::date AS start_date, $2::date AS end_date"));
        assert!(query_head.contains(
            "s.trade_date BETWEEN (SELECT start_date FROM query_params) AND (SELECT end_date FROM query_params)"
        ));
        assert!(!query_head.contains("LIMIT 252"));
    }

    #[test]
    fn db_native_queries_consume_all_relation_placeholders() {
        let plan = crate::db_check::plan_from_inspections(&BTreeMap::new());

        for query in [
            DB_NATIVE_DAILY_WINDOW_QUERY,
            DB_NATIVE_PICK_DATE_EXTRAS_QUERY,
            DB_NATIVE_PREVIOUS_MONTH_MACD_QUERY,
            DB_NATIVE_SW_L2_EXTRAS_QUERY,
        ] {
            let adapted = plan.adapt_query(query);
            assert!(!adapted.contains("{{"), "unresolved relation placeholder");
        }
    }

    #[test]
    fn db_module_no_longer_exposes_legacy_daily_market_loader() {
        let source = include_str!("db.rs")
            .split("#[cfg(test)]")
            .next()
            .unwrap_or_default();

        assert!(!source.contains("const DAILY_WINDOW_QUERY"));
        assert!(!source.contains("pub fn fetch_daily_window"));
        assert!(!source.contains("DB_NATIVE_COVERAGE_PROBE_QUERY"));
        assert!(!source.contains("probe_db_native_coverage"));
    }

    #[test]
    fn db_native_index_context_joins_asof_weights_and_factor_payloads() -> anyhow::Result<()> {
        let client = open_duckdb(":memory:")?;
        client.execute_batch(
            "CREATE TABLE stock_stk_factor_pro (ts_code VARCHAR, trade_date DATE, pct_chg DOUBLE);
             CREATE TABLE index_weight (index_code VARCHAR, con_code VARCHAR, trade_date DATE, weight DOUBLE);
             CREATE TABLE index_idx_factor_pro (ts_code VARCHAR, trade_date DATE, close DOUBLE, pct_change DOUBLE, macd_bfq DOUBLE);
             CREATE TABLE calc_daily_indicators (source_dataset VARCHAR, ts_code VARCHAR, trade_date DATE, calc_version VARCHAR, daily_macd_dif_asof DOUBLE, daily_macd_hist_x2_asof DOUBLE, weekly_kdj_k_asof DOUBLE);
             CREATE TABLE calc_daily_rolling_factors (source_dataset VARCHAR, ts_code VARCHAR, trade_date DATE, calc_version VARCHAR, position_90d DOUBLE);
             CREATE TABLE calc_daily_czsc_structure (source_dataset VARCHAR, ts_code VARCHAR, trade_date DATE, calc_version VARCHAR, daily_recent_bi_count INTEGER);
             CREATE TABLE index_sw_member (ts_code VARCHAR, l2_code VARCHAR, in_date DATE, out_date DATE);
             CREATE TABLE calc_daily_industry_moneyflow (source_dataset VARCHAR, industry_code VARCHAR, trade_date DATE, stock_count BIGINT, main_net_amount DOUBLE, net_mf_amount DOUBLE, calc_version VARCHAR);
             INSERT INTO stock_stk_factor_pro VALUES
               ('000001.SZ', DATE '2026-02-10', 1.1), ('000002.SZ', DATE '2026-02-10', -1.0),
               ('000003.SZ', DATE '2026-02-10', 0.4);
             INSERT INTO index_weight VALUES
               ('000016.SH', '000001.SZ', DATE '2026-02-01', 1.3),
               ('000016.SH', '000002.SZ', DATE '2026-02-01', 0.9),
               ('000016.SH', '000001.SZ', DATE '2026-02-05', 1.6),
               ('000016.SH', '000001.SZ', DATE '2026-02-15', 1.9),
               ('000016.SH', '000003.SZ', DATE '2026-02-05', 0.0),
               ('000300.SH', '000001.SZ', DATE '2026-02-05', 2.5),
               ('399303.SZ', '000001.SZ', DATE '2026-02-05', 0.8),
               ('399006.SZ', '000001.SZ', DATE '2026-02-05', 1.2),
               ('899050.BJ', '000001.SZ', DATE '2026-02-05', 3.0);
             INSERT INTO index_idx_factor_pro VALUES
               ('000016.SH', DATE '2026-02-10', 10.0, 0.8, 2.0),
               ('000905.SH', DATE '2026-02-10', 10.0, 0.7, 3.0),
               ('000688.SH', DATE '2026-02-10', 10.0, 0.6, 4.0),
               ('930050.CSI', DATE '2026-02-10', 10.0, 0.5, 5.0),
               ('000922.CSI', DATE '2026-02-10', 10.0, 0.4, 6.0),
               ('000300.SH', DATE '2026-02-10', 10.0, 0.3, 7.0),
               ('399303.SZ', DATE '2026-02-10', 10.0, 0.2, 8.0),
               ('399006.SZ', DATE '2026-02-10', 10.0, 0.1, 9.0),
               ('899050.BJ', DATE '2026-02-10', 10.0, 0.0, 10.0),
               ('801100.SI', DATE '2026-02-10', 10.0, 1.0, 0.5),
               ('801200.SI', DATE '2026-02-10', 2.0, 2.0, 0.8);
             INSERT INTO calc_daily_indicators VALUES
               ('index_idx_factor_pro', '000016.SH', DATE '2026-02-10', 'v3-macd-kdj-czsc-1', 0.75, 0.4, 66.0),
               ('index_idx_factor_pro', '801200.SI', DATE '2026-02-10', 'v3-macd-kdj-czsc-1', 0.25, 0.2, 54.0);
             INSERT INTO calc_daily_rolling_factors VALUES
               ('index_idx_factor_pro', '000016.SH', DATE '2026-02-10', 'v3-macd-kdj-czsc-1', 0.7);
             INSERT INTO calc_daily_czsc_structure VALUES
               ('index_idx_factor_pro', '000016.SH', DATE '2026-02-10', 'v3-macd-kdj-czsc-1', 8);
             INSERT INTO index_sw_member VALUES
               ('000001.SZ', '801100.SI', DATE '2026-01-01', NULL),
               ('000001.SZ', '801200.SI', DATE '2026-02-01', NULL);
             INSERT INTO calc_daily_industry_moneyflow VALUES
               ('stock_moneyflow', '801200.SI', DATE '2026-02-10', 4, 12.0, 20.0, 'sw2021-l2-v1');",
        )?;
        let query = [
            ("{{stock_stk_factor_pro}}", "stock_stk_factor_pro"),
            ("{{index_weight}}", "index_weight"),
            ("{{index_idx_factor_pro}}", "index_idx_factor_pro"),
            ("{{calc_daily_indicators}}", "calc_daily_indicators"),
            (
                "{{calc_daily_rolling_factors}}",
                "calc_daily_rolling_factors",
            ),
            ("{{calc_daily_czsc_structure}}", "calc_daily_czsc_structure"),
            ("{{index_sw_member}}", "index_sw_member"),
            (
                "{{calc_daily_industry_moneyflow}}",
                "calc_daily_industry_moneyflow",
            ),
        ]
        .into_iter()
        .fold(
            DB_NATIVE_SW_L2_EXTRAS_QUERY.to_string(),
            |query, (placeholder, table)| query.replace(placeholder, table),
        );
        let date = NaiveDate::from_ymd_opt(2026, 2, 10).unwrap();
        let mut rows = ["000001.SZ", "000002.SZ", "000003.SZ"]
            .into_iter()
            .map(|ts_code| {
                db_native_market_row_from_values(DbNativeDailyRow {
                    ts_code: ts_code.to_string(),
                    trade_date: date,
                    open: 10.0,
                    high: 10.0,
                    low: 10.0,
                    close: 10.0,
                    adj_factor: Some(1.0),
                    vol: 1.0,
                    turnover_rate: Some(1.0),
                    db_factors: BTreeMap::new(),
                })
            })
            .collect::<anyhow::Result<Vec<_>>>()?;

        merge_sw_l2_extras(&client, &query, date, &mut rows)?;

        assert_eq!(rows.len(), 3);
        let member = rows.iter().find(|row| row.ts_code == "000001.SZ").unwrap();
        assert_eq!(member.db_factors["market_index_sse50_member_flag"], 1.0);
        assert_eq!(member.db_factors["market_index_sse50_weight_pct"], 1.6);
        assert_eq!(
            member.db_factors["market_index_sse50_idx_macd_bfq_to_close_pct"],
            20.0
        );
        assert_eq!(
            member.db_factors["market_index_sse50_weighted_idx_macd_bfq_to_close_pct"],
            0.32
        );
        assert!(
            (member.db_factors
                ["market_index_sse50_calc_daily_indicators_daily_macd_dif_asof_to_close_pct"]
                - 7.5)
                .abs()
                < 1e-12
        );
        assert!(
            (member.db_factors["market_index_sse50_weighted_calc_daily_indicators_daily_macd_hist_asof_to_close_pct"]
                - 0.032)
                .abs()
                < 1e-12
        );
        assert_eq!(
            member.db_factors["market_index_sse50_calc_daily_indicators_daily_macd_hist_asof_to_close_pct"],
            2.0
        );
        assert!(
            (member.db_factors
                ["market_index_sse50_weighted_calc_daily_rolling_factors_position_90d"]
                - 0.0112)
                .abs()
                < 1e-12
        );
        for (alias, weight, macd) in [
            ("csi300", 2.5, 7.0),
            ("guozheng2000", 0.8, 8.0),
            ("chinext", 1.2, 9.0),
            ("bse50", 3.0, 10.0),
        ] {
            assert_eq!(
                member.db_factors[&format!("market_index_{alias}_member_flag")],
                1.0
            );
            assert_eq!(
                member.db_factors[&format!("market_index_{alias}_weight_pct")],
                weight
            );
            assert_eq!(
                member.db_factors[&format!("market_index_{alias}_idx_macd_bfq_to_close_pct")],
                macd * 10.0
            );
            assert_eq!(
                member.db_factors
                    [&format!("market_index_{alias}_weighted_idx_macd_bfq_to_close_pct")],
                macd * 10.0 * weight / 100.0
            );
        }
        assert_eq!(member.db_factors["sw_l2_membership_current_flag"], 1.0);
        assert_eq!(
            member.db_factors["sw_l2_main_index_idx_macd_bfq_to_close_pct"],
            40.0
        );
        assert_eq!(member.db_factors["sw_l2_main_net_amount_per_stock"], 3.0);
        assert_eq!(
            member.db_factors["sw_l2_main_moneyflow_net_mf_amount_per_stock"],
            5.0
        );
        assert!((member.db_factors["stock_vs_sw_l2_main_pct_change"] + 0.9).abs() < 1e-12);
        assert!(
            !member
                .db_factors
                .contains_key("sw_l2_main_moneyflow_buy_lg_amount")
        );

        let non_member = rows.iter().find(|row| row.ts_code == "000002.SZ").unwrap();
        assert_eq!(non_member.db_factors["market_index_sse50_member_flag"], 0.0);
        assert_eq!(non_member.db_factors["market_index_sse50_weight_pct"], 0.0);
        assert_eq!(
            non_member.db_factors["market_index_sse50_idx_macd_bfq_to_close_pct"],
            0.0
        );
        assert_eq!(
            non_member.db_factors["market_index_sse50_weighted_idx_macd_bfq_to_close_pct"],
            0.0
        );
        assert_eq!(non_member.db_factors["sw_l2_membership_current_flag"], 0.0);

        let zero_weight_member = rows.iter().find(|row| row.ts_code == "000003.SZ").unwrap();
        assert_eq!(
            zero_weight_member.db_factors["market_index_sse50_member_flag"],
            1.0
        );
        assert_eq!(
            zero_weight_member.db_factors["market_index_sse50_weight_pct"],
            0.0
        );
        assert_eq!(
            zero_weight_member.db_factors["market_index_sse50_idx_macd_bfq_to_close_pct"],
            20.0
        );
        assert_eq!(
            zero_weight_member.db_factors["market_index_sse50_weighted_idx_macd_bfq_to_close_pct"],
            0.0
        );

        client.execute_batch(
            "INSERT INTO stock_stk_factor_pro VALUES ('000004.SZ', DATE '2020-01-03', 0.2);
             INSERT INTO index_idx_factor_pro VALUES ('000016.SH', DATE '2020-01-03', 11.0, 0.1, 11.0);",
        )?;
        let before_weight_history_date = NaiveDate::from_ymd_opt(2020, 1, 3).unwrap();
        let mut before_weight_history = vec![db_native_market_row_from_values(DbNativeDailyRow {
            ts_code: "000004.SZ".to_string(),
            trade_date: before_weight_history_date,
            open: 10.0,
            high: 10.0,
            low: 10.0,
            close: 10.0,
            adj_factor: Some(1.0),
            vol: 1.0,
            turnover_rate: Some(1.0),
            db_factors: BTreeMap::new(),
        })?];
        merge_sw_l2_extras(
            &client,
            &query,
            before_weight_history_date,
            &mut before_weight_history,
        )?;
        let before_weight_history = &before_weight_history[0].db_factors;
        assert_eq!(before_weight_history["market_index_sse50_member_flag"], 0.0);
        assert_eq!(before_weight_history["market_index_sse50_weight_pct"], 0.0);
        assert_eq!(
            before_weight_history["market_index_sse50_idx_macd_bfq_to_close_pct"],
            0.0
        );
        assert_eq!(before_weight_history["market_index_bse50_member_flag"], 0.0);
        assert_eq!(before_weight_history["market_index_bse50_weight_pct"], 0.0);
        assert!(!before_weight_history.contains_key("market_index_bse50_idx_macd_bfq"));
        Ok(())
    }

    #[test]
    fn db_native_factor_queries_use_sw_l2_and_full_index_derivatives() {
        for fragment in [
            "FROM {{index_weight}} w",
            "max(w.trade_date) AS snapshot_date",
            "w.trade_date <= $1",
            "('000016.SH', 'sse50')",
            "('000905.SH', 'csi500')",
            "('000688.SH', 'sci50')",
            "('930050.CSI', 'csi_a50')",
            "('000922.CSI', 'csi_dividend')",
            "('000300.SH', 'csi300')",
            "('399303.SZ', 'guozheng2000')",
            "('399006.SZ', 'chinext')",
            "('899050.BJ', 'bse50')",
            "to_json(i)",
            "to_json(a)",
            "to_json(r)",
            "to_json(c)",
            "to_json(mf)",
            "s.trade_date >= m.in_date",
            "m.out_date IS NULL OR s.trade_date < m.out_date",
            "a.source_dataset = 'index_idx_factor_pro'",
            "a.calc_version = 'v3-macd-kdj-czsc-1'",
            "mf.source_dataset = 'stock_moneyflow'",
            "mf.calc_version = 'sw2021-l2-v1'",
        ] {
            assert!(
                DB_NATIVE_SW_L2_EXTRAS_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("000001.SH"));
        assert!(DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("399303.SZ"));
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("000001.SH"));
        assert!(!DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("399303.SZ"));
        assert!(!DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("stock_moneyflow_ths"));
        assert!(!DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("index_moneyflow_cnt_ths"));

        let factor_columns = db_native_index_context_factor_columns();
        assert!(
            factor_columns.len() < 2200,
            "unexpectedly wide index context: {}",
            factor_columns.len()
        );
        for factor in [
            "market_index_sse50_member_flag",
            "market_index_sse50_weight_pct",
            "market_index_sse50_idx_macd_bfq_to_close_pct",
            "market_index_sse50_weighted_idx_macd_bfq_to_close_pct",
            "market_index_sse50_calc_daily_indicators_daily_macd_dif_asof_to_close_pct",
            "market_index_csi300_member_flag",
            "market_index_csi300_weight_pct",
            "market_index_guozheng2000_idx_macd_bfq_to_close_pct",
            "market_index_chinext_weighted_idx_macd_bfq_to_close_pct",
            "market_index_bse50_calc_daily_czsc_structure_daily_recent_bi_count",
            "market_index_csi_dividend_calc_daily_indicators_weekly_kdj_k_asof",
            "sw_l2_main_index_idx_xsii_td4_bfq_to_close_pct",
            "sw_l2_main_index_calc_daily_rolling_factors_position_90d",
            "sw_l2_main_moneyflow_net_lg_amount_per_stock",
        ] {
            assert!(
                factor_columns.iter().any(|column| column == factor),
                "missing {factor}"
            );
        }
        assert!(DB_NATIVE_SW_L2_FACTOR_COLUMNS.contains(&"sw_l2_main_net_amount_per_stock"));
        assert!(
            !factor_columns
                .iter()
                .any(|column| column == "market_index_sse50_idx_close")
        );
        assert!(
            !factor_columns
                .iter()
                .any(|column| column == "market_index_sse50_weighted_idx_kdj_k_bfq")
        );
        assert!(
            !factor_columns
                .iter()
                .any(|column| column == "sw_l2_main_moneyflow_buy_lg_amount")
        );
        assert_eq!(
            factor_columns
                .iter()
                .filter(|column| column.contains("_weighted_"))
                .count(),
            INDEX_BENCHMARKS.len() * 4
        );
        assert!(
            !factor_columns
                .iter()
                .any(|column| column.contains("000016.SH"))
        );
    }

    #[test]
    fn db_native_moneyflow_queries_use_current_sources_and_units() {
        assert!(DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("FROM {{stock_moneyflow}} f"));
        assert!(DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("LEFT JOIN stock_moneyflow_recent smf"));
        assert!(DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("{{calc_daily_industry_moneyflow}}"));
        assert!(DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("{{index_sw_member}}"));
        assert!(DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("FROM {{index_weight}} w"));
        assert!(DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("w.con_code = s.ts_code"));
        assert!(DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("m.ts_code = s.ts_code"));
        assert!(DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("s.trade_date >= m.in_date"));
        assert!(
            DB_NATIVE_SW_L2_EXTRAS_QUERY
                .contains("m.out_date IS NULL OR s.trade_date < m.out_date")
        );
        assert!(DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("mf.industry_code = m.industry_code"));
        assert!(DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("mf.source_dataset = 'stock_moneyflow'"));
        assert!(!DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("stock_moneyflow_ths"));
        assert!(!DB_NATIVE_SW_L2_EXTRAS_QUERY.contains("index_moneyflow_cnt_ths"));
        assert!(DB_NATIVE_PICK_DATE_EXTRAS_QUERY.contains("s.amount / 10.0"));
    }

    #[test]
    fn resolve_previous_trade_date_query_uses_stock_cache_trade_dates() {
        for fragment in [
            "SELECT max(trade_date) AS trade_date",
            "FROM stock_stk_factor_pro",
            "WHERE trade_date < $1",
        ] {
            assert!(
                PREVIOUS_TRADE_DATE_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!PREVIOUS_TRADE_DATE_QUERY.contains("daily_market"));
        assert!(!PREVIOUS_TRADE_DATE_QUERY.contains("postgres://"));
        assert!(!PREVIOUS_TRADE_DATE_QUERY.contains("postgres://"));
        assert!(!PREVIOUS_TRADE_DATE_QUERY.contains("postgresql://"));
    }

    #[test]
    fn stock_period_macd_state_query_reads_completed_period_states_only() {
        for fragment in [
            "FROM calc_indicator_state p",
            "p.period_type = 'daily' AND p.period_end_date < $2",
            "p.period_type = 'weekly' AND p.period_end_date < date_trunc('week', $2::date)::date",
            "p.period_type = 'monthly' AND p.period_end_date < date_trunc('month', $2::date)::date",
            "p.calc_version = 'v3-macd-kdj-czsc-1'",
            "p.macd_period_count IS NOT NULL",
            "ORDER BY p.ts_code, p.period_type, p.period_end_date DESC",
        ] {
            assert!(
                STOCK_PERIOD_MACD_STATE_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("daily_asof"));
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("calc_daily_indicators"));
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("postgres://"));
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("postgres://"));
        assert!(!STOCK_PERIOD_MACD_STATE_QUERY.contains("postgresql://"));
    }

    #[test]
    fn instrument_info_queries_keep_stock_and_industry_scans_separate() {
        for fragment in [
            "WITH requested AS",
            "SELECT unnest($1::text[]) AS ts_code",
            "LEFT JOIN stock_basic s ON s.ts_code = r.ts_code",
            "NULLIF(trim(s.name), '') AS name",
        ] {
            assert!(
                STOCK_BASIC_INFO_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!STOCK_BASIC_INFO_QUERY.contains("index_sw_member"));
        for fragment in [
            "WITH requested AS",
            "JOIN index_sw_member m ON m.ts_code = r.ts_code",
            "m.l2_name AS industry",
            "m.out_date IS NULL",
        ] {
            assert!(
                SW_L2_INDUSTRY_QUERY.contains(fragment),
                "missing {fragment}"
            );
        }
        assert!(!SW_L2_INDUSTRY_QUERY.contains("stock_basic"));
        assert!(!SW_L2_INDUSTRY_QUERY.contains("index_ths"));
        assert!(!SW_L2_INDUSTRY_QUERY.contains("index_sw_l2_member"));
    }

    #[test]
    fn fetch_instrument_info_combines_names_and_sw_industries() {
        let temp = tempfile::tempdir().unwrap();
        let db_path = temp.path().join("instrument-info.duckdb");
        let stock_basic_csv = temp.path().join("stock-basic.csv");
        let sw_member_csv = temp.path().join("sw-member.csv");
        std::fs::write(&stock_basic_csv, "ts_code,name\n000001.SZ,平安银行\n").unwrap();
        std::fs::write(
            &sw_member_csv,
            "ts_code,l2_name,in_date,out_date\n000001.SZ,银行,2020-01-01,\n",
        )
        .unwrap();

        let environment = Environment::new().unwrap();
        let instance = Instance::new(&environment).unwrap();
        instance
            .attach(
                AttachBuilder::new(StorageLocation::OnDisk(
                    db_path.to_string_lossy().into_owned(),
                ))
                .options([("read_only", "false")])
                .make_default(),
            )
            .unwrap();
        let connection = instance.connect().unwrap();
        connection
            .execute(
                &format!(
                    "CREATE VIEW stock_basic AS SELECT * FROM read_csv_auto('{}')",
                    stock_basic_csv.display(),
                ),
                Parameters::None,
            )
            .unwrap();
        connection
            .execute(
                &format!(
                    "CREATE VIEW index_sw_member AS SELECT * FROM read_csv('{}', columns={{'ts_code':'VARCHAR','l2_name':'VARCHAR','in_date':'DATE','out_date':'DATE'}})",
                    sw_member_csv.display(),
                ),
                Parameters::None,
            )
            .unwrap();

        let instruments =
            fetch_instrument_info(db_path.to_str().unwrap(), &["000001.SZ".to_string()]).unwrap();

        assert_eq!(
            instruments.get("000001.SZ"),
            Some(&InstrumentInfo {
                name: Some("平安银行".to_string()),
                industry: Some("银行".to_string()),
            })
        );
    }

    #[test]
    fn db_native_fixture_row_maps_stock_cache_values_to_market_row() {
        let trade_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();
        let row = DbNativeDailyRow {
            ts_code: "000001.SZ".to_string(),
            trade_date,
            open: 10.1,
            high: 10.8,
            low: 9.9,
            close: 10.5,
            adj_factor: Some(1.25),
            vol: 123456.0,
            turnover_rate: Some(2.5),
            db_factors: [
                ("kdj_k_qfq".to_string(), Some(61.0)),
                ("kdj_d_qfq".to_string(), Some(52.0)),
                ("kdj_j_qfq".to_string(), Some(79.0)),
                ("dmi_adxr_qfq".to_string(), Some(22.0)),
                ("dmi_adx_qfq".to_string(), Some(25.0)),
                ("dmi_pdi_qfq".to_string(), Some(31.0)),
                ("dmi_mdi_qfq".to_string(), Some(19.0)),
                ("dmi_pdi_mdi_spread_qfq".to_string(), Some(12.0)),
                ("dmi_adx_adxr_gap_qfq".to_string(), Some(3.0)),
                ("wr_qfq".to_string(), Some(-12.5)),
                ("mtm_qfq".to_string(), Some(1.8)),
                ("roc_qfq".to_string(), Some(4.2)),
                ("trix_qfq".to_string(), Some(0.35)),
                ("obv_qfq".to_string(), Some(123456.0)),
                ("vr_qfq".to_string(), Some(135.0)),
                ("psy_qfq".to_string(), Some(66.7)),
                ("bias1_qfq".to_string(), Some(2.4)),
                ("macd_daily_dif".to_string(), Some(0.42)),
                ("macd_daily_dea".to_string(), Some(0.30)),
                ("macd_daily_hist".to_string(), Some(0.12)),
                ("macd_weekly_hist".to_string(), Some(0.34)),
                ("macd_monthly_hist".to_string(), Some(-0.08)),
                ("rolling_ma25_qfq".to_string(), Some(10.2)),
                ("rolling_position_90d".to_string(), Some(0.72)),
                ("close_to_20d_max_close_pct".to_string(), Some(-1.8)),
                ("rolling_range_compression_20d".to_string(), Some(0.16)),
                ("_czsc_snapshot_available".to_string(), Some(1.0)),
                ("_czsc_status_code".to_string(), Some(4.0)),
                ("_czsc_recent_peak_high".to_string(), Some(11.8)),
                ("_czsc_post_peak_first_bear_open".to_string(), Some(11.2)),
                ("sw_l2_membership_current_flag".to_string(), Some(1.0)),
                ("sw_l2_main_sector_rank".to_string(), Some(3.0)),
                ("sw_l2_main_pct_change".to_string(), Some(2.4)),
                ("sw_l2_main_net_amount_per_stock".to_string(), Some(1.2)),
                ("sw_l2_main_limit_up_count".to_string(), Some(8.0)),
                ("sw_l2_main_limit_days".to_string(), Some(2.0)),
                ("sw_l2_main_limit_pct_chg".to_string(), Some(5.6)),
                ("sw_l2_main_limit_rank".to_string(), Some(4.0)),
                ("sw_l2_main_macd_daily_hist".to_string(), Some(0.06)),
                ("sw_l2_sector_count".to_string(), Some(4.0)),
                ("sw_l2_best_pct_change".to_string(), Some(3.1)),
                ("sw_l2_avg_pct_change".to_string(), Some(1.7)),
                ("sw_l2_best_net_buy_amount".to_string(), Some(2.2)),
                ("sw_l2_avg_net_buy_amount".to_string(), Some(1.1)),
                ("sw_l2_best_net_sell_amount".to_string(), Some(0.9)),
                ("sw_l2_avg_net_sell_amount".to_string(), Some(0.4)),
                ("sw_l2_best_limit_up_count".to_string(), Some(12.0)),
                ("sw_l2_avg_limit_up_count".to_string(), Some(6.0)),
                ("sw_l2_any_limit_up_sector_flag".to_string(), Some(1.0)),
                ("sw_l2_limit_up_sector_count".to_string(), Some(3.0)),
                ("sw_l2_limit_up_sector_ratio".to_string(), Some(0.75)),
                ("sw_l2_best_limit_days".to_string(), Some(3.0)),
                ("sw_l2_best_limit_pct_chg".to_string(), Some(7.8)),
                ("sw_l2_avg_limit_pct_chg".to_string(), Some(4.9)),
                ("sw_l2_best_limit_rank".to_string(), Some(2.0)),
                ("stock_vs_sw_l2_main_pct_change".to_string(), Some(0.8)),
                ("stock_vs_sw_l2_avg_pct_change".to_string(), Some(1.5)),
                ("stock_env_sector_ret5_pct".to_string(), Some(6.2)),
                ("stock_env_sector_ret20_pct".to_string(), Some(12.4)),
                ("stock_env_sector_ma20_bias_pct".to_string(), Some(3.3)),
                ("stock_env_sector_vs_broad_ret5_pct".to_string(), Some(4.8)),
                ("stock_env_sector_vs_broad_ret20_pct".to_string(), Some(9.6)),
                ("stock_env_style_ret5_spread_pct".to_string(), Some(0.6)),
                (
                    "stock_env_market_sector_ret5_sum_pct".to_string(),
                    Some(7.6),
                ),
                ("stock_env_market_score".to_string(), Some(1.05)),
                ("stock_env_sector_score".to_string(), Some(3.4)),
                ("stock_env_alignment_score".to_string(), Some(1.0)),
                ("stock_env_limit_heat_score".to_string(), Some(1.75)),
                ("stock_env_overall_score".to_string(), Some(2.05)),
                ("stock_mf_net_amount".to_string(), Some(900.0)),
                ("stock_mf_net_d5_amount".to_string(), Some(1500.0)),
                ("stock_mf_buy_lg_amount".to_string(), Some(500.0)),
                ("stock_mf_buy_lg_amount_rate".to_string(), Some(5.0)),
                ("stock_mf_buy_md_amount".to_string(), Some(250.0)),
                ("stock_mf_buy_md_amount_rate".to_string(), Some(2.5)),
                ("stock_mf_buy_sm_amount".to_string(), Some(-100.0)),
                ("stock_mf_buy_sm_amount_rate".to_string(), Some(-1.0)),
                ("large_net_amount_to_amount_pct".to_string(), Some(1.5)),
                ("mid_net_amount_to_amount_pct".to_string(), Some(0.75)),
                ("small_net_amount_to_amount_pct".to_string(), Some(-0.3)),
                ("net_mf_amount_to_amount_pct".to_string(), Some(2.7)),
                ("market_sse_ret5_pct".to_string(), Some(1.1)),
                ("market_sse_ret20_pct".to_string(), Some(2.2)),
                ("market_sse_ma20_bias_pct".to_string(), Some(0.3)),
                ("market_sse_volatility20_pct".to_string(), Some(0.9)),
                ("market_cn2000_ret5_pct".to_string(), Some(1.7)),
                ("market_cn2000_ret20_pct".to_string(), Some(3.4)),
                ("market_cn2000_ma20_bias_pct".to_string(), Some(0.6)),
                ("market_cn2000_volatility20_pct".to_string(), Some(1.3)),
                ("market_broad_ret5_pct".to_string(), Some(1.4)),
                ("market_broad_ret20_pct".to_string(), Some(2.8)),
                ("market_broad_ma20_bias_pct".to_string(), Some(0.45)),
                ("market_broad_volatility20_pct".to_string(), Some(1.1)),
                ("ignored_nan".to_string(), Some(f64::NAN)),
                ("ignored_null".to_string(), None),
            ]
            .into_iter()
            .collect(),
        };

        let mapped = db_native_market_row_from_values(row).unwrap();

        assert_eq!(mapped.ts_code, "000001.SZ");
        assert_eq!(mapped.trade_date, trade_date);
        assert_eq!(mapped.open, 10.1);
        assert_eq!(mapped.high, 10.8);
        assert_eq!(mapped.low, 9.9);
        assert_eq!(mapped.close, 10.5);
        assert_eq!(mapped.vol, 123456.0);
        assert_eq!(mapped.turnover_rate, Some(2.5));
        assert_eq!(mapped.adj_factor, Some(1.25));
        assert_eq!(mapped.db_factors["kdj_k_qfq"], 61.0);
        assert_eq!(mapped.db_factors["kdj_d_qfq"], 52.0);
        assert_eq!(mapped.db_factors["kdj_j_qfq"], 79.0);
        assert_eq!(mapped.db_factors["dmi_adxr_qfq"], 22.0);
        assert_eq!(mapped.db_factors["dmi_adx_qfq"], 25.0);
        assert_eq!(mapped.db_factors["dmi_pdi_qfq"], 31.0);
        assert_eq!(mapped.db_factors["dmi_mdi_qfq"], 19.0);
        assert_eq!(mapped.db_factors["dmi_pdi_mdi_spread_qfq"], 12.0);
        assert_eq!(mapped.db_factors["dmi_adx_adxr_gap_qfq"], 3.0);
        assert_eq!(mapped.db_factors["wr_qfq"], -12.5);
        assert_eq!(mapped.db_factors["mtm_qfq"], 1.8);
        assert_eq!(mapped.db_factors["roc_qfq"], 4.2);
        assert_eq!(mapped.db_factors["trix_qfq"], 0.35);
        assert_eq!(mapped.db_factors["obv_qfq"], 123456.0);
        assert_eq!(mapped.db_factors["vr_qfq"], 135.0);
        assert_eq!(mapped.db_factors["psy_qfq"], 66.7);
        assert_eq!(mapped.db_factors["bias1_qfq"], 2.4);
        assert_eq!(mapped.db_factors["macd_daily_dif"], 0.42);
        assert_eq!(mapped.db_factors["macd_daily_dea"], 0.30);
        assert_eq!(mapped.db_factors["macd_daily_hist"], 0.12);
        assert_eq!(mapped.db_factors["macd_weekly_hist"], 0.34);
        assert_eq!(mapped.db_factors["macd_monthly_hist"], -0.08);
        assert_eq!(mapped.db_factors["rolling_ma25_qfq"], 10.2);
        assert_eq!(mapped.db_factors["rolling_position_90d"], 0.72);
        assert_eq!(mapped.db_factors["close_to_20d_max_close_pct"], -1.8);
        assert_eq!(mapped.db_factors["rolling_range_compression_20d"], 0.16);
        assert_eq!(mapped.db_factors["_czsc_snapshot_available"], 1.0);
        assert_eq!(mapped.db_factors["_czsc_status_code"], 4.0);
        assert_eq!(mapped.db_factors["_czsc_recent_peak_high"], 11.8);
        assert_eq!(mapped.db_factors["_czsc_post_peak_first_bear_open"], 11.2);
        assert_eq!(mapped.db_factors["sw_l2_membership_current_flag"], 1.0);
        assert_eq!(mapped.db_factors["sw_l2_main_sector_rank"], 3.0);
        assert_eq!(mapped.db_factors["sw_l2_main_pct_change"], 2.4);
        assert_eq!(mapped.db_factors["sw_l2_main_net_amount_per_stock"], 1.2);
        assert_eq!(mapped.db_factors["sw_l2_main_limit_up_count"], 8.0);
        assert_eq!(mapped.db_factors["sw_l2_main_limit_days"], 2.0);
        assert_eq!(mapped.db_factors["sw_l2_main_limit_pct_chg"], 5.6);
        assert_eq!(mapped.db_factors["sw_l2_main_limit_rank"], 4.0);
        assert_eq!(mapped.db_factors["sw_l2_main_macd_daily_hist"], 0.06);
        assert_eq!(mapped.db_factors["sw_l2_sector_count"], 4.0);
        assert_eq!(mapped.db_factors["sw_l2_best_pct_change"], 3.1);
        assert_eq!(mapped.db_factors["sw_l2_avg_pct_change"], 1.7);
        assert_eq!(mapped.db_factors["sw_l2_best_net_buy_amount"], 2.2);
        assert_eq!(mapped.db_factors["sw_l2_avg_net_buy_amount"], 1.1);
        assert_eq!(mapped.db_factors["sw_l2_best_net_sell_amount"], 0.9);
        assert_eq!(mapped.db_factors["sw_l2_avg_net_sell_amount"], 0.4);
        assert_eq!(mapped.db_factors["sw_l2_best_limit_up_count"], 12.0);
        assert_eq!(mapped.db_factors["sw_l2_avg_limit_up_count"], 6.0);
        assert_eq!(mapped.db_factors["sw_l2_any_limit_up_sector_flag"], 1.0);
        assert_eq!(mapped.db_factors["sw_l2_limit_up_sector_count"], 3.0);
        assert_eq!(mapped.db_factors["sw_l2_limit_up_sector_ratio"], 0.75);
        assert_eq!(mapped.db_factors["sw_l2_best_limit_days"], 3.0);
        assert_eq!(mapped.db_factors["sw_l2_best_limit_pct_chg"], 7.8);
        assert_eq!(mapped.db_factors["sw_l2_avg_limit_pct_chg"], 4.9);
        assert_eq!(mapped.db_factors["sw_l2_best_limit_rank"], 2.0);
        assert_eq!(mapped.db_factors["stock_vs_sw_l2_main_pct_change"], 0.8);
        assert_eq!(mapped.db_factors["stock_vs_sw_l2_avg_pct_change"], 1.5);
        assert_eq!(mapped.db_factors["stock_env_sector_ret5_pct"], 6.2);
        assert_eq!(mapped.db_factors["stock_env_sector_ret20_pct"], 12.4);
        assert_eq!(mapped.db_factors["stock_env_sector_ma20_bias_pct"], 3.3);
        assert_eq!(mapped.db_factors["stock_env_sector_vs_broad_ret5_pct"], 4.8);
        assert_eq!(
            mapped.db_factors["stock_env_sector_vs_broad_ret20_pct"],
            9.6
        );
        assert_eq!(mapped.db_factors["stock_env_style_ret5_spread_pct"], 0.6);
        assert_eq!(
            mapped.db_factors["stock_env_market_sector_ret5_sum_pct"],
            7.6
        );
        assert_eq!(mapped.db_factors["stock_env_market_score"], 1.05);
        assert_eq!(mapped.db_factors["stock_env_sector_score"], 3.4);
        assert_eq!(mapped.db_factors["stock_env_alignment_score"], 1.0);
        assert_eq!(mapped.db_factors["stock_env_limit_heat_score"], 1.75);
        assert_eq!(mapped.db_factors["stock_env_overall_score"], 2.05);
        assert_eq!(mapped.db_factors["stock_mf_net_amount"], 900.0);
        assert_eq!(mapped.db_factors["stock_mf_net_d5_amount"], 1500.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_lg_amount"], 500.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_lg_amount_rate"], 5.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_md_amount"], 250.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_md_amount_rate"], 2.5);
        assert_eq!(mapped.db_factors["stock_mf_buy_sm_amount"], -100.0);
        assert_eq!(mapped.db_factors["stock_mf_buy_sm_amount_rate"], -1.0);
        assert_eq!(mapped.db_factors["large_net_amount_to_amount_pct"], 1.5);
        assert_eq!(mapped.db_factors["mid_net_amount_to_amount_pct"], 0.75);
        assert_eq!(mapped.db_factors["small_net_amount_to_amount_pct"], -0.3);
        assert_eq!(mapped.db_factors["net_mf_amount_to_amount_pct"], 2.7);
        assert_eq!(mapped.db_factors["market_sse_ret5_pct"], 1.1);
        assert_eq!(mapped.db_factors["market_sse_ret20_pct"], 2.2);
        assert_eq!(mapped.db_factors["market_sse_ma20_bias_pct"], 0.3);
        assert_eq!(mapped.db_factors["market_sse_volatility20_pct"], 0.9);
        assert_eq!(mapped.db_factors["market_cn2000_ret5_pct"], 1.7);
        assert_eq!(mapped.db_factors["market_cn2000_ret20_pct"], 3.4);
        assert_eq!(mapped.db_factors["market_cn2000_ma20_bias_pct"], 0.6);
        assert_eq!(mapped.db_factors["market_cn2000_volatility20_pct"], 1.3);
        assert_eq!(mapped.db_factors["market_broad_ret5_pct"], 1.4);
        assert_eq!(mapped.db_factors["market_broad_ret20_pct"], 2.8);
        assert_eq!(mapped.db_factors["market_broad_ma20_bias_pct"], 0.45);
        assert_eq!(mapped.db_factors["market_broad_volatility20_pct"], 1.1);
        assert!(!mapped.db_factors.contains_key("ignored_nan"));
        assert!(!mapped.db_factors.contains_key("ignored_null"));
    }

    #[test]
    #[ignore = "需本地 .env 数据库；只读核对 2026-11-13 的 17 只 SCM 样本，使用临时 runtime"]
    fn scm_previous_month_macd_database_regression() -> anyhow::Result<()> {
        use crate::cache::prepared_cache_start_date;
        use crate::model::Method;
        use crate::screening::{
            PoolSource, ScreenRequest, run_db_native_screen_with_dataset_loader,
        };

        let codes = [
            "688475.SH",
            "601985.SH",
            "601668.SH",
            "601288.SH",
            "601077.SH",
            "600993.SH",
            "600900.SH",
            "600377.SH",
            "600028.SH",
            "600019.SH",
            "300138.SZ",
            "003816.SZ",
            "002299.SZ",
            "000999.SZ",
            "000895.SZ",
            "000429.SZ",
            "000423.SZ",
        ];
        let pick_date = NaiveDate::from_ymd_opt(2026, 11, 13).unwrap();
        let start_date = prepared_cache_start_date(pick_date);
        let duckdb_path = crate::config::resolve_duckdb_path_from_env(None)?;
        let client = open_duckdb(&duckdb_path)?;
        configure_daily_window_session(&client)?;
        let plan =
            preflight_db_native_load(&client, start_date, pick_date, &resolve_db_check_tables()?)?;
        let code_filter = codes.map(|code| format!("'{code}'")).join(", ");
        let scope_query = |query: &str| {
            format!(
                "SELECT sampled.* FROM ({}) sampled WHERE sampled.ts_code IN ({code_filter})",
                plan.adapt_query(query)
            )
        };
        let mut rows = client.query_map(
            &scope_query(DB_NATIVE_DAILY_WINDOW_QUERY),
            &[
                DuckDbParameter::Date(start_date),
                DuckDbParameter::Date(pick_date),
            ],
            db_native_market_row_from_db_row,
        )?;
        merge_pick_date_extras(
            &client,
            &scope_query(DB_NATIVE_PICK_DATE_EXTRAS_QUERY),
            pick_date,
            &mut rows,
        )?;
        merge_previous_month_macd(
            &client,
            &scope_query(DB_NATIVE_PREVIOUS_MONTH_MACD_QUERY),
            pick_date,
            &mut rows,
        )?;
        let root = tempfile::tempdir()?;
        let request = ScreenRequest {
            method: Method::Scm,
            pick_date,
            runtime_root: root.path().to_path_buf(),
            duckdb_path,
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: false,
            environment_state: None,
        };
        let output = run_db_native_screen_with_dataset_loader(request, |_, _, _| {
            Ok(MarketDataset {
                rows,
                db_data_gaps: plan.db_data_gaps,
            })
        })?;
        let result: serde_json::Value = serde_json::from_slice(&std::fs::read(output)?)?;
        assert_eq!(result["stats"]["total_symbols"], 17);
        assert_eq!(result["stats"]["fail_macd"], 0, "{result}");
        assert!(
            result["candidates"]
                .as_array()
                .unwrap()
                .iter()
                .any(|row| row["code"] == "601985.SH")
        );
        println!("SCM_MONTHLY_DATABASE_PROBE {}", result["stats"]);
        Ok(())
    }

    #[test]
    #[ignore = "需本地 .env 数据库；仅四只股票并使用临时 runtime"]
    fn historical_qfq_price_basis_samples_match_formal_czsc_and_reuse_cache() {
        let samples = [
            ("603409.SH", (2026, 1, 30)),
            ("003026.SZ", (2026, 2, 25)),
            ("301328.SZ", (2026, 2, 11)),
            ("688268.SH", (2026, 4, 20)),
        ];
        std::thread::scope(|scope| {
            let workers = samples
                .into_iter()
                .map(|(code, (year, month, day))| {
                    scope.spawn(move || {
                        historical_qfq_price_basis_probe(
                            code,
                            NaiveDate::from_ymd_opt(year, month, day).unwrap(),
                        )
                    })
                })
                .collect::<Vec<_>>();
            for worker in workers {
                let report = worker
                    .join()
                    .expect("price basis worker panicked")
                    .expect("price basis probe failed");
                println!("PRICE_BASIS_PROBE {report}");
            }
        });
    }

    fn historical_qfq_price_basis_probe(
        code: &str,
        pick_date: NaiveDate,
    ) -> anyhow::Result<serde_json::Value> {
        use crate::cache::{
            load_prepared_cache, prepared_cache_data_path, prepared_cache_meta_path,
            prepared_cache_start_date,
        };
        use crate::factors::registry::build_candidate_factor_rows;
        use crate::factors::types::FactorValue;
        use crate::model::{Candidate, Method};
        use crate::screening::{
            PoolSource, ScreenRequest, run_db_native_screen_with_dataset_loader,
        };

        let duckdb_path = crate::config::resolve_duckdb_path_from_env(None)?;
        let root = tempfile::tempdir()?;
        let start_date = prepared_cache_start_date(pick_date);
        let client = open_duckdb(&duckdb_path)?;
        configure_daily_window_session(&client)?;
        let plan =
            preflight_db_native_load(&client, start_date, pick_date, &resolve_db_check_tables()?)?;
        let scope_query = |query: &str| {
            format!(
                "SELECT sampled.* FROM ({}) sampled WHERE sampled.ts_code IN ('{code}', '000001.SZ')",
                plan.adapt_query(query)
            )
        };
        let mut rows = client.query_map(
            &scope_query(DB_NATIVE_DAILY_WINDOW_QUERY),
            &[
                DuckDbParameter::Date(start_date),
                DuckDbParameter::Date(pick_date),
            ],
            db_native_market_row_from_db_row,
        )?;
        merge_pick_date_extras(
            &client,
            &scope_query(DB_NATIVE_PICK_DATE_EXTRAS_QUERY),
            pick_date,
            &mut rows,
        )?;
        merge_sw_l2_extras(
            &client,
            &scope_query(DB_NATIVE_SW_L2_EXTRAS_QUERY),
            pick_date,
            &mut rows,
        )?;
        rows.sort_by_key(|row| row.trade_date);
        let latest = rows
            .iter()
            .rev()
            .find(|row| row.ts_code == code)
            .expect("sample history is empty");
        assert_eq!(latest.trade_date, pick_date);
        let close = latest.close;
        let qfq_close = latest.db_factors["_source_close_qfq"];
        let qfq_peak = latest.db_factors["_czsc_recent_peak_high"];
        let peak_day = latest.db_factors["_czsc_recent_peak_day"];
        let qfq_ma25 = latest.db_factors["rolling_ma25_qfq"];
        let qfq_dif = latest.db_factors["macd_daily_dif"];
        let expected_distance = 100.0 * (qfq_close / qfq_peak - 1.0);
        let multiplier = close / qfq_close;
        let expected_turnover = rows
            .iter()
            .rev()
            .filter(|row| row.ts_code == code)
            .take(43)
            .map(|row| (row.open + row.close) / 2.0 * row.vol)
            .sum::<f64>();
        let loaded_rows = rows.len();
        let request = |method| ScreenRequest {
            method,
            pick_date,
            runtime_root: root.path().to_path_buf(),
            duckdb_path: duckdb_path.clone(),
            recompute: false,
            write_prepared_cache: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            export_factors: true,
            environment_state: Some("weak".to_string()),
        };
        let candidate_path =
            run_db_native_screen_with_dataset_loader(request(Method::Scm), |_, _, _| {
                Ok(MarketDataset {
                    rows,
                    db_data_gaps: plan.db_data_gaps,
                })
            })?;
        let selected_scm: serde_json::Value =
            serde_json::from_slice(&std::fs::read(candidate_path)?)?;
        let prepared =
            load_prepared_cache(root.path(), Method::Scm, pick_date, start_date, pick_date)?
                .unwrap();
        let latest = prepared
            .iter()
            .rev()
            .find(|row| row.ts_code == code)
            .unwrap();
        assert_eq!(latest.close, close);
        assert!((latest.ma25.unwrap() - qfq_ma25 * multiplier).abs() < 1e-8);
        assert!((latest.dif - qfq_dif * multiplier).abs() < 1e-8);
        assert!((latest.turnover_n / expected_turnover - 1.0).abs() < 1e-10);
        assert!(
            prepared
                .iter()
                .all(|row| !row.db_factors.contains_key("_source_close_qfq"))
        );
        let local_ma25 = prepared
            .iter()
            .rev()
            .filter(|row| row.ts_code == code)
            .take(25)
            .map(|row| row.close)
            .sum::<f64>()
            / 25.0;
        assert!((latest.ma25.unwrap() - local_ma25).abs() < 0.0001 * multiplier);
        let factors = build_candidate_factor_rows(
            &[Candidate {
                code: code.to_string(),
                pick_date,
                close,
                turnover_n: latest.turnover_n,
                signal: Some("SCM".to_string()),
            }],
            &prepared,
            Method::Scm,
            Some("weak"),
        );
        let FactorValue::Number(actual_distance) =
            factors[0].factors["czsc_close_to_recent_peak_pct"]
        else {
            panic!("formal peak distance is missing");
        };
        assert!(
            (100.0 * (latest.close / latest.db_factors["_czsc_recent_peak_high"] - 1.0)
                - expected_distance)
                .abs()
                < 1e-9
        );
        assert!(
            (actual_distance - expected_distance).abs() < 0.00005,
            "{code}: exported={actual_distance} expected={expected_distance}"
        );
        let data_path = prepared_cache_data_path(root.path(), pick_date);
        let meta_path = prepared_cache_meta_path(root.path(), pick_date);
        let data_before = std::fs::read(&data_path)?;
        let meta_before = std::fs::read(&meta_path)?;
        let data_modified = std::fs::metadata(&data_path)?.modified()?;
        let meta_modified = std::fs::metadata(&meta_path)?.modified()?;
        let pbm_path =
            run_db_native_screen_with_dataset_loader(request(Method::Pbm), |_, _, _| {
                panic!("PBM must reuse the corrected SCM cache without loading the database")
            })?;
        let selected_pbm: serde_json::Value = serde_json::from_slice(&std::fs::read(pbm_path)?)?;
        assert_eq!(std::fs::read(&data_path)?, data_before);
        assert_eq!(std::fs::read(&meta_path)?, meta_before);
        assert_eq!(std::fs::metadata(data_path)?.modified()?, data_modified);
        assert_eq!(std::fs::metadata(meta_path)?.modified()?, meta_modified);
        Ok(serde_json::json!({
            "code": code, "pick_date": pick_date, "rows_loaded": loaded_rows,
            "raw_close": close, "source_close_qfq": qfq_close,
            "peak_day": peak_day, "source_peak_qfq": qfq_peak,
            "aligned_peak": latest.db_factors["_czsc_recent_peak_high"],
            "old_distance_pct": 100.0 * (close / qfq_peak - 1.0),
            "new_distance_pct": actual_distance, "expected_distance_pct": expected_distance,
            "old_ma25_distance_pct": 100.0 * (close / qfq_ma25 - 1.0),
            "new_ma25_distance_pct": 100.0 * (close / latest.ma25.unwrap() - 1.0),
            "ma25_after": latest.ma25, "local_ma25": local_ma25,
            "dif_before": qfq_dif, "dif_after": latest.dif,
            "selected_scm": selected_scm["candidates"].as_array().unwrap().iter().any(|row| row["code"] == code),
            "selected_pbm": selected_pbm["candidates"].as_array().unwrap().iter().any(|row| row["code"] == code),
            "shared_cache_untouched": true,
        }))
    }

    #[test]
    fn db_native_loader_reads_local_stock_cache_when_duckdb_path_is_available() {
        let Ok(duckdb_path) = std::env::var("DUCKDB_PATH") else {
            eprintln!("skipping local stock-cache DB-native loader probe: DUCKDB_PATH is not set");
            return;
        };
        let pick_date = NaiveDate::from_ymd_opt(2026, 6, 15).unwrap();

        let rows = fetch_db_native_daily_window(&duckdb_path, pick_date, pick_date).unwrap();

        assert!(!rows.is_empty());
        let row = rows
            .iter()
            .find(|row| row.trade_date == pick_date)
            .expect("loader should return pick-date rows");
        assert!(row.open.is_finite());
        assert!(row.high.is_finite());
        assert!(row.low.is_finite());
        assert!(row.close.is_finite());
        assert!(row.db_factors.contains_key("kdj_k_qfq"));
        assert!(row.db_factors.contains_key("kdj_d_qfq"));
        assert!(row.db_factors.contains_key("kdj_j_qfq"));
        assert!(row.db_factors.contains_key("dmi_adx_qfq"));
        assert!(row.db_factors.contains_key("dmi_pdi_mdi_spread_qfq"));
        assert!(row.db_factors.contains_key("trix_qfq"));
        assert!(row.db_factors.contains_key("macd_daily_hist"));
        assert!(row.db_factors.contains_key("macd_weekly_hist"));
        assert!(row.db_factors.contains_key("macd_monthly_hist"));
        assert!(row.db_factors.contains_key("rolling_position_90d"));
        assert!(row.db_factors.contains_key("close_to_20d_max_close_pct"));
        assert!(row.db_factors.contains_key("_czsc_snapshot_available"));
        assert!(row.db_factors.contains_key("_czsc_status_code"));
        assert!(
            !row.db_factors
                .keys()
                .any(|key| key.starts_with("left_peak_"))
        );
        assert!(row.db_factors.contains_key("stock_mf_net_amount"));
        assert!(
            row.db_factors
                .contains_key("large_net_amount_to_amount_pct")
        );
        assert!(row.db_factors.contains_key("mid_net_amount_to_amount_pct"));
        assert!(
            row.db_factors
                .contains_key("small_net_amount_to_amount_pct")
        );
        assert!(row.db_factors.contains_key("net_mf_amount_to_amount_pct"));
        assert!(row.db_factors.contains_key("sw_l2_main_limit_up_count"));
        assert!(row.db_factors.contains_key("sw_l2_best_limit_up_count"));
        assert!(
            row.db_factors
                .contains_key("sw_l2_any_limit_up_sector_flag")
        );
        assert!(row.db_factors.contains_key("sw_l2_limit_up_sector_count"));
        assert!(row.db_factors.contains_key("sw_l2_limit_up_sector_ratio"));
        assert!(row.db_factors.contains_key("stock_env_sector_ret5_pct"));
        assert!(
            row.db_factors
                .contains_key("stock_env_sector_vs_broad_ret5_pct")
        );
        assert!(
            row.db_factors
                .contains_key("stock_env_style_ret5_spread_pct")
        );
        assert!(row.db_factors.contains_key("stock_env_market_score"));
        assert!(row.db_factors.contains_key("stock_env_sector_score"));
        assert!(row.db_factors.contains_key("stock_env_alignment_score"));
        assert!(row.db_factors.contains_key("stock_env_limit_heat_score"));
        assert!(row.db_factors.contains_key("stock_env_overall_score"));
        assert!(row.db_factors.contains_key("market_sse_ret5_pct"));
        assert!(row.db_factors.contains_key("market_cn2000_ret5_pct"));
        assert!(row.db_factors.contains_key("market_broad_ret5_pct"));
    }

    #[test]
    fn db_native_window_session_settings_bound_duckdb_threads_and_memory() {
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("SET threads = 4"));
        assert!(DAILY_WINDOW_SESSION_SETTINGS_SQL.contains("SET memory_limit = '1GB'"));
    }
}
#[cfg(test)]
mod duckdb_neo_tests {
    use super::{DuckDbParameter, NaiveDate, open_duckdb};

    #[test]
    fn duckdb_query_maps_date_parameters_and_integer_columns() {
        let connection = open_duckdb(":memory:").unwrap();
        let trade_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
        let row = connection
            .query_rows(
                "SELECT $1::DATE AS trade_date, 3::INTEGER AS period_count",
                &[DuckDbParameter::Date(trade_date)],
            )
            .unwrap()
            .remove(0);

        assert_eq!(row.try_get::<NaiveDate>("trade_date").unwrap(), trade_date);
        assert_eq!(row.try_get::<i32>("period_count").unwrap(), 3);
    }

    #[test]
    fn duckdb_query_for_each_visits_multiple_chunks_in_order() {
        let connection = open_duckdb(":memory:").unwrap();
        let mut visited = Vec::new();

        connection
            .query_for_each(
                "SELECT i::BIGINT AS row_id, CASE WHEN i % 2 = 0 THEN i::DOUBLE ELSE NULL END AS maybe_id, 'row-' || i::VARCHAR AS label FROM range(5000) AS rows(i) ORDER BY i",
                &[],
                |row| {
                    Ok((
                        row.try_get::<i64>("row_id")?,
                        row.try_get::<Option<f64>>("maybe_id")?,
                        row.try_get::<String>("label")?,
                    ))
                },
                |row| {
                    visited.push(row);
                    Ok(())
                },
            )
            .unwrap();

        assert_eq!(visited.len(), 5000);
        assert_eq!(visited[0], (0, Some(0.0), "row-0".to_string()));
        assert_eq!(visited[1], (1, None, "row-1".to_string()));
        assert_eq!(visited[4999], (4999, None, "row-4999".to_string()));
        assert!(visited.windows(2).all(|pair| pair[0].0 + 1 == pair[1].0));
    }
}
