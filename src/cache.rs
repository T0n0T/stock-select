use std::collections::BTreeSet;
use std::fs;
use std::io::{Cursor, Read, Write};
use std::path::{Path, PathBuf};

use chrono::{Datelike, NaiveDate};
use serde::{Deserialize, Serialize};

use crate::model::{Method, PreparedRow};

pub const PREPARED_CACHE_ARTIFACT_VERSION: u32 = 1;
pub const PREPARED_CACHE_SCHEMA_VERSION: u32 = 1;

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
}

pub fn prepared_cache_data_path(runtime_root: &Path, pick_date: NaiveDate) -> PathBuf {
    runtime_root
        .join("prepared")
        .join(format!("{}.bin", pick_date.format("%Y-%m-%d")))
}

pub fn prepared_cache_meta_path(runtime_root: &Path, pick_date: NaiveDate) -> PathBuf {
    runtime_root
        .join("prepared")
        .join(format!("{}.meta.json", pick_date.format("%Y-%m-%d")))
}

pub fn candidate_output_path(runtime_root: &Path, pick_date: NaiveDate, method: Method) -> PathBuf {
    runtime_root.join("candidates").join(format!(
        "{}.{}.json",
        pick_date.format("%Y-%m-%d"),
        method.as_str()
    ))
}

pub fn build_metadata(
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
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
        shared_methods: vec!["b1".to_string(), "b2".to_string(), "dribull".to_string()],
        pick_date,
        start_date,
        end_date,
        schema_version: PREPARED_CACHE_SCHEMA_VERSION,
        row_count: rows.len(),
        symbol_count,
        source_table: "daily_market".to_string(),
    }
}

pub fn metadata_matches(
    metadata: &PreparedCacheMetadata,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> bool {
    metadata.artifact_version == PREPARED_CACHE_ARTIFACT_VERSION
        && metadata.schema_version == PREPARED_CACHE_SCHEMA_VERSION
        && metadata
            .shared_methods
            .iter()
            .any(|item| item == method.as_str())
        && metadata.pick_date == pick_date
        && metadata.start_date == start_date
        && metadata.end_date == end_date
        && metadata.source_table == "daily_market"
}

pub fn write_prepared_cache(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    rows: &[PreparedRow],
) -> anyhow::Result<()> {
    let data_path = prepared_cache_data_path(runtime_root, pick_date);
    let meta_path = prepared_cache_meta_path(runtime_root, pick_date);
    if let Some(parent) = data_path.parent() {
        fs::create_dir_all(parent)?;
    }
    atomic_write_binary(&data_path, &encode_prepared_rows(rows)?)?;
    let metadata = build_metadata(method, pick_date, start_date, end_date, rows);
    atomic_write_json(&meta_path, &metadata)?;
    Ok(())
}

pub fn load_prepared_cache(
    runtime_root: &Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Option<Vec<PreparedRow>>> {
    let data_path = prepared_cache_data_path(runtime_root, pick_date);
    let meta_path = prepared_cache_meta_path(runtime_root, pick_date);
    if !data_path.exists() || !meta_path.exists() {
        return Ok(None);
    }
    let metadata: PreparedCacheMetadata = serde_json::from_slice(&fs::read(&meta_path)?)?;
    if !metadata_matches(&metadata, method, pick_date, start_date, end_date) {
        return Ok(None);
    }
    let rows = decode_prepared_rows(&fs::read(&data_path)?)?;
    if rows.len() != metadata.row_count {
        return Ok(None);
    }
    Ok(Some(rows))
}

pub fn atomic_write_json<T: Serialize>(path: &Path, value: &T) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp_path = path.with_extension(format!(
        "{}.tmp",
        path.extension()
            .and_then(|ext| ext.to_str())
            .unwrap_or("json")
    ));
    let bytes = serde_json::to_vec_pretty(value)?;
    fs::write(&tmp_path, bytes)?;
    fs::rename(tmp_path, path)?;
    Ok(())
}

fn atomic_write_binary(path: &Path, bytes: &[u8]) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let tmp_path = path.with_extension(format!(
        "{}.tmp",
        path.extension()
            .and_then(|ext| ext.to_str())
            .unwrap_or("bin")
    ));
    fs::write(&tmp_path, bytes)?;
    fs::rename(tmp_path, path)?;
    Ok(())
}

fn encode_prepared_rows(rows: &[PreparedRow]) -> anyhow::Result<Vec<u8>> {
    let mut out = Vec::with_capacity(rows.len() * 196 + 16);
    out.extend_from_slice(b"SSPRBIN1");
    write_u64(&mut out, rows.len() as u64)?;
    for row in rows {
        write_string(&mut out, &row.ts_code)?;
        write_i32(&mut out, row.trade_date.num_days_from_ce())?;
        write_f64(&mut out, row.open)?;
        write_f64(&mut out, row.high)?;
        write_f64(&mut out, row.low)?;
        write_f64(&mut out, row.close)?;
        write_f64(&mut out, row.volume)?;
        write_f64(&mut out, row.turnover_n)?;
        write_f64(&mut out, row.k)?;
        write_f64(&mut out, row.d)?;
        write_f64(&mut out, row.j)?;
        write_option_f64(&mut out, row.zxdq)?;
        write_option_f64(&mut out, row.zxdkx)?;
        write_f64(&mut out, row.dif)?;
        write_f64(&mut out, row.dea)?;
        write_f64(&mut out, row.macd_hist)?;
        write_option_f64(&mut out, row.ma25)?;
        write_option_f64(&mut out, row.ma60)?;
        write_option_f64(&mut out, row.ma144)?;
        write_bool(&mut out, row.weekly_ma_bull)?;
        write_bool(&mut out, row.max_vol_not_bearish)?;
        write_bool(&mut out, row.v_shrink)?;
        write_bool(&mut out, row.safe_mode)?;
        write_bool(&mut out, row.lt_filter)?;
    }
    Ok(out)
}

fn decode_prepared_rows(bytes: &[u8]) -> anyhow::Result<Vec<PreparedRow>> {
    let mut cursor = Cursor::new(bytes);
    let mut magic = [0_u8; 8];
    cursor.read_exact(&mut magic)?;
    if &magic != b"SSPRBIN1" {
        anyhow::bail!("invalid prepared cache magic");
    }
    let count = read_u64(&mut cursor)? as usize;
    let mut rows = Vec::with_capacity(count);
    for _ in 0..count {
        let ts_code = read_string(&mut cursor)?;
        let trade_date = NaiveDate::from_num_days_from_ce_opt(read_i32(&mut cursor)?)
            .ok_or_else(|| anyhow::anyhow!("invalid cached trade_date"))?;
        rows.push(PreparedRow {
            ts_code,
            trade_date,
            open: read_f64(&mut cursor)?,
            high: read_f64(&mut cursor)?,
            low: read_f64(&mut cursor)?,
            close: read_f64(&mut cursor)?,
            volume: read_f64(&mut cursor)?,
            turnover_n: read_f64(&mut cursor)?,
            k: read_f64(&mut cursor)?,
            d: read_f64(&mut cursor)?,
            j: read_f64(&mut cursor)?,
            zxdq: read_option_f64(&mut cursor)?,
            zxdkx: read_option_f64(&mut cursor)?,
            dif: read_f64(&mut cursor)?,
            dea: read_f64(&mut cursor)?,
            macd_hist: read_f64(&mut cursor)?,
            ma25: read_option_f64(&mut cursor)?,
            ma60: read_option_f64(&mut cursor)?,
            ma144: read_option_f64(&mut cursor)?,
            weekly_ma_bull: read_bool(&mut cursor)?,
            max_vol_not_bearish: read_bool(&mut cursor)?,
            v_shrink: read_bool(&mut cursor)?,
            safe_mode: read_bool(&mut cursor)?,
            lt_filter: read_bool(&mut cursor)?,
        });
    }
    Ok(rows)
}

fn write_string(out: &mut Vec<u8>, value: &str) -> anyhow::Result<()> {
    let bytes = value.as_bytes();
    write_u16(out, bytes.len() as u16)?;
    out.write_all(bytes)?;
    Ok(())
}

fn read_string(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<String> {
    let len = read_u16(cursor)? as usize;
    let mut bytes = vec![0_u8; len];
    cursor.read_exact(&mut bytes)?;
    Ok(String::from_utf8(bytes)?)
}

fn write_bool(out: &mut Vec<u8>, value: bool) -> anyhow::Result<()> {
    out.write_all(&[u8::from(value)])?;
    Ok(())
}

fn read_bool(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<bool> {
    let mut bytes = [0_u8; 1];
    cursor.read_exact(&mut bytes)?;
    Ok(bytes[0] != 0)
}

fn write_option_f64(out: &mut Vec<u8>, value: Option<f64>) -> anyhow::Result<()> {
    match value {
        Some(value) => {
            write_bool(out, true)?;
            write_f64(out, value)?;
        }
        None => {
            write_bool(out, false)?;
        }
    }
    Ok(())
}

fn read_option_f64(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<Option<f64>> {
    if read_bool(cursor)? {
        Ok(Some(read_f64(cursor)?))
    } else {
        Ok(None)
    }
}

fn write_u16(out: &mut Vec<u8>, value: u16) -> anyhow::Result<()> {
    out.write_all(&value.to_le_bytes())?;
    Ok(())
}

fn read_u16(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<u16> {
    let mut bytes = [0_u8; 2];
    cursor.read_exact(&mut bytes)?;
    Ok(u16::from_le_bytes(bytes))
}

fn write_u64(out: &mut Vec<u8>, value: u64) -> anyhow::Result<()> {
    out.write_all(&value.to_le_bytes())?;
    Ok(())
}

fn read_u64(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<u64> {
    let mut bytes = [0_u8; 8];
    cursor.read_exact(&mut bytes)?;
    Ok(u64::from_le_bytes(bytes))
}

fn write_i32(out: &mut Vec<u8>, value: i32) -> anyhow::Result<()> {
    out.write_all(&value.to_le_bytes())?;
    Ok(())
}

fn read_i32(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<i32> {
    let mut bytes = [0_u8; 4];
    cursor.read_exact(&mut bytes)?;
    Ok(i32::from_le_bytes(bytes))
}

fn write_f64(out: &mut Vec<u8>, value: f64) -> anyhow::Result<()> {
    out.write_all(&value.to_le_bytes())?;
    Ok(())
}

fn read_f64(cursor: &mut Cursor<&[u8]>) -> anyhow::Result<f64> {
    let mut bytes = [0_u8; 8];
    cursor.read_exact(&mut bytes)?;
    Ok(f64::from_le_bytes(bytes))
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

    use super::*;

    fn prepared_row(code: &str, day: u32) -> PreparedRow {
        PreparedRow {
            ts_code: code.to_string(),
            trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
            open: 10.0,
            high: 11.0,
            low: 9.0,
            close: 10.5,
            volume: 100.0,
            turnover_n: 1000.0,
            k: 50.0,
            d: 50.0,
            j: 50.0,
            zxdq: Some(10.0),
            zxdkx: Some(9.5),
            dif: 0.1,
            dea: 0.0,
            macd_hist: 0.1,
            ma25: Some(10.0),
            ma60: Some(9.0),
            ma144: Some(8.0),
            weekly_ma_bull: true,
            max_vol_not_bearish: true,
            v_shrink: true,
            safe_mode: true,
            lt_filter: true,
        }
    }

    #[test]
    fn cache_paths_match_runtime_layout() {
        let root = PathBuf::from("/tmp/runtime");
        let pick = NaiveDate::from_ymd_opt(2026, 5, 26).unwrap();
        assert_eq!(
            prepared_cache_data_path(&root, pick),
            PathBuf::from("/tmp/runtime/prepared/2026-05-26.bin")
        );
        assert_eq!(
            candidate_output_path(&root, pick, Method::B2),
            PathBuf::from("/tmp/runtime/candidates/2026-05-26.b2.json")
        );
    }

    #[test]
    fn metadata_match_requires_window_and_method() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 26).unwrap();
        let start = NaiveDate::from_ymd_opt(2025, 5, 25).unwrap();
        let rows = vec![prepared_row("000001.SZ", 26)];
        let metadata = build_metadata(Method::B1, pick, start, pick, &rows);
        assert!(metadata_matches(
            &metadata,
            Method::Dribull,
            pick,
            start,
            pick
        ));
        assert!(!metadata_matches(
            &metadata,
            Method::B1,
            pick,
            start.succ_opt().unwrap(),
            pick
        ));
    }

    #[test]
    fn prepared_cache_round_trips_rows() {
        let temp = tempfile::tempdir().unwrap();
        let pick = NaiveDate::from_ymd_opt(2026, 5, 26).unwrap();
        let start = NaiveDate::from_ymd_opt(2025, 5, 25).unwrap();
        let rows = vec![prepared_row("000001.SZ", 26), prepared_row("000002.SZ", 26)];
        write_prepared_cache(temp.path(), Method::B1, pick, start, pick, &rows).unwrap();
        let loaded = load_prepared_cache(temp.path(), Method::B2, pick, start, pick)
            .unwrap()
            .unwrap();
        assert_eq!(loaded, rows);
    }
}
