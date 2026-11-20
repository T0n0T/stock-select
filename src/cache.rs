use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::SystemTime;

use arrow::array::{Array, ArrayRef, BooleanArray, Date32Array, Float64Array, StringArray};
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use arrow::record_batch::RecordBatch;
use bytes::Bytes;
use chrono::{Datelike, NaiveDate};
use parquet::arrow::ArrowWriter;
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::basic::Compression;
use parquet::file::properties::WriterProperties;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::model::{DbDataGap, Method, PreparedDataset, PreparedRow, db_data_gap_warning_message};

pub const PREPARED_CACHE_ARTIFACT_VERSION: u32 = 1;
pub const PREPARED_CACHE_SCHEMA_VERSION: u32 = 14;
pub const DB_NATIVE_PREPARED_CACHE_SOURCE: &str = "stock-cache-db-native";
pub const LOCAL_DERIVED_PREPARED_CACHE_SOURCE: &str = "prepared-local-derived";
pub const DEFAULT_PREPARED_CACHE_RETENTION_LIMIT: usize = 30;
pub const PREPARED_CACHE_RETENTION_LIMIT_ENV: &str = "STOCK_SELECT_PREPARED_CACHE_LIMIT";
pub const MIN_DB_NATIVE_WINDOW_TRADING_DAYS: u32 = 235;
const DB_NATIVE_MACD_CALC_VERSION: &str = "macd_qfq_12_26_9_v1";
const DB_NATIVE_ROLLING_CALC_VERSION: &str = "rolling_qfq_v1";
const DB_NATIVE_CZSC_CALC_VERSION: &str = "czsc_structure_qfq_min6_r7_v1";
const DB_NATIVE_PRICE_BASIS_VERSION: &str = "asof_qfq_v1";
const DB_NATIVE_MONTHLY_MACD_HISTORY_VERSION: &str = "previous_completed_month_v1";
const PARQUET_MAGIC: &[u8; 4] = b"PAR1";
const PREPARED_CACHE_BATCH_SIZE: usize = 4096;

static WARNED_PREPARED_CACHE_GAPS: OnceLock<Mutex<BTreeSet<String>>> = OnceLock::new();

pub fn prepared_cache_start_date(end_date: NaiveDate) -> NaiveDate {
    date_years_before(end_date, 1)
}

fn date_years_before(date: NaiveDate, years: i32) -> NaiveDate {
    let target_year = date.year() - years;
    let mut day = date.day();
    loop {
        if let Some(value) = NaiveDate::from_ymd_opt(target_year, date.month(), day) {
            return value;
        }
        day -= 1;
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PreparedCachePaths {
    pub data_path: PathBuf,
    pub meta_path: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PreparedCacheMetadata {
    pub artifact_version: u32,
    pub method: String,
    pub shared_methods: Vec<String>,
    pub pick_date: NaiveDate,
    pub start_date: NaiveDate,
    pub end_date: NaiveDate,
    pub schema_version: u32,
    pub row_count: usize,
    pub symbol_count: usize,
    pub source_table: String,
    #[serde(default)]
    pub mode: Option<String>,
    #[serde(default)]
    pub source: Option<String>,
    #[serde(default)]
    pub run_id: Option<String>,
    #[serde(default)]
    pub previous_trade_date: Option<NaiveDate>,
    #[serde(default)]
    pub compression: Option<String>,
    #[serde(default)]
    pub encoding: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub window_trading_days: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub window_start_date: Option<NaiveDate>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub window_end_date: Option<NaiveDate>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub calc_versions: BTreeMap<String, String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub membership_sources: BTreeMap<String, String>,
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub db_data_gaps: BTreeMap<String, DbDataGap>,
}

pub fn prepared_cache_data_path(runtime_root: &Path, pick_date: NaiveDate) -> PathBuf {
    prepared_cache_paths(runtime_root, pick_date, false).data_path
}

pub fn prepared_cache_meta_path(runtime_root: &Path, pick_date: NaiveDate) -> PathBuf {
    prepared_cache_paths(runtime_root, pick_date, false).meta_path
}

pub fn prepared_cache_paths(
    runtime_root: &Path,
    pick_date: NaiveDate,
    intraday: bool,
) -> PreparedCachePaths {
    let suffix = if intraday { ".intraday" } else { "" };
    let base_name = format!("{}{}", pick_date.format("%Y-%m-%d"), suffix);
    let dir = runtime_root.join("prepared");
    PreparedCachePaths {
        data_path: dir.join(format!("{base_name}.parquet")),
        meta_path: dir.join(format!("{base_name}.meta.json")),
    }
}

pub fn candidate_output_path(runtime_root: &Path, pick_date: NaiveDate, method: Method) -> PathBuf {
    runtime_root.join("candidates").join(format!(
        "{}.{}.json",
        pick_date.format("%Y-%m-%d"),
        method.as_str()
    ))
}

pub fn write_prepared_cache(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    rows: &[PreparedRow],
) -> anyhow::Result<()> {
    write_prepared_cache_for_mode(
        runtime_root,
        method,
        pick_date,
        start_date,
        end_date,
        false,
        rows,
    )
}

pub fn write_db_native_prepared_cache(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    window_trading_days: u32,
    rows: &[PreparedRow],
) -> anyhow::Result<()> {
    write_db_native_prepared_cache_parts(
        runtime_root,
        method,
        pick_date,
        start_date,
        end_date,
        window_trading_days,
        rows,
        &BTreeMap::new(),
    )
}

pub fn write_db_native_prepared_dataset(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    window_trading_days: u32,
    dataset: &PreparedDataset,
) -> anyhow::Result<()> {
    write_db_native_prepared_cache_parts(
        runtime_root,
        method,
        pick_date,
        start_date,
        end_date,
        window_trading_days,
        &dataset.rows,
        &dataset.db_data_gaps,
    )
}

fn write_db_native_prepared_cache_parts(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    window_trading_days: u32,
    rows: &[PreparedRow],
    db_data_gaps: &BTreeMap<String, DbDataGap>,
) -> anyhow::Result<()> {
    let paths = prepared_cache_paths(runtime_root, pick_date, false);
    write_prepared_cache_rows_file(&paths.data_path, rows)?;
    write_json(
        &paths.meta_path,
        &build_db_native_metadata(
            method,
            pick_date,
            start_date,
            end_date,
            window_trading_days,
            rows,
            db_data_gaps,
        ),
    )?;
    prune_eod_prepared_cache_to_limit(runtime_root, prepared_cache_retention_limit()?)?;
    Ok(())
}

pub(crate) struct DbNativePreparedCacheStreamWriter {
    writer: Option<ArrowWriter<std::fs::File>>,
    schema: SchemaRef,
    factor_keys: Vec<String>,
    runtime_root: PathBuf,
    data_path: PathBuf,
    temp_data_path: PathBuf,
    meta_path: PathBuf,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    requested_window_trading_days: u32,
    db_data_gaps: BTreeMap<String, DbDataGap>,
}

impl DbNativePreparedCacheStreamWriter {
    pub(crate) fn new(
        runtime_root: &Path,
        method: Method,
        pick_date: NaiveDate,
        start_date: NaiveDate,
        end_date: NaiveDate,
        requested_window_trading_days: u32,
        mut factor_keys: Vec<String>,
        db_data_gaps: BTreeMap<String, DbDataGap>,
    ) -> anyhow::Result<Self> {
        let paths = prepared_cache_paths(runtime_root, pick_date, false);
        if let Some(parent) = paths.data_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        let temp_data_path = paths.data_path.with_file_name(format!(
            ".{}.{}.tmp",
            paths
                .data_path
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("prepared.parquet"),
            std::process::id()
        ));
        let file = std::fs::File::create(&temp_data_path)?;
        let properties = WriterProperties::builder()
            .set_compression(Compression::ZSTD(Default::default()))
            .build();
        factor_keys.sort_unstable();
        let schema = prepared_cache_schema(&factor_keys);
        let writer = ArrowWriter::try_new(file, schema.clone(), Some(properties))?;
        Ok(Self {
            writer: Some(writer),
            schema,
            factor_keys,
            runtime_root: runtime_root.to_path_buf(),
            data_path: paths.data_path,
            temp_data_path,
            meta_path: paths.meta_path,
            method,
            pick_date,
            start_date,
            end_date,
            requested_window_trading_days,
            db_data_gaps,
        })
    }

    pub(crate) fn write_rows(&mut self, rows: &[PreparedRow]) -> anyhow::Result<()> {
        for key in rows.iter().flat_map(|row| row.db_factors.keys()) {
            if self.factor_keys.binary_search(key).is_err() {
                anyhow::bail!("prepared cache stream found a factor absent from its schema: {key}");
            }
        }
        let writer = self
            .writer
            .as_mut()
            .expect("prepared cache stream writer is open");
        for chunk in rows.chunks(PREPARED_CACHE_BATCH_SIZE) {
            writer.write(&prepared_rows_record_batch_optimized(
                chunk,
                &self.factor_keys,
                self.schema.clone(),
            )?)?;
        }
        Ok(())
    }

    pub(crate) fn set_db_data_gaps(&mut self, db_data_gaps: BTreeMap<String, DbDataGap>) {
        self.db_data_gaps = db_data_gaps;
    }

    pub(crate) fn finish(
        mut self,
        row_count: usize,
        symbol_count: usize,
        trade_dates: &BTreeSet<NaiveDate>,
    ) -> anyhow::Result<()> {
        self.writer
            .take()
            .expect("prepared cache stream writer is open")
            .close()?;
        std::fs::rename(&self.temp_data_path, &self.data_path)?;
        let prepared_window = Some((
            *trade_dates.first().unwrap_or(&self.start_date),
            *trade_dates.last().unwrap_or(&self.end_date),
            u32::try_from(trade_dates.len()).unwrap_or(self.requested_window_trading_days),
        ));
        write_json(
            &self.meta_path,
            &build_db_native_metadata_from_counts(
                self.method,
                self.pick_date,
                self.start_date,
                self.end_date,
                row_count,
                symbol_count,
                prepared_window,
                self.requested_window_trading_days,
                &self.db_data_gaps,
            ),
        )?;
        prune_eod_prepared_cache_to_limit(&self.runtime_root, prepared_cache_retention_limit()?)?;
        Ok(())
    }
}

impl Drop for DbNativePreparedCacheStreamWriter {
    fn drop(&mut self) {
        self.writer.take();
        let _ = std::fs::remove_file(&self.temp_data_path);
    }
}

pub fn write_prepared_cache_for_mode(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    intraday: bool,
    rows: &[PreparedRow],
) -> anyhow::Result<()> {
    write_prepared_cache_parts(
        runtime_root,
        method,
        pick_date,
        start_date,
        end_date,
        intraday,
        rows,
        &BTreeMap::new(),
    )
}

pub fn write_prepared_dataset_for_mode(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    intraday: bool,
    dataset: &PreparedDataset,
) -> anyhow::Result<()> {
    write_prepared_cache_parts(
        runtime_root,
        method,
        pick_date,
        start_date,
        end_date,
        intraday,
        &dataset.rows,
        &dataset.db_data_gaps,
    )
}

fn write_prepared_cache_parts(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    intraday: bool,
    rows: &[PreparedRow],
    db_data_gaps: &BTreeMap<String, DbDataGap>,
) -> anyhow::Result<()> {
    let retention_limit = if intraday {
        None
    } else {
        Some(prepared_cache_retention_limit()?)
    };
    let paths = prepared_cache_paths(runtime_root, pick_date, intraday);
    write_prepared_cache_rows_file(&paths.data_path, rows)?;
    write_json(
        &paths.meta_path,
        &build_metadata(
            method,
            pick_date,
            start_date,
            end_date,
            intraday,
            rows,
            db_data_gaps,
        ),
    )?;
    if let Some(limit) = retention_limit {
        prune_eod_prepared_cache_to_limit(runtime_root, limit)?;
    }
    Ok(())
}

pub fn prepared_cache_retention_limit() -> anyhow::Result<usize> {
    let env_value = std::env::var(PREPARED_CACHE_RETENTION_LIMIT_ENV).ok();
    let dotenv = std::fs::read_to_string(".env").unwrap_or_default();
    prepared_cache_retention_limit_from_sources(env_value.as_deref(), &dotenv)
}

pub fn prepared_cache_retention_limit_from_sources(
    env_value: Option<&str>,
    dotenv_content: &str,
) -> anyhow::Result<usize> {
    let value = crate::config::resolve_config_value_from(
        None,
        env_value,
        dotenv_content,
        PREPARED_CACHE_RETENTION_LIMIT_ENV,
    );
    let Some(value) = value else {
        return Ok(DEFAULT_PREPARED_CACHE_RETENTION_LIMIT);
    };
    let limit = value.parse::<usize>().map_err(|err| {
        anyhow::anyhow!("{PREPARED_CACHE_RETENTION_LIMIT_ENV} must be a positive integer: {err}")
    })?;
    if limit == 0 {
        anyhow::bail!("{PREPARED_CACHE_RETENTION_LIMIT_ENV} must be a positive integer");
    }
    Ok(limit)
}

pub fn prune_eod_prepared_cache_to_limit(
    runtime_root: &Path,
    limit: usize,
) -> anyhow::Result<usize> {
    let prepared_dir = runtime_root.join("prepared");
    if !prepared_dir.exists() {
        return Ok(0);
    }
    let mut artifacts = Vec::new();
    for entry in std::fs::read_dir(&prepared_dir)? {
        let entry = entry?;
        let path = entry.path();
        let Some(file_name) = path.file_name().and_then(|value| value.to_str()) else {
            continue;
        };
        if !file_name.ends_with(".meta.json") || file_name.contains(".intraday.") {
            continue;
        }
        let Ok(bytes) = std::fs::read(&path) else {
            continue;
        };
        let Ok(metadata) = serde_json::from_slice::<PreparedCacheMetadata>(&bytes) else {
            continue;
        };
        if metadata.mode.as_deref() == Some("intraday_snapshot") {
            continue;
        }
        let created_at = prepared_cache_artifact_time(&path)?;
        artifacts.push((created_at, metadata.pick_date, path));
    }
    artifacts.sort_by(|left, right| {
        right
            .0
            .cmp(&left.0)
            .then_with(|| right.1.cmp(&left.1))
            .then_with(|| right.2.cmp(&left.2))
    });

    let mut removed = 0;
    for (_created_at, pick_date, meta_path) in artifacts.into_iter().skip(limit) {
        let paths = prepared_cache_paths(runtime_root, pick_date, false);
        remove_file_if_exists(&paths.data_path)?;
        remove_file_if_exists(&meta_path)?;
        removed += 1;
    }
    Ok(removed)
}

fn prepared_cache_artifact_time(path: &Path) -> anyhow::Result<SystemTime> {
    Ok(std::fs::metadata(path)?.modified()?)
}

fn remove_file_if_exists(path: &Path) -> anyhow::Result<()> {
    match std::fs::remove_file(path) {
        Ok(()) => Ok(()),
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(err) => Err(err.into()),
    }
}

fn build_metadata(
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    intraday: bool,
    rows: &[PreparedRow],
    db_data_gaps: &BTreeMap<String, DbDataGap>,
) -> PreparedCacheMetadata {
    let symbol_count = rows
        .iter()
        .map(|row| row.ts_code.as_str())
        .collect::<BTreeSet<_>>()
        .len();
    build_metadata_from_counts(
        method,
        pick_date,
        start_date,
        end_date,
        intraday,
        rows.len(),
        symbol_count,
        db_data_gaps,
    )
}

fn build_metadata_from_counts(
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    intraday: bool,
    row_count: usize,
    symbol_count: usize,
    db_data_gaps: &BTreeMap<String, DbDataGap>,
) -> PreparedCacheMetadata {
    PreparedCacheMetadata {
        artifact_version: PREPARED_CACHE_ARTIFACT_VERSION,
        method: method.as_str().to_string(),
        shared_methods: vec!["b2".to_string(), "scm".to_string(), "pbm".to_string()],
        pick_date,
        start_date,
        end_date,
        schema_version: PREPARED_CACHE_SCHEMA_VERSION,
        row_count,
        symbol_count,
        source_table: LOCAL_DERIVED_PREPARED_CACHE_SOURCE.to_string(),
        mode: intraday.then(|| "intraday_snapshot".to_string()),
        source: intraday.then(|| "tushare_rt_k".to_string()),
        run_id: None,
        previous_trade_date: None,
        compression: Some("zstd".to_string()),
        encoding: Some("parquet".to_string()),
        window_trading_days: None,
        window_start_date: None,
        window_end_date: None,
        calc_versions: BTreeMap::new(),
        membership_sources: BTreeMap::new(),
        db_data_gaps: db_data_gaps.clone(),
    }
}

fn build_db_native_metadata(
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    requested_window_trading_days: u32,
    rows: &[PreparedRow],
    db_data_gaps: &BTreeMap<String, DbDataGap>,
) -> PreparedCacheMetadata {
    let symbol_count = rows
        .iter()
        .map(|row| row.ts_code.as_str())
        .collect::<BTreeSet<_>>()
        .len();
    build_db_native_metadata_from_counts(
        method,
        pick_date,
        start_date,
        end_date,
        rows.len(),
        symbol_count,
        prepared_row_window(rows),
        requested_window_trading_days,
        db_data_gaps,
    )
}

fn build_db_native_metadata_from_counts(
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    row_count: usize,
    symbol_count: usize,
    prepared_window: Option<(NaiveDate, NaiveDate, u32)>,
    requested_window_trading_days: u32,
    db_data_gaps: &BTreeMap<String, DbDataGap>,
) -> PreparedCacheMetadata {
    let mut metadata = build_metadata_from_counts(
        method,
        pick_date,
        start_date,
        end_date,
        false,
        row_count,
        symbol_count,
        db_data_gaps,
    );
    metadata.source_table = DB_NATIVE_PREPARED_CACHE_SOURCE.to_string();
    metadata.source = Some(DB_NATIVE_PREPARED_CACHE_SOURCE.to_string());
    let (window_start_date, window_end_date, window_trading_days) =
        prepared_window.unwrap_or((start_date, end_date, requested_window_trading_days));
    metadata.start_date = window_start_date;
    metadata.end_date = window_end_date;
    metadata.window_trading_days = Some(window_trading_days);
    metadata.window_start_date = Some(window_start_date);
    metadata.window_end_date = Some(window_end_date);
    metadata.calc_versions = BTreeMap::from([
        ("macd".to_string(), DB_NATIVE_MACD_CALC_VERSION.to_string()),
        (
            "rolling".to_string(),
            DB_NATIVE_ROLLING_CALC_VERSION.to_string(),
        ),
        ("czsc".to_string(), DB_NATIVE_CZSC_CALC_VERSION.to_string()),
        (
            "price_basis".to_string(),
            DB_NATIVE_PRICE_BASIS_VERSION.to_string(),
        ),
        (
            "monthly_macd_history".to_string(),
            DB_NATIVE_MONTHLY_MACD_HISTORY_VERSION.to_string(),
        ),
    ]);
    metadata.membership_sources =
        BTreeMap::from([("ths".to_string(), "current_index_ths_member".to_string())]);
    metadata
}

fn prepared_row_window(rows: &[PreparedRow]) -> Option<(NaiveDate, NaiveDate, u32)> {
    let dates = rows
        .iter()
        .map(|row| row.trade_date)
        .collect::<BTreeSet<_>>();
    let start_date = dates.first().copied()?;
    let end_date = dates.last().copied()?;
    let trading_days = u32::try_from(dates.len()).ok()?;
    Some((start_date, end_date, trading_days))
}

fn write_prepared_cache_rows_file(path: &Path, rows: &[PreparedRow]) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let file = std::fs::File::create(path)?;
    let properties = WriterProperties::builder()
        .set_compression(Compression::ZSTD(Default::default()))
        .build();
    let factor_keys = prepared_cache_factor_keys(rows);
    let schema = prepared_cache_schema(&factor_keys);
    let mut writer = ArrowWriter::try_new(file, schema.clone(), Some(properties))?;
    for chunk in rows.chunks(PREPARED_CACHE_BATCH_SIZE) {
        writer.write(&prepared_rows_record_batch_optimized(
            chunk,
            &factor_keys,
            schema.clone(),
        )?)?;
    }
    writer.close()?;
    Ok(())
}

fn prepared_cache_factor_keys(rows: &[PreparedRow]) -> Vec<String> {
    prepared_cache_factor_keys_optimized(rows)
}

fn prepared_cache_factor_keys_optimized(rows: &[PreparedRow]) -> Vec<String> {
    let mut keys = rows
        .iter()
        .flat_map(|row| row.db_factors.keys().map(String::as_str))
        .collect::<HashSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    keys.sort_unstable();
    keys.into_iter().map(str::to_owned).collect()
}

fn prepared_cache_schema(factor_keys: &[String]) -> SchemaRef {
    let field = |name, data_type, nullable| Field::new(name, data_type, nullable);
    let mut fields = vec![
        field("ts_code", DataType::Utf8, false),
        field("trade_date", DataType::Date32, false),
        field("open", DataType::Float64, false),
        field("high", DataType::Float64, false),
        field("low", DataType::Float64, false),
        field("close", DataType::Float64, false),
        field("volume", DataType::Float64, false),
        field("turnover_n", DataType::Float64, false),
        field("turnover_rate", DataType::Float64, true),
        field("k", DataType::Float64, false),
        field("d", DataType::Float64, false),
        field("j", DataType::Float64, false),
        field("zxdq", DataType::Float64, true),
        field("zxdkx", DataType::Float64, true),
        field("dif", DataType::Float64, false),
        field("dea", DataType::Float64, false),
        field("macd_hist", DataType::Float64, false),
        field("ma25", DataType::Float64, true),
        field("ma60", DataType::Float64, true),
        field("ma144", DataType::Float64, true),
        field("chg_d", DataType::Float64, true),
        field("weekly_ma_bull", DataType::Boolean, false),
        field("max_vol_not_bearish", DataType::Boolean, false),
        field("v_shrink", DataType::Boolean, false),
        field("safe_mode", DataType::Boolean, false),
        field("lt_filter", DataType::Boolean, false),
    ];
    fields.extend(
        factor_keys
            .iter()
            .map(|key| field(key, DataType::Float64, true)),
    );
    Arc::new(Schema::new(fields))
}

fn prepared_rows_record_batch_optimized(
    rows: &[PreparedRow],
    factor_keys: &[String],
    schema: SchemaRef,
) -> anyhow::Result<RecordBatch> {
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Unix epoch is valid");
    let dates = rows
        .iter()
        .map(|row| i32::try_from(row.trade_date.signed_duration_since(epoch).num_days()))
        .collect::<Result<Vec<_>, _>>()?;
    let mut arrays: Vec<ArrayRef> = vec![
        Arc::new(StringArray::from(
            rows.iter()
                .map(|row| row.ts_code.as_str())
                .collect::<Vec<_>>(),
        )),
        Arc::new(Date32Array::from(dates)),
        required_f64_array(rows, |row| row.open),
        required_f64_array(rows, |row| row.high),
        required_f64_array(rows, |row| row.low),
        required_f64_array(rows, |row| row.close),
        required_f64_array(rows, |row| row.volume),
        required_f64_array(rows, |row| row.turnover_n),
        optional_f64_array(rows, |row| row.turnover_rate),
        required_f64_array(rows, |row| row.k),
        required_f64_array(rows, |row| row.d),
        required_f64_array(rows, |row| row.j),
        optional_f64_array(rows, |row| row.zxdq),
        optional_f64_array(rows, |row| row.zxdkx),
        required_f64_array(rows, |row| row.dif),
        required_f64_array(rows, |row| row.dea),
        required_f64_array(rows, |row| row.macd_hist),
        optional_f64_array(rows, |row| row.ma25),
        optional_f64_array(rows, |row| row.ma60),
        optional_f64_array(rows, |row| row.ma144),
        optional_f64_array(rows, |row| row.chg_d),
        boolean_array(rows, |row| row.weekly_ma_bull),
        boolean_array(rows, |row| row.max_vol_not_bearish),
        boolean_array(rows, |row| row.v_shrink),
        boolean_array(rows, |row| row.safe_mode),
        boolean_array(rows, |row| row.lt_filter),
    ];
    let factor_indexes = factor_keys
        .iter()
        .enumerate()
        .map(|(index, key)| (key.as_str(), index))
        .collect::<HashMap<_, _>>();
    let mut factor_columns = (0..factor_keys.len())
        .map(|_| vec![None; rows.len()])
        .collect::<Vec<_>>();
    for (row_index, row) in rows.iter().enumerate() {
        for (key, value) in &row.db_factors {
            if let Some(&column_index) = factor_indexes.get(key.as_str()) {
                factor_columns[column_index][row_index] = value.is_finite().then_some(*value);
            }
        }
    }
    arrays.extend(
        factor_columns
            .into_iter()
            .map(|values| Arc::new(Float64Array::from(values)) as ArrayRef),
    );
    Ok(RecordBatch::try_new(schema, arrays)?)
}

fn required_f64_array(rows: &[PreparedRow], value: impl Fn(&PreparedRow) -> f64) -> ArrayRef {
    Arc::new(Float64Array::from_iter_values(rows.iter().map(value)))
}

fn optional_f64_array(
    rows: &[PreparedRow],
    value: impl Fn(&PreparedRow) -> Option<f64>,
) -> ArrayRef {
    Arc::new(Float64Array::from(
        rows.iter().map(value).collect::<Vec<_>>(),
    ))
}

fn boolean_array(rows: &[PreparedRow], value: impl Fn(&PreparedRow) -> bool) -> ArrayRef {
    Arc::new(BooleanArray::from(
        rows.iter().map(value).collect::<Vec<_>>(),
    ))
}

pub fn decode_prepared_cache_rows(bytes: &[u8]) -> anyhow::Result<Vec<PreparedRow>> {
    if !bytes.starts_with(PARQUET_MAGIC) {
        anyhow::bail!("binary prepared caches are no longer supported; expected Parquet")
    }
    decode_prepared_cache_rows_from_parquet(Bytes::copy_from_slice(bytes))
}

fn is_parquet_cache_file(path: &Path) -> anyhow::Result<bool> {
    let mut file = match std::fs::File::open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(false),
        Err(error) => return Err(error.into()),
    };
    let mut magic = [0_u8; 4];
    Ok(file.read_exact(&mut magic).is_ok() && &magic == PARQUET_MAGIC)
}

fn decode_prepared_cache_parquet_file(path: &Path) -> anyhow::Result<Vec<PreparedRow>> {
    let mut file = std::fs::File::open(path)?;
    let mut magic = [0_u8; 4];
    file.read_exact(&mut magic)?;
    if &magic != PARQUET_MAGIC {
        anyhow::bail!("binary prepared caches are no longer supported; expected Parquet")
    }
    file.seek(SeekFrom::Start(0))?;
    decode_prepared_cache_rows_from_parquet(file)
}

fn decode_prepared_cache_rows_from_parquet<R: parquet::file::reader::ChunkReader + 'static>(
    reader: R,
) -> anyhow::Result<Vec<PreparedRow>> {
    let mut batches = ParquetRecordBatchReaderBuilder::try_new(reader)?.build()?;
    let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Unix epoch is valid");
    let mut rows = Vec::new();
    while let Some(batch) = batches.next() {
        let batch = batch?;
        let schema = batch.schema();
        let ts_codes = string_column_by_name(&batch, "ts_code")?;
        let trade_dates = array_column_by_name::<Date32Array>(&batch, "trade_date")?;
        let floats = (2..=20)
            .map(|index| array_column::<Float64Array>(&batch, index))
            .collect::<Result<Vec<_>, _>>()?;
        let booleans = (21..=25)
            .map(|index| array_column::<BooleanArray>(&batch, index))
            .collect::<Result<Vec<_>, _>>()?;
        let factor_columns = schema
            .fields()
            .iter()
            .enumerate()
            .skip(26)
            .map(|(index, field)| {
                anyhow::Ok((
                    field.name().to_string(),
                    array_column::<Float64Array>(&batch, index)?,
                ))
            })
            .collect::<anyhow::Result<Vec<_>>>()?;
        for row_index in 0..batch.num_rows() {
            let trade_date = epoch
                .checked_add_signed(chrono::Duration::days(i64::from(
                    trade_dates.value(row_index),
                )))
                .ok_or_else(|| anyhow::anyhow!("cached trade_date is out of range"))?;
            let db_factors = factor_columns
                .iter()
                .filter_map(|(key, values)| {
                    (!values.is_null(row_index)).then_some((key.clone(), values.value(row_index)))
                })
                .collect();
            rows.push(PreparedRow {
                ts_code: ts_codes.value(row_index).to_string(),
                trade_date,
                open: floats[0].value(row_index),
                high: floats[1].value(row_index),
                low: floats[2].value(row_index),
                close: floats[3].value(row_index),
                volume: floats[4].value(row_index),
                turnover_n: floats[5].value(row_index),
                turnover_rate: optional_float_value(floats[6], row_index),
                k: floats[7].value(row_index),
                d: floats[8].value(row_index),
                j: floats[9].value(row_index),
                zxdq: optional_float_value(floats[10], row_index),
                zxdkx: optional_float_value(floats[11], row_index),
                dif: floats[12].value(row_index),
                dea: floats[13].value(row_index),
                macd_hist: floats[14].value(row_index),
                ma25: optional_float_value(floats[15], row_index),
                ma60: optional_float_value(floats[16], row_index),
                ma144: optional_float_value(floats[17], row_index),
                chg_d: optional_float_value(floats[18], row_index),
                weekly_ma_bull: booleans[0].value(row_index),
                max_vol_not_bearish: booleans[1].value(row_index),
                v_shrink: booleans[2].value(row_index),
                safe_mode: booleans[3].value(row_index),
                lt_filter: booleans[4].value(row_index),
                db_factors,
            });
        }
    }
    Ok(rows)
}

fn array_column<T: Array + 'static>(batch: &RecordBatch, index: usize) -> anyhow::Result<&T> {
    batch
        .column(index)
        .as_any()
        .downcast_ref::<T>()
        .ok_or_else(|| anyhow::anyhow!("prepared Parquet column {index} has an unexpected type"))
}

fn array_column_by_name<'a, T: Array + 'static>(
    batch: &'a RecordBatch,
    name: &str,
) -> anyhow::Result<&'a T> {
    let index = batch
        .schema()
        .index_of(name)
        .map_err(|error| anyhow::anyhow!("prepared Parquet column {name} is missing: {error}"))?;
    array_column(batch, index)
}

fn string_column_by_name<'a>(
    batch: &'a RecordBatch,
    name: &str,
) -> anyhow::Result<&'a StringArray> {
    array_column_by_name(batch, name)
}

fn optional_float_value(values: &Float64Array, index: usize) -> Option<f64> {
    (!values.is_null(index)).then(|| values.value(index))
}

pub fn load_prepared_cache(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Option<Vec<PreparedRow>>> {
    Ok(
        load_prepared_dataset(runtime_root, method, pick_date, start_date, end_date)?
            .map(|dataset| dataset.rows),
    )
}

pub fn load_prepared_dataset(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Option<PreparedDataset>> {
    load_prepared_dataset_for_mode(runtime_root, method, pick_date, start_date, end_date, false)
}

pub fn load_prepared_cache_for_mode(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    intraday: bool,
) -> anyhow::Result<Option<Vec<PreparedRow>>> {
    Ok(load_prepared_dataset_for_mode(
        runtime_root,
        method,
        pick_date,
        start_date,
        end_date,
        intraday,
    )?
    .map(|dataset| dataset.rows))
}

pub fn load_prepared_dataset_for_mode(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    intraday: bool,
) -> anyhow::Result<Option<PreparedDataset>> {
    let paths = prepared_cache_paths(runtime_root, pick_date, intraday);
    if !paths.meta_path.exists() {
        return Ok(None);
    }
    if !paths.data_path.exists() {
        return Ok(None);
    }

    let metadata: PreparedCacheMetadata =
        serde_json::from_slice(&std::fs::read(&paths.meta_path)?)?;
    if !metadata_matches(&metadata, method, pick_date, start_date, end_date) {
        return Ok(None);
    }
    if !is_parquet_cache_file(&paths.data_path)? {
        return Ok(None);
    }
    let rows = decode_prepared_cache_parquet_file(&paths.data_path)?;
    if rows.len() != metadata.row_count {
        return Ok(None);
    }
    if !decoded_rows_match_db_native_window(&metadata, start_date, end_date, &rows) {
        return Ok(None);
    }
    if !rows.iter().any(|row| row.trade_date == end_date) {
        return Ok(None);
    }

    warn_prepared_cache_gaps_once(&paths.meta_path, pick_date, &metadata.db_data_gaps);
    Ok(Some(PreparedDataset {
        rows,
        db_data_gaps: metadata.db_data_gaps,
    }))
}

fn warn_prepared_cache_gaps_once(
    metadata_path: &Path,
    pick_date: NaiveDate,
    db_data_gaps: &BTreeMap<String, DbDataGap>,
) {
    let warned = WARNED_PREPARED_CACHE_GAPS.get_or_init(|| Mutex::new(BTreeSet::new()));
    let mut warned = warned
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    for (table, gap) in db_data_gaps {
        let message = db_data_gap_warning_message(pick_date, table, gap, Some("prepared_cache"));
        let key = format!("{}\n{message}", metadata_path.display());
        if warned.insert(key) {
            eprintln!("{message}");
        }
    }
}

fn decoded_rows_match_db_native_window(
    metadata: &PreparedCacheMetadata,
    requested_start_date: NaiveDate,
    requested_end_date: NaiveDate,
    rows: &[PreparedRow],
) -> bool {
    if metadata.source_table != DB_NATIVE_PREPARED_CACHE_SOURCE
        || metadata.mode.as_deref() == Some("intraday_snapshot")
    {
        return true;
    }
    let trade_dates = rows
        .iter()
        .map(|row| row.trade_date)
        .collect::<BTreeSet<_>>();
    let Some(actual_start) = trade_dates.first().copied() else {
        return false;
    };
    actual_start >= requested_start_date
        && trade_dates.last().copied() == Some(requested_end_date)
        && u32::try_from(trade_dates.len())
            .is_ok_and(|len| len >= MIN_DB_NATIVE_WINDOW_TRADING_DAYS)
}

fn metadata_matches(
    metadata: &PreparedCacheMetadata,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> bool {
    metadata.artifact_version == PREPARED_CACHE_ARTIFACT_VERSION
        && metadata_schema_matches(metadata.schema_version)
        && metadata_method_matches(metadata, method)
        && metadata.pick_date == pick_date
        && metadata_window_matches(metadata, start_date)
        && metadata.end_date == end_date
        && (metadata.source_table == LOCAL_DERIVED_PREPARED_CACHE_SOURCE
            || metadata.source_table == DB_NATIVE_PREPARED_CACHE_SOURCE)
        && db_native_calc_versions_match(metadata)
}

fn db_native_calc_versions_match(metadata: &PreparedCacheMetadata) -> bool {
    if metadata.source_table != DB_NATIVE_PREPARED_CACHE_SOURCE {
        return true;
    }
    if metadata
        .calc_versions
        .get("price_basis")
        .map(String::as_str)
        != Some(DB_NATIVE_PRICE_BASIS_VERSION)
    {
        return false;
    }

    let macd_matches =
        metadata.calc_versions.get("macd").map(String::as_str) == Some(DB_NATIVE_MACD_CALC_VERSION);
    let monthly_history_matches = metadata
        .calc_versions
        .get("monthly_macd_history")
        .map(String::as_str)
        == Some(DB_NATIVE_MONTHLY_MACD_HISTORY_VERSION);
    monthly_history_matches
        && macd_matches
        && metadata.calc_versions.get("rolling").map(String::as_str)
            == Some(DB_NATIVE_ROLLING_CALC_VERSION)
        && metadata.calc_versions.get("czsc").map(String::as_str)
            == Some(DB_NATIVE_CZSC_CALC_VERSION)
}

fn metadata_window_matches(metadata: &PreparedCacheMetadata, start_date: NaiveDate) -> bool {
    if metadata.start_date == start_date || metadata.mode.as_deref() == Some("intraday_snapshot") {
        return true;
    }
    metadata.source_table == DB_NATIVE_PREPARED_CACHE_SOURCE
        && metadata.start_date >= start_date
        && metadata
            .window_trading_days
            .is_some_and(|days| days >= MIN_DB_NATIVE_WINDOW_TRADING_DAYS)
}

fn metadata_schema_matches(schema_version: u32) -> bool {
    schema_version == PREPARED_CACHE_SCHEMA_VERSION
}

fn metadata_method_matches(metadata: &PreparedCacheMetadata, method: Method) -> bool {
    metadata
        .shared_methods
        .iter()
        .any(|item| item == method.as_str())
}

pub fn history_payload_for_code(rows: &[PreparedRow], code: &str) -> Vec<Value> {
    let mut rows = rows
        .iter()
        .filter(|row| row.ts_code == code)
        .collect::<Vec<_>>();
    rows.sort_by_key(|row| row.trade_date);

    rows.into_iter()
        .filter(|row| prepared_history_row_has_required_values(row))
        .map(|row| {
            json!({
                "trade_date": row.trade_date,
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "volume": row.volume,
                "turnover_n": row.turnover_n,
                "turnover_rate": row.turnover_rate,
                "k": row.k,
                "d": row.d,
                "j": row.j,
                "zxdq": row.zxdq,
                "zxdkx": row.zxdkx,
                "dif": row.dif,
                "dea": row.dea,
                "macd_hist": row.macd_hist,
                "ma25": row.ma25,
                "ma60": row.ma60,
                "ma144": row.ma144,
                "chg_d": row.chg_d,
                "db_factors": row.db_factors,
            })
        })
        .collect()
}

fn prepared_history_row_has_required_values(row: &PreparedRow) -> bool {
    [
        row.open,
        row.high,
        row.low,
        row.close,
        row.volume,
        row.turnover_n,
    ]
    .into_iter()
    .all(f64::is_finite)
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, serde_json::to_vec_pretty(value)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;

    #[test]
    fn parquet_payload_round_trips_rows() {
        let root = tempfile::tempdir().unwrap();
        let path = root.path().join("prepared.parquet");
        let date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
        let rows = vec![prepared_row_with_factors(
            "000001.SZ",
            date,
            10.0,
            &[("boll_width_pct", 12.3), ("wr_qfq", -87.5)],
        )];

        write_prepared_cache_rows_file(&path, &rows).unwrap();

        assert_eq!(decode_prepared_cache_parquet_file(&path).unwrap(), rows);
    }

    #[test]
    fn optimized_factor_key_collection_matches_old_implementation() {
        let rows = test_rows_with_sparse_factors();

        let expected = rows
            .iter()
            .flat_map(|row| row.db_factors.keys().cloned())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();

        assert_eq!(prepared_cache_factor_keys_optimized(&rows), expected);
    }

    #[test]
    fn optimized_record_batch_matches_old_implementation() {
        let rows = test_rows_with_sparse_factors();
        let factor_keys = rows
            .iter()
            .flat_map(|row| row.db_factors.keys().cloned())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect::<Vec<_>>();
        let schema = prepared_cache_schema(&factor_keys);

        let expected = prepared_rows_record_batch_old(&rows, &factor_keys, schema.clone()).unwrap();
        let actual = prepared_rows_record_batch_optimized(&rows, &factor_keys, schema).unwrap();

        assert_record_batches_equal(&actual, &expected);
    }

    fn prepared_rows_record_batch_old(
        rows: &[PreparedRow],
        factor_keys: &[String],
        schema: SchemaRef,
    ) -> anyhow::Result<RecordBatch> {
        let epoch = NaiveDate::from_ymd_opt(1970, 1, 1).expect("Unix epoch is valid");
        let dates = rows
            .iter()
            .map(|row| i32::try_from(row.trade_date.signed_duration_since(epoch).num_days()))
            .collect::<Result<Vec<_>, _>>()?;
        let mut arrays: Vec<ArrayRef> = vec![
            Arc::new(StringArray::from(
                rows.iter()
                    .map(|row| row.ts_code.as_str())
                    .collect::<Vec<_>>(),
            )),
            Arc::new(Date32Array::from(dates)),
            required_f64_array(rows, |row| row.open),
            required_f64_array(rows, |row| row.high),
            required_f64_array(rows, |row| row.low),
            required_f64_array(rows, |row| row.close),
            required_f64_array(rows, |row| row.volume),
            required_f64_array(rows, |row| row.turnover_n),
            optional_f64_array(rows, |row| row.turnover_rate),
            required_f64_array(rows, |row| row.k),
            required_f64_array(rows, |row| row.d),
            required_f64_array(rows, |row| row.j),
            optional_f64_array(rows, |row| row.zxdq),
            optional_f64_array(rows, |row| row.zxdkx),
            required_f64_array(rows, |row| row.dif),
            required_f64_array(rows, |row| row.dea),
            required_f64_array(rows, |row| row.macd_hist),
            optional_f64_array(rows, |row| row.ma25),
            optional_f64_array(rows, |row| row.ma60),
            optional_f64_array(rows, |row| row.ma144),
            optional_f64_array(rows, |row| row.chg_d),
            boolean_array(rows, |row| row.weekly_ma_bull),
            boolean_array(rows, |row| row.max_vol_not_bearish),
            boolean_array(rows, |row| row.v_shrink),
            boolean_array(rows, |row| row.safe_mode),
            boolean_array(rows, |row| row.lt_filter),
        ];
        arrays.extend(factor_keys.iter().map(|key| {
            optional_f64_array(rows, |row| {
                row.db_factors
                    .get(key)
                    .copied()
                    .filter(|value| value.is_finite())
            })
        }));
        Ok(RecordBatch::try_new(schema, arrays)?)
    }

    fn assert_record_batches_equal(actual: &RecordBatch, expected: &RecordBatch) {
        assert_eq!(actual.schema(), expected.schema());
        assert_eq!(actual.num_rows(), expected.num_rows());
        assert_eq!(actual.num_columns(), expected.num_columns());

        for index in 0..actual.num_columns() {
            let actual_column = actual.column(index);
            let expected_column = expected.column(index);
            assert_eq!(actual_column.data_type(), expected_column.data_type());
            assert_eq!(actual_column.null_count(), expected_column.null_count());
            match actual_column.data_type() {
                DataType::Utf8 => {
                    let actual = actual_column
                        .as_any()
                        .downcast_ref::<StringArray>()
                        .unwrap();
                    let expected = expected_column
                        .as_any()
                        .downcast_ref::<StringArray>()
                        .unwrap();
                    assert_eq!(
                        actual.iter().collect::<Vec<_>>(),
                        expected.iter().collect::<Vec<_>>()
                    );
                }
                DataType::Date32 => {
                    let actual = actual_column
                        .as_any()
                        .downcast_ref::<Date32Array>()
                        .unwrap();
                    let expected = expected_column
                        .as_any()
                        .downcast_ref::<Date32Array>()
                        .unwrap();
                    assert_eq!(
                        actual.iter().collect::<Vec<_>>(),
                        expected.iter().collect::<Vec<_>>()
                    );
                }
                DataType::Float64 => {
                    let actual = actual_column
                        .as_any()
                        .downcast_ref::<Float64Array>()
                        .unwrap();
                    let expected = expected_column
                        .as_any()
                        .downcast_ref::<Float64Array>()
                        .unwrap();
                    let actual = actual
                        .iter()
                        .map(|value| value.map(f64::to_bits))
                        .collect::<Vec<_>>();
                    let expected = expected
                        .iter()
                        .map(|value| value.map(f64::to_bits))
                        .collect::<Vec<_>>();
                    assert_eq!(actual, expected);
                }
                DataType::Boolean => {
                    let actual = actual_column
                        .as_any()
                        .downcast_ref::<BooleanArray>()
                        .unwrap();
                    let expected = expected_column
                        .as_any()
                        .downcast_ref::<BooleanArray>()
                        .unwrap();
                    assert_eq!(
                        actual.iter().collect::<Vec<_>>(),
                        expected.iter().collect::<Vec<_>>()
                    );
                }
                data_type => panic!("unexpected prepared cache test data type: {data_type:?}"),
            }
        }
    }

    fn test_rows_with_sparse_factors() -> Vec<PreparedRow> {
        let mut first = prepared_row_with_factors(
            "000001.SZ",
            NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
            10.0,
            &[("z_factor", 1.0), ("a_factor", 2.0)],
        );
        first.turnover_rate = None;
        first.db_factors.insert("nan_factor".to_string(), f64::NAN);

        let mut second = prepared_row_with_factors(
            "000002.SZ",
            NaiveDate::from_ymd_opt(2026, 5, 26).unwrap(),
            11.0,
            &[("m_factor", 3.0), ("z_factor", 4.0)],
        );
        second.ma144 = None;

        let mut third = prepared_row_with_factors(
            "000003.SZ",
            NaiveDate::from_ymd_opt(2026, 5, 27).unwrap(),
            12.0,
            &[("a_factor", 5.0), ("m_factor", 6.0)],
        );
        third
            .db_factors
            .insert("inf_factor".to_string(), f64::INFINITY);

        vec![first, second, third]
    }

    fn prepared_row_with_factors(
        code: &str,
        trade_date: NaiveDate,
        close: f64,
        factors: &[(&str, f64)],
    ) -> PreparedRow {
        PreparedRow {
            ts_code: code.to_string(),
            trade_date,
            open: close - 0.5,
            high: close + 1.0,
            low: close - 1.0,
            close,
            volume: 1000.0,
            turnover_n: 12.0,
            turnover_rate: Some(1.5),
            k: 50.0,
            d: 40.0,
            j: 60.0,
            zxdq: Some(10.2),
            zxdkx: Some(10.1),
            dif: 0.3,
            dea: 0.2,
            macd_hist: 0.1,
            ma25: Some(10.0),
            ma60: Some(9.8),
            ma144: None,
            chg_d: Some(1.2),
            weekly_ma_bull: true,
            max_vol_not_bearish: false,
            v_shrink: true,
            safe_mode: false,
            lt_filter: true,
            db_factors: factors
                .iter()
                .map(|(key, value)| ((*key).to_string(), *value))
                .collect::<BTreeMap<_, _>>(),
        }
    }
}
