use std::collections::{BTreeMap, BTreeSet};
use std::io::{Cursor, Read};
use std::path::PathBuf;

use chrono::NaiveDate;
use serde_json::{Value, json};
use stock_select::cache::{PreparedCacheMetadata, decode_prepared_cache_rows};
use stock_select::model::PreparedRow;

#[derive(Debug, Clone, Copy)]
struct DiffStats {
    n: usize,
    mean_diff: f64,
    mae: f64,
    median_abs: f64,
    p90_abs: f64,
    max_abs: f64,
    mean_abs_rel: Option<f64>,
}

fn main() -> anyhow::Result<()> {
    let pick_date = arg_value("--pick-date").unwrap_or_else(|| "2026-06-05".to_string());
    let cache_path = PathBuf::from(
        arg_value("--cache").unwrap_or_else(|| format!("runtime/prepared/{pick_date}.bin")),
    );
    let factors_path = PathBuf::from(
        arg_value("--factors")
            .unwrap_or_else(|| format!("runtime/factors/{pick_date}.b2/factors.json")),
    );
    let reference_cache_path = arg_value("--reference-cache").map(PathBuf::from);
    let reference_factors_path = arg_value("--reference-factors")
        .map(PathBuf::from)
        .unwrap_or_else(|| factors_path.clone());
    let pick_date = NaiveDate::parse_from_str(&pick_date, "%Y-%m-%d")?;

    let factor_payload: Value = serde_json::from_slice(&std::fs::read(&factors_path)?)?;
    let reference_factor_payload: Value =
        serde_json::from_slice(&std::fs::read(&reference_factors_path)?)?;
    let candidate_codes = factor_payload["rows"]
        .as_array()
        .unwrap_or(&Vec::new())
        .iter()
        .filter_map(|row| row["code"].as_str())
        .map(str::to_string)
        .collect::<BTreeSet<_>>();
    let first_factors = reference_factor_payload["rows"]
        .as_array()
        .and_then(|rows| rows.first())
        .and_then(|row| row["factors"].as_object())
        .cloned()
        .unwrap_or_default();

    let rows = load_prepared_rows(&cache_path)?;
    let reference_rows = match reference_cache_path.as_ref() {
        Some(path) => load_prepared_rows(path)?,
        None => rows.clone(),
    };
    let reference_latest = reference_rows
        .iter()
        .filter(|row| row.trade_date == pick_date)
        .map(|row| (row.ts_code.clone(), row.clone()))
        .collect::<BTreeMap<_, _>>();

    let mut histories: BTreeMap<String, Vec<PreparedRow>> = BTreeMap::new();
    let mut latest_all = Vec::new();
    for row in rows {
        if row.trade_date == pick_date {
            latest_all.push(row.clone());
        }
        if candidate_codes.contains(&row.ts_code) {
            histories.entry(row.ts_code.clone()).or_default().push(row);
        }
    }
    for history in histories.values_mut() {
        history.sort_by_key(|row| row.trade_date);
    }

    let mut comparisons: BTreeMap<&str, Vec<(Option<f64>, Option<f64>)>> = BTreeMap::new();
    for history in histories.values() {
        let Some(latest) = history.last() else {
            continue;
        };
        let Some(reference) = reference_latest.get(&latest.ts_code) else {
            continue;
        };
        let close = history.iter().map(|row| row.close).collect::<Vec<_>>();
        let high = history.iter().map(|row| row.high).collect::<Vec<_>>();
        let low = history.iter().map(|row| row.low).collect::<Vec<_>>();
        let volume = history.iter().map(|row| row.volume).collect::<Vec<_>>();
        let db = &reference.db_factors;

        push_pair(
            &mut comparisons,
            "chip_turnover_from_turnover_rate_vs_db_chip_turnover",
            latest.turnover_rate.map(|value| value / 100.0),
            db.get("chip_turnover").copied(),
        );
        for (name, value) in [
            ("close", Some(latest.close)),
            ("open_close_mid", Some((latest.open + latest.close) / 2.0)),
            (
                "ohlc4",
                Some((latest.open + latest.high + latest.low + latest.close) / 4.0),
            ),
            (
                "hlc3",
                Some((latest.high + latest.low + latest.close) / 3.0),
            ),
        ] {
            let key = format!("chip_vwap_proxy_{name}_vs_db_chip_vwap");
            push_pair_owned(&mut comparisons, key, value, db.get("chip_vwap").copied());
        }
        let (dist_up, dist_down) = local_limit_dist(history);
        push_pair(
            &mut comparisons,
            "local_dist_to_up_limit_vs_db",
            dist_up,
            db.get("dist_to_up_limit_pct").copied(),
        );
        push_pair(
            &mut comparisons,
            "local_dist_to_down_limit_vs_db",
            dist_down,
            db.get("dist_to_down_limit_pct").copied(),
        );
        push_pair(
            &mut comparisons,
            "boll_width20_population_vs_db",
            boll_width(&close, 20, false),
            db.get("boll_width_pct").copied(),
        );
        push_pair(
            &mut comparisons,
            "boll_width20_sample_vs_db",
            boll_width(&close, 20, true),
            db.get("boll_width_pct").copied(),
        );
        push_pair(
            &mut comparisons,
            "bias6_vs_db_bias1",
            bias(&close, 6),
            db.get("bias1_qfq").copied(),
        );
        push_pair(
            &mut comparisons,
            "roc12_vs_db_roc",
            roc(&close, 12),
            db.get("roc_qfq").copied(),
        );
        push_pair(
            &mut comparisons,
            "mtm12_vs_db_mtm",
            mtm(&close, 12),
            db.get("mtm_qfq").copied(),
        );
        push_pair(
            &mut comparisons,
            "wr10_vs_db_wr",
            wr(&high, &low, &close, 10),
            db.get("wr_qfq").copied(),
        );
        push_pair(
            &mut comparisons,
            "wr10_positive_vs_db_wr",
            wr_positive(&high, &low, &close, 10),
            db.get("wr_qfq").copied(),
        );
        push_pair(
            &mut comparisons,
            "wr14_vs_db_wr",
            wr(&high, &low, &close, 14),
            db.get("wr_qfq").copied(),
        );
        push_pair(
            &mut comparisons,
            "wr14_positive_vs_db_wr",
            wr_positive(&high, &low, &close, 14),
            db.get("wr_qfq").copied(),
        );
        push_pair(
            &mut comparisons,
            "psy12_vs_db_psy",
            psy(&close, 12),
            db.get("psy_qfq").copied(),
        );
        push_pair(
            &mut comparisons,
            "vr24_vs_db_vr",
            vr(&close, &volume, 24),
            db.get("vr_qfq").copied(),
        );
        push_pair(
            &mut comparisons,
            "obv_raw_vs_db_obv",
            obv(&close, &volume),
            db.get("obv_qfq").copied(),
        );
    }

    let mut stats = serde_json::Map::new();
    for (key, pairs) in comparisons {
        stats.insert(key.to_string(), stats_json(diff_stats(&pairs)));
    }

    let market_local = local_market_state(&reference_rows, &latest_all, pick_date);
    let market_first = [
        "market_up_ratio",
        "market_ge5_ratio",
        "market_le_minus5_ratio",
        "market_median_pct_chg",
        "market_amount_ma5_ratio",
        "market_approx_limit_up_count",
        "market_approx_limit_down_count",
    ]
    .into_iter()
    .map(|key| {
        (
            key.to_string(),
            json!({
                    "local": market_local.get(key).copied(),
                    "artifact_first": first_factors.get(key).and_then(Value::as_f64),
            }),
        )
    })
    .collect::<serde_json::Map<_, _>>();

    println!(
        "{}",
        serde_json::to_string_pretty(&json!({
            "pick_date": pick_date,
            "candidate_count": candidate_codes.len(),
            "history_count": histories.len(),
            "latest_market_rows": latest_all.len(),
            "reference_latest_rows": reference_latest.len(),
            "comparisons": stats,
            "market_local_vs_artifact_first": market_first,
        }))?
    );
    Ok(())
}

fn load_prepared_rows(path: &PathBuf) -> anyhow::Result<Vec<PreparedRow>> {
    let bytes = std::fs::read(path)?;
    let schema_version = prepared_cache_schema_version(path)?;
    if schema_version >= 4 {
        return decode_prepared_cache_rows(&bytes);
    }
    decode_legacy_prepared_cache_rows(&bytes)
}

fn prepared_cache_schema_version(path: &PathBuf) -> anyhow::Result<u32> {
    let mut meta_path = path.clone();
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| anyhow::anyhow!("invalid cache path"))?;
    let meta_name = file_name
        .strip_suffix(".bin")
        .map(|stem| format!("{stem}.meta.json"))
        .ok_or_else(|| anyhow::anyhow!("cache path must end with .bin"))?;
    meta_path.set_file_name(meta_name);
    let metadata: PreparedCacheMetadata = serde_json::from_slice(&std::fs::read(meta_path)?)?;
    Ok(metadata.schema_version)
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

fn decode_legacy_prepared_cache_rows(bytes: &[u8]) -> anyhow::Result<Vec<PreparedRow>> {
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
            turnover_rate: read_option_f64(&mut cursor)?,
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
            chg_d: read_option_f64(&mut cursor)?,
            weekly_ma_bull: read_bool(&mut cursor)?,
            max_vol_not_bearish: read_bool(&mut cursor)?,
            v_shrink: read_bool(&mut cursor)?,
            safe_mode: read_bool(&mut cursor)?,
            lt_filter: read_bool(&mut cursor)?,
            yellow_b1: read_bool(&mut cursor)?,
            db_factors: BTreeMap::new(),
        });
    }
    Ok(rows)
}

fn arg_value(name: &str) -> Option<String> {
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == name {
            return args.next();
        }
        if let Some(value) = arg.strip_prefix(&format!("{name}=")) {
            return Some(value.to_string());
        }
    }
    None
}

fn push_pair(
    comparisons: &mut BTreeMap<&str, Vec<(Option<f64>, Option<f64>)>>,
    key: &'static str,
    local: Option<f64>,
    reference: Option<f64>,
) {
    comparisons.entry(key).or_default().push((local, reference));
}

fn push_pair_owned(
    comparisons: &mut BTreeMap<&str, Vec<(Option<f64>, Option<f64>)>>,
    key: String,
    local: Option<f64>,
    reference: Option<f64>,
) {
    let key: &'static str = Box::leak(key.into_boxed_str());
    comparisons.entry(key).or_default().push((local, reference));
}

fn diff_stats(pairs: &[(Option<f64>, Option<f64>)]) -> Option<DiffStats> {
    let mut diffs = Vec::new();
    let mut abs_diffs = Vec::new();
    let mut rel_diffs = Vec::new();
    for (local, reference) in pairs {
        let (Some(local), Some(reference)) = (local, reference) else {
            continue;
        };
        if !local.is_finite() || !reference.is_finite() {
            continue;
        }
        let diff = local - reference;
        diffs.push(diff);
        abs_diffs.push(diff.abs());
        if *reference != 0.0 {
            rel_diffs.push(diff.abs() / reference.abs());
        }
    }
    if diffs.is_empty() {
        return None;
    }
    abs_diffs.sort_by(f64::total_cmp);
    let mean_diff = diffs.iter().sum::<f64>() / diffs.len() as f64;
    let mae = abs_diffs.iter().sum::<f64>() / abs_diffs.len() as f64;
    let mean_abs_rel = if rel_diffs.is_empty() {
        None
    } else {
        Some(rel_diffs.iter().sum::<f64>() / rel_diffs.len() as f64)
    };
    Some(DiffStats {
        n: diffs.len(),
        mean_diff,
        mae,
        median_abs: median_sorted(&abs_diffs),
        p90_abs: percentile_sorted(&abs_diffs, 0.9),
        max_abs: *abs_diffs.last().unwrap_or(&0.0),
        mean_abs_rel,
    })
}

fn stats_json(stats: Option<DiffStats>) -> Value {
    match stats {
        Some(stats) => json!({
            "n": stats.n,
            "mean_diff": round6(stats.mean_diff),
            "mae": round6(stats.mae),
            "median_abs": round6(stats.median_abs),
            "p90_abs": round6(stats.p90_abs),
            "max_abs": round6(stats.max_abs),
            "mean_abs_rel": stats.mean_abs_rel.map(round6),
        }),
        None => json!({"n": 0}),
    }
}

fn round6(value: f64) -> f64 {
    (value * 1_000_000.0).round() / 1_000_000.0
}

fn median_sorted(values: &[f64]) -> f64 {
    let mid = values.len() / 2;
    if values.len() % 2 == 0 {
        (values[mid - 1] + values[mid]) / 2.0
    } else {
        values[mid]
    }
}

fn percentile_sorted(values: &[f64], percentile: f64) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let idx = ((values.len() - 1) as f64 * percentile).round() as usize;
    values[idx.min(values.len() - 1)]
}

fn limit_pct(code: &str) -> f64 {
    let symbol = code.split('.').next().unwrap_or(code);
    if code.ends_with(".BJ") || symbol.starts_with('4') || symbol.starts_with('8') {
        0.30
    } else if symbol.starts_with("300")
        || symbol.starts_with("301")
        || symbol.starts_with("688")
        || symbol.starts_with("689")
    {
        0.20
    } else {
        0.10
    }
}

fn local_limit_dist(history: &[PreparedRow]) -> (Option<f64>, Option<f64>) {
    let Some(latest) = history.last() else {
        return (None, None);
    };
    let Some(previous) = history.iter().rev().nth(1) else {
        return (None, None);
    };
    if latest.close == 0.0 {
        return (None, None);
    }
    let pct = limit_pct(&latest.ts_code);
    let up_limit = (previous.close * (1.0 + pct) * 100.0).round() / 100.0;
    let down_limit = (previous.close * (1.0 - pct) * 100.0).round() / 100.0;
    (
        Some((up_limit - latest.close) / latest.close * 100.0),
        Some((latest.close - down_limit) / latest.close * 100.0),
    )
}

fn tail(values: &[f64], n: usize) -> Option<&[f64]> {
    (values.len() >= n).then(|| &values[values.len() - n..])
}

fn boll_width(close: &[f64], n: usize, sample: bool) -> Option<f64> {
    let values = tail(close, n)?;
    let mean = values.iter().sum::<f64>() / n as f64;
    if mean == 0.0 {
        return None;
    }
    let denom = if sample && n > 1 { n - 1 } else { n } as f64;
    let variance = values
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / denom;
    Some(4.0 * variance.sqrt() / mean * 100.0)
}

fn bias(close: &[f64], n: usize) -> Option<f64> {
    let values = tail(close, n)?;
    let mean = values.iter().sum::<f64>() / n as f64;
    (mean != 0.0).then_some((close.last()? - mean) / mean * 100.0)
}

fn roc(close: &[f64], n: usize) -> Option<f64> {
    if close.len() <= n {
        return None;
    }
    let base = close[close.len() - 1 - n];
    (base != 0.0).then_some((close.last()? - base) / base * 100.0)
}

fn mtm(close: &[f64], n: usize) -> Option<f64> {
    if close.len() <= n {
        return None;
    }
    Some(close.last()? - close[close.len() - 1 - n])
}

fn wr(high: &[f64], low: &[f64], close: &[f64], n: usize) -> Option<f64> {
    let high = tail(high, n)?;
    let low = tail(low, n)?;
    let highest = high.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let lowest = low.iter().copied().fold(f64::INFINITY, f64::min);
    (highest != lowest).then_some((close.last()? - highest) / (highest - lowest) * 100.0)
}

fn wr_positive(high: &[f64], low: &[f64], close: &[f64], n: usize) -> Option<f64> {
    let high = tail(high, n)?;
    let low = tail(low, n)?;
    let highest = high.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let lowest = low.iter().copied().fold(f64::INFINITY, f64::min);
    (highest != lowest).then_some((highest - close.last()?) / (highest - lowest) * 100.0)
}

fn psy(close: &[f64], n: usize) -> Option<f64> {
    if close.len() <= n {
        return None;
    }
    let start = close.len() - n;
    let ups = (start..close.len())
        .filter(|idx| close[*idx] > close[*idx - 1])
        .count();
    Some(ups as f64 / n as f64 * 100.0)
}

fn vr(close: &[f64], volume: &[f64], n: usize) -> Option<f64> {
    if close.len() <= n || volume.len() != close.len() {
        return None;
    }
    let start = close.len() - n;
    let (mut av, mut bv, mut cv) = (0.0, 0.0, 0.0);
    for idx in start..close.len() {
        if close[idx] > close[idx - 1] {
            av += volume[idx];
        } else if close[idx] < close[idx - 1] {
            bv += volume[idx];
        } else {
            cv += volume[idx];
        }
    }
    let denominator = bv + cv / 2.0;
    (denominator != 0.0).then_some((av + cv / 2.0) / denominator * 100.0)
}

fn obv(close: &[f64], volume: &[f64]) -> Option<f64> {
    if close.len() < 2 || volume.len() != close.len() {
        return None;
    }
    let mut total = 0.0;
    for idx in 1..close.len() {
        if close[idx] > close[idx - 1] {
            total += volume[idx];
        } else if close[idx] < close[idx - 1] {
            total -= volume[idx];
        }
    }
    Some(total)
}

fn local_market_state(
    all_rows: &[PreparedRow],
    latest_rows: &[PreparedRow],
    pick_date: NaiveDate,
) -> BTreeMap<&'static str, f64> {
    let changes = latest_rows
        .iter()
        .filter_map(|row| row.chg_d.filter(|value| value.is_finite()))
        .collect::<Vec<_>>();
    let mut output = BTreeMap::new();
    if changes.is_empty() {
        return output;
    }
    output.insert(
        "market_up_ratio",
        changes.iter().filter(|value| **value > 0.0).count() as f64 / changes.len() as f64,
    );
    output.insert(
        "market_ge5_ratio",
        changes.iter().filter(|value| **value >= 5.0).count() as f64 / changes.len() as f64,
    );
    output.insert(
        "market_le_minus5_ratio",
        changes.iter().filter(|value| **value <= -5.0).count() as f64 / changes.len() as f64,
    );
    let mut sorted = changes.clone();
    sorted.sort_by(f64::total_cmp);
    output.insert("market_median_pct_chg", median_sorted(&sorted));
    if let Some(ratio) = market_amount_ma5_ratio(all_rows, pick_date) {
        output.insert("market_amount_ma5_ratio", ratio);
    }

    let mut up_limit = 0.0;
    let mut down_limit = 0.0;
    let mut by_code = BTreeMap::<String, Vec<PreparedRow>>::new();
    for row in all_rows {
        by_code
            .entry(row.ts_code.clone())
            .or_default()
            .push(row.clone());
    }
    for history in by_code.values_mut() {
        history.sort_by_key(|row| row.trade_date);
        if history
            .last()
            .is_some_and(|row| row.trade_date == pick_date)
        {
            let (up, down) = local_limit_dist(history);
            if up.is_some_and(|value| value.is_finite() && value <= 0.2) {
                up_limit += 1.0;
            }
            if down.is_some_and(|value| value.is_finite() && value <= 0.2) {
                down_limit += 1.0;
            }
        }
    }
    output.insert("market_approx_limit_up_count", up_limit);
    output.insert("market_approx_limit_down_count", down_limit);
    output
}

fn market_amount_ma5_ratio(rows: &[PreparedRow], pick_date: NaiveDate) -> Option<f64> {
    let mut by_date = BTreeMap::<NaiveDate, f64>::new();
    for row in rows {
        if row.trade_date > pick_date {
            continue;
        }
        let amount = ((row.open + row.close) / 2.0) * row.volume;
        if amount.is_finite() {
            *by_date.entry(row.trade_date).or_default() += amount;
        }
    }
    let daily_amounts = by_date.into_iter().collect::<Vec<_>>();
    let idx = daily_amounts
        .iter()
        .position(|(trade_date, _amount)| *trade_date == pick_date)?;
    let start = idx.saturating_sub(4);
    let window = &daily_amounts[start..=idx];
    let base = window.iter().map(|(_date, amount)| *amount).sum::<f64>() / window.len() as f64;
    let amount = daily_amounts[idx].1;
    (base != 0.0 && amount.is_finite() && base.is_finite()).then_some(amount / base)
}
