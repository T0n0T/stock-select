use std::collections::{BTreeMap, BTreeSet};
use std::io::{BufRead, BufReader, Cursor, Read, Write};
use std::path::{Path, PathBuf};
use std::time::SystemTime;

use chrono::{Datelike, NaiveDate};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::model::{Method, PreparedRow};

pub const PREPARED_CACHE_ARTIFACT_VERSION: u32 = 1;
pub const PREPARED_CACHE_SCHEMA_VERSION: u32 = 8;
pub const DEFAULT_PREPARED_CACHE_RETENTION_LIMIT: usize = 30;
pub const PREPARED_CACHE_RETENTION_LIMIT_ENV: &str = "STOCK_SELECT_PREPARED_CACHE_LIMIT";
const LEGACY_PREPARED_CACHE_MAGIC: &[u8; 8] = b"SSPRBIN1";
const DICTIONARY_PREPARED_CACHE_MAGIC: &[u8; 8] = b"SSPRDIC2";
const ZSTD_FRAME_MAGIC: &[u8; 4] = &[0x28, 0xb5, 0x2f, 0xfd];
const PREPARED_CACHE_ZSTD_LEVEL: i32 = 1;

pub fn prepared_cache_start_date(end_date: NaiveDate) -> NaiveDate {
    date_years_before(end_date, 3)
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
        data_path: dir.join(format!("{base_name}.bin.zst")),
        meta_path: dir.join(format!("{base_name}.meta.json")),
    }
}

fn legacy_prepared_cache_data_path(
    runtime_root: &Path,
    pick_date: NaiveDate,
    intraday: bool,
) -> PathBuf {
    let suffix = if intraday { ".intraday" } else { "" };
    runtime_root
        .join("prepared")
        .join(format!("{}{}.bin", pick_date.format("%Y-%m-%d"), suffix))
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

pub fn write_prepared_cache_for_mode(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    intraday: bool,
    rows: &[PreparedRow],
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
        &build_metadata(method, pick_date, start_date, end_date, intraday, rows),
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
        remove_file_if_exists(&legacy_prepared_cache_data_path(
            runtime_root,
            pick_date,
            false,
        ))?;
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
) -> PreparedCacheMetadata {
    let symbol_count = rows
        .iter()
        .map(|row| row.ts_code.as_str())
        .collect::<BTreeSet<_>>()
        .len();
    PreparedCacheMetadata {
        artifact_version: PREPARED_CACHE_ARTIFACT_VERSION,
        method: method.as_str().to_string(),
        shared_methods: vec![
            "b1".to_string(),
            "b2".to_string(),
            "b3".to_string(),
            "lsh".to_string(),
            "dribull".to_string(),
        ],
        pick_date,
        start_date,
        end_date,
        schema_version: PREPARED_CACHE_SCHEMA_VERSION,
        row_count: rows.len(),
        symbol_count,
        source_table: "daily_market".to_string(),
        mode: intraday.then(|| "intraday_snapshot".to_string()),
        source: intraday.then(|| "tushare_rt_k".to_string()),
        run_id: None,
        previous_trade_date: None,
        compression: Some("zstd".to_string()),
        encoding: Some("dictionary_v2".to_string()),
    }
}

fn write_prepared_cache_rows_file(path: &Path, rows: &[PreparedRow]) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut file = std::fs::File::create(path)?;
    encode_prepared_cache_rows_to_writer(rows, &mut file)?;
    file.flush()?;
    Ok(())
}

fn encode_prepared_cache_rows_to_writer<W: Write>(
    rows: &[PreparedRow],
    out: W,
) -> anyhow::Result<()> {
    let mut encoder = zstd::stream::Encoder::new(out, PREPARED_CACHE_ZSTD_LEVEL)?;
    encode_prepared_cache_rows_dictionary_to_writer(rows, &mut encoder)?;
    encoder.finish()?;
    Ok(())
}

fn encode_prepared_cache_rows_dictionary_to_writer<W: Write>(
    rows: &[PreparedRow],
    out: &mut W,
) -> anyhow::Result<()> {
    let factor_keys = collect_factor_keys(rows);
    let mut factor_key_ids = BTreeMap::<&str, u16>::new();
    for (idx, key) in factor_keys.iter().enumerate() {
        factor_key_ids.insert(key.as_str(), u16::try_from(idx)?);
    }

    out.write_all(DICTIONARY_PREPARED_CACHE_MAGIC)?;
    write_u64(out, factor_keys.len() as u64)?;
    for key in &factor_keys {
        write_string(out, key)?;
    }
    write_u64(out, rows.len() as u64)?;
    let mut row_buffer = Vec::new();
    for row in rows {
        row_buffer.clear();
        row_buffer.reserve(prepared_row_encoded_capacity_hint(row));
        write_prepared_row_core(&mut row_buffer, row)?;
        write_u64(&mut row_buffer, row.db_factors.len() as u64)?;
        for (key, value) in &row.db_factors {
            let id = factor_key_ids
                .get(key.as_str())
                .ok_or_else(|| anyhow::anyhow!("missing prepared cache factor key id: {key}"))?;
            write_u16(&mut row_buffer, *id)?;
            write_f64(&mut row_buffer, *value)?;
        }
        out.write_all(&row_buffer)?;
    }
    Ok(())
}

fn collect_factor_keys(rows: &[PreparedRow]) -> Vec<String> {
    rows.iter()
        .flat_map(|row| row.db_factors.keys().cloned())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn prepared_row_encoded_capacity_hint(row: &PreparedRow) -> usize {
    const PREPARED_ROW_CORE_FIXED_BYTES: usize = 177;
    const PREPARED_ROW_FACTOR_BYTES: usize = 10;

    2 + row.ts_code.len()
        + PREPARED_ROW_CORE_FIXED_BYTES
        + row.db_factors.len() * PREPARED_ROW_FACTOR_BYTES
}

fn write_prepared_row_core<W: Write>(out: &mut W, row: &PreparedRow) -> anyhow::Result<()> {
    write_string(out, &row.ts_code)?;
    write_i32(out, row.trade_date.num_days_from_ce())?;
    for value in [
        row.open,
        row.high,
        row.low,
        row.close,
        row.volume,
        row.turnover_n,
    ] {
        write_f64(out, value)?;
    }
    write_option_f64(out, row.turnover_rate)?;
    for value in [row.k, row.d, row.j] {
        write_f64(out, value)?;
    }
    write_option_f64(out, row.zxdq)?;
    write_option_f64(out, row.zxdkx)?;
    for value in [row.dif, row.dea, row.macd_hist] {
        write_f64(out, value)?;
    }
    write_option_f64(out, row.ma25)?;
    write_option_f64(out, row.ma60)?;
    write_option_f64(out, row.ma144)?;
    write_option_f64(out, row.chg_d)?;
    for value in [
        row.weekly_ma_bull,
        row.max_vol_not_bearish,
        row.v_shrink,
        row.safe_mode,
        row.lt_filter,
        row.yellow_b1,
    ] {
        write_bool(out, value)?;
    }
    Ok(())
}

pub fn decode_prepared_cache_rows(bytes: &[u8]) -> anyhow::Result<Vec<PreparedRow>> {
    decode_prepared_cache_rows_from_reader(Cursor::new(bytes))
}

fn decode_prepared_cache_rows_from_reader<R: Read>(reader: R) -> anyhow::Result<Vec<PreparedRow>> {
    let mut reader = BufReader::new(reader);
    if reader.fill_buf()?.starts_with(ZSTD_FRAME_MAGIC) {
        let decoder = zstd::stream::Decoder::new(reader)?;
        return decode_prepared_cache_rows_dictionary_from_reader(decoder);
    }

    let mut magic = [0_u8; 8];
    reader.read_exact(&mut magic)?;
    if &magic == LEGACY_PREPARED_CACHE_MAGIC {
        return decode_prepared_cache_rows_legacy(reader);
    }

    anyhow::bail!("invalid prepared cache magic");
}

fn decode_prepared_cache_rows_dictionary_from_reader<R: Read>(
    reader: R,
) -> anyhow::Result<Vec<PreparedRow>> {
    let mut cursor = BufReader::new(reader);
    let mut magic = [0_u8; 8];
    cursor.read_exact(&mut magic)?;
    if &magic != DICTIONARY_PREPARED_CACHE_MAGIC {
        anyhow::bail!("invalid prepared cache dictionary magic");
    }

    let factor_key_count = read_u64(&mut cursor)? as usize;
    let mut factor_keys = Vec::with_capacity(factor_key_count);
    for _ in 0..factor_key_count {
        factor_keys.push(read_string(&mut cursor)?);
    }

    let count = read_u64(&mut cursor)? as usize;
    let mut rows = Vec::with_capacity(count);
    for _ in 0..count {
        let mut row = read_prepared_row_core(&mut cursor)?;
        let factor_count = read_u64(&mut cursor)? as usize;
        let mut factors = BTreeMap::new();
        for _ in 0..factor_count {
            let key_id = read_u16(&mut cursor)? as usize;
            let key = factor_keys
                .get(key_id)
                .ok_or_else(|| anyhow::anyhow!("invalid prepared cache factor key id"))?;
            factors.insert(key.clone(), read_f64(&mut cursor)?);
        }
        row.db_factors = factors;
        rows.push(row);
    }
    Ok(rows)
}

fn decode_prepared_cache_rows_legacy(mut cursor: impl Read) -> anyhow::Result<Vec<PreparedRow>> {
    let count = read_u64(&mut cursor)? as usize;
    let mut rows = Vec::with_capacity(count);
    for _ in 0..count {
        let mut row = read_prepared_row_core(&mut cursor)?;
        row.db_factors = read_factor_map(&mut cursor)?;
        rows.push(row);
    }
    Ok(rows)
}

fn read_prepared_row_core(cursor: &mut impl Read) -> anyhow::Result<PreparedRow> {
    let ts_code = read_string(cursor)?;
    let trade_date = NaiveDate::from_num_days_from_ce_opt(read_i32(cursor)?)
        .ok_or_else(|| anyhow::anyhow!("invalid cached trade_date"))?;
    Ok(PreparedRow {
        ts_code,
        trade_date,
        open: read_f64(cursor)?,
        high: read_f64(cursor)?,
        low: read_f64(cursor)?,
        close: read_f64(cursor)?,
        volume: read_f64(cursor)?,
        turnover_n: read_f64(cursor)?,
        turnover_rate: read_option_f64(cursor)?,
        k: read_f64(cursor)?,
        d: read_f64(cursor)?,
        j: read_f64(cursor)?,
        zxdq: read_option_f64(cursor)?,
        zxdkx: read_option_f64(cursor)?,
        dif: read_f64(cursor)?,
        dea: read_f64(cursor)?,
        macd_hist: read_f64(cursor)?,
        ma25: read_option_f64(cursor)?,
        ma60: read_option_f64(cursor)?,
        ma144: read_option_f64(cursor)?,
        chg_d: read_option_f64(cursor)?,
        weekly_ma_bull: read_bool(cursor)?,
        max_vol_not_bearish: read_bool(cursor)?,
        v_shrink: read_bool(cursor)?,
        safe_mode: read_bool(cursor)?,
        lt_filter: read_bool(cursor)?,
        yellow_b1: read_bool(cursor)?,
        db_factors: BTreeMap::new(),
    })
}

pub fn load_prepared_cache(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Option<Vec<PreparedRow>>> {
    load_prepared_cache_for_mode(runtime_root, method, pick_date, start_date, end_date, false)
}

pub fn load_prepared_cache_for_mode(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    intraday: bool,
) -> anyhow::Result<Option<Vec<PreparedRow>>> {
    let paths = prepared_cache_paths(runtime_root, pick_date, intraday);
    if !paths.meta_path.exists() {
        return Ok(None);
    }
    let data_path = if paths.data_path.exists() {
        paths.data_path
    } else {
        let legacy_path = legacy_prepared_cache_data_path(runtime_root, pick_date, intraday);
        if !legacy_path.exists() {
            return Ok(None);
        }
        legacy_path
    };

    let metadata: PreparedCacheMetadata =
        serde_json::from_slice(&std::fs::read(&paths.meta_path)?)?;
    if !metadata_matches(&metadata, method, pick_date, start_date, end_date) {
        return Ok(None);
    }
    let rows = decode_prepared_cache_rows_from_reader(std::fs::File::open(data_path)?)?;
    if rows.len() != metadata.row_count {
        return Ok(None);
    }
    if !rows.iter().any(|row| row.trade_date == end_date) {
        return Ok(None);
    }

    Ok(Some(rows))
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
        && (metadata.start_date == start_date
            || metadata.mode.as_deref() == Some("intraday_snapshot"))
        && metadata.end_date == end_date
        && metadata.source_table == "daily_market"
}

fn metadata_schema_matches(schema_version: u32) -> bool {
    schema_version == PREPARED_CACHE_SCHEMA_VERSION
}

fn metadata_method_matches(metadata: &PreparedCacheMetadata, method: Method) -> bool {
    if metadata
        .shared_methods
        .iter()
        .any(|item| item == method.as_str())
    {
        return true;
    }
    method == Method::Lsh
        && metadata
            .shared_methods
            .iter()
            .any(|item| item == "b2" || item == "b3")
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

fn read_string(cursor: &mut impl Read) -> anyhow::Result<String> {
    let len = read_u16(cursor)? as usize;
    let mut bytes = vec![0_u8; len];
    cursor.read_exact(&mut bytes)?;
    Ok(String::from_utf8(bytes)?)
}

fn read_bool(cursor: &mut impl Read) -> anyhow::Result<bool> {
    let mut bytes = [0_u8; 1];
    cursor.read_exact(&mut bytes)?;
    Ok(bytes[0] != 0)
}

fn read_option_f64(cursor: &mut impl Read) -> anyhow::Result<Option<f64>> {
    if read_bool(cursor)? {
        Ok(Some(read_f64(cursor)?))
    } else {
        Ok(None)
    }
}

fn read_u16(cursor: &mut impl Read) -> anyhow::Result<u16> {
    let mut bytes = [0_u8; 2];
    cursor.read_exact(&mut bytes)?;
    Ok(u16::from_le_bytes(bytes))
}

fn read_u64(cursor: &mut impl Read) -> anyhow::Result<u64> {
    let mut bytes = [0_u8; 8];
    cursor.read_exact(&mut bytes)?;
    Ok(u64::from_le_bytes(bytes))
}

fn read_i32(cursor: &mut impl Read) -> anyhow::Result<i32> {
    let mut bytes = [0_u8; 4];
    cursor.read_exact(&mut bytes)?;
    Ok(i32::from_le_bytes(bytes))
}

fn read_f64(cursor: &mut impl Read) -> anyhow::Result<f64> {
    let mut bytes = [0_u8; 8];
    cursor.read_exact(&mut bytes)?;
    Ok(f64::from_le_bytes(bytes))
}

fn read_factor_map(cursor: &mut impl Read) -> anyhow::Result<BTreeMap<String, f64>> {
    let count = read_u64(cursor)? as usize;
    let mut factors = BTreeMap::new();
    for _ in 0..count {
        factors.insert(read_string(cursor)?, read_f64(cursor)?);
    }
    Ok(factors)
}

fn write_json<T: Serialize>(path: &Path, value: &T) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, serde_json::to_vec_pretty(value)?)?;
    Ok(())
}

fn write_string(out: &mut impl Write, value: &str) -> anyhow::Result<()> {
    let len = u16::try_from(value.len())?;
    out.write_all(&len.to_le_bytes())?;
    out.write_all(value.as_bytes())?;
    Ok(())
}

fn write_bool(out: &mut impl Write, value: bool) -> anyhow::Result<()> {
    out.write_all(&[u8::from(value)])?;
    Ok(())
}

fn write_option_f64(out: &mut impl Write, value: Option<f64>) -> anyhow::Result<()> {
    match value {
        Some(value) => {
            write_bool(out, true)?;
            write_f64(out, value)?;
        }
        None => write_bool(out, false)?,
    }
    Ok(())
}

fn write_u64(out: &mut impl Write, value: u64) -> anyhow::Result<()> {
    out.write_all(&value.to_le_bytes())?;
    Ok(())
}

fn write_u16(out: &mut impl Write, value: u16) -> anyhow::Result<()> {
    out.write_all(&value.to_le_bytes())?;
    Ok(())
}

fn write_i32(out: &mut impl Write, value: i32) -> anyhow::Result<()> {
    out.write_all(&value.to_le_bytes())?;
    Ok(())
}

fn write_f64(out: &mut impl Write, value: f64) -> anyhow::Result<()> {
    out.write_all(&value.to_le_bytes())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::BTreeMap;
    use std::io;

    #[test]
    fn prepared_cache_zstd_writer_stream_round_trips_rows() {
        let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
        let rows = vec![
            prepared_row_with_factors(
                "000001.SZ",
                pick_date,
                10.0,
                &[("boll_width_pct", 12.3), ("wr_qfq", -87.5)],
            ),
            prepared_row_with_factors(
                "000002.SZ",
                pick_date,
                20.0,
                &[("boll_width_pct", 8.8), ("wr_qfq", -50.0)],
            ),
        ];

        let mut bytes = Vec::new();
        encode_prepared_cache_rows_to_writer(&rows, &mut bytes).unwrap();

        assert_eq!(&bytes[..4], ZSTD_FRAME_MAGIC);
        assert_eq!(decode_prepared_cache_rows(&bytes).unwrap(), rows);
    }

    #[test]
    fn prepared_cache_zstd_reader_stream_decodes_rows() {
        let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
        let rows = vec![prepared_row_with_factors(
            "000001.SZ",
            pick_date,
            10.0,
            &[("boll_width_pct", 12.3), ("wr_qfq", -87.5)],
        )];
        let mut bytes = Vec::new();
        encode_prepared_cache_rows_to_writer(&rows, &mut bytes).unwrap();

        let decoded = decode_prepared_cache_rows_from_reader(Cursor::new(bytes)).unwrap();

        assert_eq!(decoded, rows);
    }

    #[test]
    fn prepared_cache_dictionary_writer_writes_one_payload_chunk_per_row() {
        let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
        let rows = vec![
            prepared_row_with_factors(
                "000001.SZ",
                pick_date,
                10.0,
                &[
                    ("boll_width_pct", 12.3),
                    ("wr_qfq", -87.5),
                    ("market_value", 12345.6),
                ],
            ),
            prepared_row_with_factors(
                "000002.SZ",
                pick_date,
                20.0,
                &[("boll_width_pct", 8.8), ("wr_qfq", -50.0)],
            ),
        ];
        let mut out = RowWriteCounting::new(dictionary_header_len(&rows));

        encode_prepared_cache_rows_dictionary_to_writer(&rows, &mut out).unwrap();

        assert_eq!(out.payload_writes, rows.len());
        assert_eq!(
            decode_prepared_cache_rows_dictionary_from_reader(Cursor::new(out.bytes)).unwrap(),
            rows
        );
    }

    fn dictionary_header_len(rows: &[PreparedRow]) -> usize {
        DICTIONARY_PREPARED_CACHE_MAGIC.len()
            + std::mem::size_of::<u64>()
            + collect_factor_keys(rows)
                .iter()
                .map(|key| std::mem::size_of::<u16>() + key.len())
                .sum::<usize>()
            + std::mem::size_of::<u64>()
    }

    struct RowWriteCounting {
        bytes: Vec<u8>,
        payload_offset: usize,
        payload_writes: usize,
    }

    impl RowWriteCounting {
        fn new(payload_offset: usize) -> Self {
            Self {
                bytes: Vec::new(),
                payload_offset,
                payload_writes: 0,
            }
        }
    }

    impl Write for RowWriteCounting {
        fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
            if self.bytes.len() >= self.payload_offset
                || self.bytes.len().saturating_add(buf.len()) > self.payload_offset
            {
                self.payload_writes += 1;
            }
            self.bytes.extend_from_slice(buf);
            Ok(buf.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
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
            yellow_b1: false,
            db_factors: factors
                .iter()
                .map(|(key, value)| ((*key).to_string(), *value))
                .collect::<BTreeMap<_, _>>(),
        }
    }
}
