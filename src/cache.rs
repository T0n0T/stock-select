use std::collections::{BTreeMap, BTreeSet};
use std::io::{Cursor, Read};
use std::path::{Path, PathBuf};

use chrono::{Datelike, NaiveDate};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

use crate::model::{Method, PreparedRow};

pub const PREPARED_CACHE_ARTIFACT_VERSION: u32 = 1;
pub const PREPARED_CACHE_SCHEMA_VERSION: u32 = 8;
const LEGACY_PREPARED_CACHE_MAGIC: &[u8; 8] = b"SSPRBIN1";
const DICTIONARY_PREPARED_CACHE_MAGIC: &[u8; 8] = b"SSPRDIC2";
const ZSTD_FRAME_MAGIC: &[u8; 4] = &[0x28, 0xb5, 0x2f, 0xfd];
const PREPARED_CACHE_ZSTD_LEVEL: i32 = 1;

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
    let paths = prepared_cache_paths(runtime_root, pick_date, intraday);
    write_binary(&paths.data_path, &encode_prepared_cache_rows(rows)?)?;
    write_json(
        &paths.meta_path,
        &build_metadata(method, pick_date, start_date, end_date, intraday, rows),
    )?;
    Ok(())
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

fn encode_prepared_cache_rows(rows: &[PreparedRow]) -> anyhow::Result<Vec<u8>> {
    let payload = encode_prepared_cache_rows_dictionary(rows)?;
    Ok(zstd::stream::encode_all(
        Cursor::new(payload),
        PREPARED_CACHE_ZSTD_LEVEL,
    )?)
}

fn encode_prepared_cache_rows_dictionary(rows: &[PreparedRow]) -> anyhow::Result<Vec<u8>> {
    let factor_keys = collect_factor_keys(rows);
    let mut factor_key_ids = BTreeMap::<&str, u16>::new();
    for (idx, key) in factor_keys.iter().enumerate() {
        factor_key_ids.insert(key.as_str(), u16::try_from(idx)?);
    }

    let mut out = Vec::new();
    out.extend_from_slice(DICTIONARY_PREPARED_CACHE_MAGIC);
    write_u64(&mut out, factor_keys.len() as u64);
    for key in &factor_keys {
        write_string(&mut out, key)?;
    }
    write_u64(&mut out, rows.len() as u64);
    for row in rows {
        write_prepared_row_core(&mut out, row)?;
        write_u64(&mut out, row.db_factors.len() as u64);
        for (key, value) in &row.db_factors {
            let id = factor_key_ids
                .get(key.as_str())
                .ok_or_else(|| anyhow::anyhow!("missing prepared cache factor key id: {key}"))?;
            write_u16(&mut out, *id);
            write_f64(&mut out, *value);
        }
    }
    Ok(out)
}

fn collect_factor_keys(rows: &[PreparedRow]) -> Vec<String> {
    rows.iter()
        .flat_map(|row| row.db_factors.keys().cloned())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect()
}

fn write_prepared_row_core(out: &mut Vec<u8>, row: &PreparedRow) -> anyhow::Result<()> {
    write_string(out, &row.ts_code)?;
    write_i32(out, row.trade_date.num_days_from_ce());
    for value in [
        row.open,
        row.high,
        row.low,
        row.close,
        row.volume,
        row.turnover_n,
    ] {
        write_f64(out, value);
    }
    write_option_f64(out, row.turnover_rate);
    for value in [row.k, row.d, row.j] {
        write_f64(out, value);
    }
    write_option_f64(out, row.zxdq);
    write_option_f64(out, row.zxdkx);
    for value in [row.dif, row.dea, row.macd_hist] {
        write_f64(out, value);
    }
    write_option_f64(out, row.ma25);
    write_option_f64(out, row.ma60);
    write_option_f64(out, row.ma144);
    write_option_f64(out, row.chg_d);
    for value in [
        row.weekly_ma_bull,
        row.max_vol_not_bearish,
        row.v_shrink,
        row.safe_mode,
        row.lt_filter,
        row.yellow_b1,
    ] {
        write_bool(out, value);
    }
    Ok(())
}

pub fn decode_prepared_cache_rows(bytes: &[u8]) -> anyhow::Result<Vec<PreparedRow>> {
    if bytes.starts_with(ZSTD_FRAME_MAGIC) {
        let payload = zstd::stream::decode_all(Cursor::new(bytes))?;
        return decode_prepared_cache_rows_dictionary(&payload);
    }

    let mut cursor = Cursor::new(bytes);
    let mut magic = [0_u8; 8];
    cursor.read_exact(&mut magic)?;
    if &magic == LEGACY_PREPARED_CACHE_MAGIC {
        return decode_prepared_cache_rows_legacy(cursor);
    }

    anyhow::bail!("invalid prepared cache magic");
}

fn decode_prepared_cache_rows_dictionary(bytes: &[u8]) -> anyhow::Result<Vec<PreparedRow>> {
    let mut cursor = Cursor::new(bytes);
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

fn decode_prepared_cache_rows_legacy(
    mut cursor: Cursor<&[u8]>,
) -> anyhow::Result<Vec<PreparedRow>> {
    let count = read_u64(&mut cursor)? as usize;
    let mut rows = Vec::with_capacity(count);
    for _ in 0..count {
        let mut row = read_prepared_row_core(&mut cursor)?;
        row.db_factors = read_factor_map(&mut cursor)?;
        rows.push(row);
    }
    Ok(rows)
}

fn read_prepared_row_core(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<PreparedRow> {
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
    let rows = decode_prepared_cache_rows(&std::fs::read(data_path)?)?;
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

fn read_string(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<String> {
    let len = read_u16(cursor)? as usize;
    let mut bytes = vec![0_u8; len];
    cursor.read_exact(&mut bytes)?;
    Ok(String::from_utf8(bytes)?)
}

fn read_bool(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<bool> {
    let mut bytes = [0_u8; 1];
    cursor.read_exact(&mut bytes)?;
    Ok(bytes[0] != 0)
}

fn read_option_f64(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<Option<f64>> {
    if read_bool(cursor)? {
        Ok(Some(read_f64(cursor)?))
    } else {
        Ok(None)
    }
}

fn read_u16(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<u16> {
    let mut bytes = [0_u8; 2];
    cursor.read_exact(&mut bytes)?;
    Ok(u16::from_le_bytes(bytes))
}

fn read_u64(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<u64> {
    let mut bytes = [0_u8; 8];
    cursor.read_exact(&mut bytes)?;
    Ok(u64::from_le_bytes(bytes))
}

fn read_i32(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<i32> {
    let mut bytes = [0_u8; 4];
    cursor.read_exact(&mut bytes)?;
    Ok(i32::from_le_bytes(bytes))
}

fn read_f64(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<f64> {
    let mut bytes = [0_u8; 8];
    cursor.read_exact(&mut bytes)?;
    Ok(f64::from_le_bytes(bytes))
}

fn read_factor_map(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<BTreeMap<String, f64>> {
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

fn write_binary(path: &Path, bytes: &[u8]) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, bytes)?;
    Ok(())
}

fn write_string(out: &mut Vec<u8>, value: &str) -> anyhow::Result<()> {
    let len = u16::try_from(value.len())?;
    out.extend_from_slice(&len.to_le_bytes());
    out.extend_from_slice(value.as_bytes());
    Ok(())
}

fn write_bool(out: &mut Vec<u8>, value: bool) {
    out.push(u8::from(value));
}

fn write_option_f64(out: &mut Vec<u8>, value: Option<f64>) {
    match value {
        Some(value) => {
            write_bool(out, true);
            write_f64(out, value);
        }
        None => write_bool(out, false),
    }
}

fn write_u64(out: &mut Vec<u8>, value: u64) {
    out.extend_from_slice(&value.to_le_bytes());
}

fn write_u16(out: &mut Vec<u8>, value: u16) {
    out.extend_from_slice(&value.to_le_bytes());
}

fn write_i32(out: &mut Vec<u8>, value: i32) {
    out.extend_from_slice(&value.to_le_bytes());
}

fn write_f64(out: &mut Vec<u8>, value: f64) {
    out.extend_from_slice(&value.to_le_bytes());
}
