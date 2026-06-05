use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::str::FromStr;

use chrono::{Duration, NaiveDate};
use serde_json::json;

use crate::cache::{
    candidate_output_path, load_prepared_cache, write_prepared_cache, write_prepared_cache_for_mode,
};
use crate::factors::registry::{build_candidate_factor_rows, write_factor_artifact};
use crate::factors::series::rolling_mean_series;
use crate::factors::zx::zx_lines;
use crate::intraday::{IntradaySnapshotProvider, build_intraday_market_rows, fetch_rt_k_snapshot};
use crate::model::{MarketRow, Method, PreparedRow, ScreenResult};
use crate::strategies::b2::run_b2_strategy;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PoolSource {
    TurnoverTop,
    Custom,
}

impl PoolSource {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::TurnoverTop => "turnover-top",
            Self::Custom => "custom",
        }
    }
}

impl FromStr for PoolSource {
    type Err = anyhow::Error;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "turnover-top" => Ok(Self::TurnoverTop),
            "custom" => Ok(Self::Custom),
            _ => anyhow::bail!("unsupported pool source: {value}"),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScreenRequest {
    pub method: Method,
    pub pick_date: NaiveDate,
    pub runtime_root: PathBuf,
    pub dsn: String,
    pub recompute: bool,
    pub pool_source: PoolSource,
    pub pool_file: Option<PathBuf>,
    pub export_factors: bool,
    pub environment_state: Option<String>,
}

pub fn screen_window(pick_date: NaiveDate) -> (NaiveDate, NaiveDate) {
    (pick_date - Duration::days(366), pick_date)
}

pub fn intraday_candidate_output_path(
    runtime_root: &Path,
    pick_date: NaiveDate,
    method: Method,
) -> PathBuf {
    runtime_root.join("candidates").join(format!(
        "{}.intraday.{}.json",
        pick_date.format("%Y-%m-%d"),
        method.as_str()
    ))
}

pub fn run_screen_with_loader<F>(request: ScreenRequest, loader: F) -> anyhow::Result<PathBuf>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
{
    if request.method != Method::B2 {
        anyhow::bail!("{} screen is not implemented", request.method.as_str());
    }
    let (start_date, end_date) = screen_window(request.pick_date);
    let prepared = if request.recompute {
        load_and_prepare(&request, start_date, end_date, loader)?
    } else {
        match load_prepared_cache(
            &request.runtime_root,
            request.method,
            request.pick_date,
            start_date,
            end_date,
        )? {
            Some(rows) => rows,
            None => load_and_prepare(&request, start_date, end_date, loader)?,
        }
    };
    if !prepared
        .iter()
        .any(|row| row.trade_date == request.pick_date)
    {
        anyhow::bail!(
            "No prepared rows found for pick_date {}.",
            request.pick_date
        );
    }

    let (pool, resolved_pool_file) = match request.pool_source {
        PoolSource::TurnoverTop => (
            filter_turnover_top_pool(&prepared, request.pick_date, 5000),
            None,
        ),
        PoolSource::Custom => {
            let resolved = resolve_custom_pool(&request)?;
            (
                filter_custom_pool(&prepared, request.pick_date, &resolved.codes)?,
                Some(resolved.path),
            )
        }
    };
    let (candidates, stats) = run_b2_strategy(&pool, request.pick_date);
    let result = ScreenResult {
        mode: None,
        method: request.method,
        pick_date: request.pick_date,
        trade_date: None,
        fetched_at: None,
        run_id: None,
        source: None,
        pool_source: request.pool_source.as_str().to_string(),
        pool_file: resolved_pool_file
            .as_ref()
            .map(|path| path.to_string_lossy().to_string()),
        screen_version: None,
        candidates,
        generated_at: Some("0".to_string()),
        count: Some(stats.get("selected").copied().unwrap_or(0)),
        stats,
    };
    let output_path = write_screen_result(&request.runtime_root, &result)?;
    if request.export_factors {
        write_screen_factor_artifact(&request, &result.candidates, &pool, &output_path, false)?;
    }
    Ok(output_path)
}

pub fn run_intraday_screen_with_provider<P, F>(
    request: ScreenRequest,
    provider: &P,
    fallback_trade_time: &str,
    history_loader: F,
) -> anyhow::Result<PathBuf>
where
    P: IntradaySnapshotProvider,
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
{
    run_intraday_screen_with_loaders(
        request,
        provider,
        fallback_trade_time,
        |_dsn, pick_date| Ok(pick_date - Duration::days(1)),
        history_loader,
    )
}

pub fn run_intraday_screen_with_loaders<P, Prev, F>(
    request: ScreenRequest,
    provider: &P,
    fallback_trade_time: &str,
    previous_trade_date_loader: Prev,
    history_loader: F,
) -> anyhow::Result<PathBuf>
where
    P: IntradaySnapshotProvider,
    Prev: FnOnce(&str, NaiveDate) -> anyhow::Result<NaiveDate>,
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
{
    if request.method != Method::B2 {
        anyhow::bail!("{} screen is not implemented", request.method.as_str());
    }
    let previous_trade_date = previous_trade_date_loader(&request.dsn, request.pick_date)?;
    let start_date = previous_trade_date - Duration::days(366);
    let snapshot = fetch_rt_k_snapshot(provider, request.pick_date, fallback_trade_time)?;
    let history = history_loader(&request.dsn, start_date, previous_trade_date)?;
    if history.is_empty() {
        anyhow::bail!("No market rows found between {start_date} and {previous_trade_date}.");
    }
    let market_rows = build_intraday_market_rows(history, &snapshot, request.pick_date);
    let prepared = prepare_rows(&market_rows);
    write_prepared_cache_for_mode(
        &request.runtime_root,
        request.method,
        request.pick_date,
        start_date,
        request.pick_date,
        true,
        &prepared,
    )?;
    let (pool, resolved_pool_file) = match request.pool_source {
        PoolSource::TurnoverTop => (
            filter_turnover_top_pool(&prepared, request.pick_date, 5000),
            None,
        ),
        PoolSource::Custom => {
            let resolved = resolve_custom_pool(&request)?;
            (
                filter_custom_pool(&prepared, request.pick_date, &resolved.codes)?,
                Some(resolved.path),
            )
        }
    };
    let (candidates, stats) = run_b2_strategy(&pool, request.pick_date);
    let result = ScreenResult {
        mode: Some("intraday_snapshot".to_string()),
        method: request.method,
        pick_date: request.pick_date,
        trade_date: Some(request.pick_date),
        fetched_at: Some(fallback_trade_time.to_string()),
        run_id: Some(fallback_trade_time.to_string()),
        source: Some("tushare_rt_k".to_string()),
        pool_source: request.pool_source.as_str().to_string(),
        pool_file: resolved_pool_file
            .as_ref()
            .map(|path| path.to_string_lossy().to_string()),
        screen_version: None,
        candidates,
        generated_at: Some("0".to_string()),
        count: Some(stats.get("selected").copied().unwrap_or(0)),
        stats,
    };
    let output_path =
        intraday_candidate_output_path(&request.runtime_root, request.pick_date, request.method);
    if let Some(parent) = output_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&output_path, serde_json::to_vec_pretty(&result)?)?;
    if request.export_factors {
        write_screen_factor_artifact(&request, &result.candidates, &pool, &output_path, true)?;
    }
    Ok(output_path)
}

fn write_screen_factor_artifact(
    request: &ScreenRequest,
    candidates: &[crate::model::Candidate],
    prepared_rows: &[PreparedRow],
    candidate_artifact: &Path,
    intraday: bool,
) -> anyhow::Result<PathBuf> {
    let artifact_key = screen_artifact_key(request.pick_date, intraday);
    let rows = build_candidate_factor_rows(
        candidates,
        prepared_rows,
        request.method,
        request.environment_state.as_deref(),
    );
    write_factor_artifact(
        &request.runtime_root,
        request.method,
        &artifact_key,
        &rows,
        Some(candidate_artifact),
    )
}

fn screen_artifact_key(pick_date: NaiveDate, intraday: bool) -> String {
    if intraday {
        format!("{}.intraday", pick_date.format("%Y-%m-%d"))
    } else {
        pick_date.format("%Y-%m-%d").to_string()
    }
}

fn load_and_prepare<F>(
    request: &ScreenRequest,
    start_date: NaiveDate,
    end_date: NaiveDate,
    loader: F,
) -> anyhow::Result<Vec<PreparedRow>>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
{
    let rows = loader(&request.dsn, start_date, end_date)?;
    if rows.is_empty() {
        anyhow::bail!("No market rows found between {start_date} and {end_date}.");
    }
    let prepared = prepare_rows(&rows);
    write_prepared_cache(
        &request.runtime_root,
        request.method,
        request.pick_date,
        start_date,
        end_date,
        &prepared,
    )?;
    Ok(prepared)
}

fn prepare_rows(rows: &[MarketRow]) -> Vec<PreparedRow> {
    let mut grouped = BTreeMap::<String, Vec<MarketRow>>::new();
    for row in rows {
        grouped
            .entry(row.ts_code.clone())
            .or_default()
            .push(row.clone());
    }
    let mut prepared = Vec::new();
    for (_code, mut rows) in grouped {
        rows.sort_by_key(|row| row.trade_date);
        let high = rows.iter().map(|row| row.high).collect::<Vec<_>>();
        let low = rows.iter().map(|row| row.low).collect::<Vec<_>>();
        let close = rows.iter().map(|row| row.close).collect::<Vec<_>>();
        let (k, d, j) = kdj(&high, &low, &close, 9);
        let (dif, dea, macd_hist) = macd(&close, 12, 26, 9);
        let ma25 = rolling_mean_series(&close, 25, 25);
        let ma60 = rolling_mean_series(&close, 60, 60);
        let ma144 = rolling_mean_series(&close, 144, 144);
        let (zxdq, zxdkx) = zx_lines(&close);
        for (idx, row) in rows.iter().enumerate() {
            prepared.push(PreparedRow {
                ts_code: row.ts_code.clone(),
                trade_date: row.trade_date,
                open: row.open,
                high: row.high,
                low: row.low,
                close: row.close,
                volume: row.vol,
                turnover_n: rows[..=idx]
                    .iter()
                    .rev()
                    .take(43)
                    .map(|row| ((row.open + row.close) / 2.0) * row.vol)
                    .sum(),
                turnover_rate: row.turnover_rate,
                k: k[idx],
                d: d[idx],
                j: j[idx],
                zxdq: Some(zxdq[idx]),
                zxdkx: zxdkx[idx],
                dif: dif[idx],
                dea: dea[idx],
                macd_hist: macd_hist[idx],
                ma25: ma25[idx],
                ma60: ma60[idx],
                ma144: ma144[idx],
                chg_d: (idx > 0).then(|| (row.close - close[idx - 1]) / close[idx - 1] * 100.0),
                weekly_ma_bull: false,
                max_vol_not_bearish: true,
                v_shrink: false,
                safe_mode: true,
                lt_filter: true,
                yellow_b1: false,
            });
        }
    }
    prepared.sort_by(|left, right| {
        left.ts_code
            .cmp(&right.ts_code)
            .then(left.trade_date.cmp(&right.trade_date))
    });
    prepared
}

fn ema(values: &[f64], span: usize) -> Vec<f64> {
    let alpha = 2.0 / (span as f64 + 1.0);
    let beta = 1.0 - alpha;
    let mut out = Vec::with_capacity(values.len());
    let mut prev = f64::NAN;
    let mut missing_after_valid = 0_i32;
    for value in values {
        if value.is_nan() {
            out.push(prev);
            if !prev.is_nan() {
                missing_after_valid += 1;
            }
        } else if prev.is_nan() {
            prev = *value;
            missing_after_valid = 0;
            out.push(prev);
        } else {
            let effective_alpha = alpha / (alpha + beta.powi(missing_after_valid + 1));
            let current = effective_alpha * *value + (1.0 - effective_alpha) * prev;
            out.push(current);
            prev = current;
            missing_after_valid = 0;
        }
    }
    out
}

fn macd(close: &[f64], fast: usize, slow: usize, signal: usize) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let fast_ema = ema(close, fast);
    let slow_ema = ema(close, slow);
    let dif = fast_ema
        .iter()
        .zip(slow_ema.iter())
        .map(|(fast, slow)| fast - slow)
        .collect::<Vec<_>>();
    let dea = ema(&dif, signal);
    let hist = dif
        .iter()
        .zip(dea.iter())
        .map(|(dif, dea)| dif - dea)
        .collect();
    (dif, dea, hist)
}

fn kdj(high: &[f64], low: &[f64], close: &[f64], n: usize) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    let low_n = rolling_extreme(low, n, f64::min);
    let high_n = rolling_extreme(high, n, f64::max);
    let mut k = Vec::with_capacity(high.len());
    let mut d = Vec::with_capacity(high.len());
    let mut j = Vec::with_capacity(high.len());
    let mut prev_k = 50.0;
    let mut prev_d = 50.0;
    for idx in 0..high.len() {
        let rsv = (close[idx] - low_n[idx]) / (high_n[idx] - low_n[idx] + 1e-9) * 100.0;
        let (current_k, current_d) = if idx == 0 {
            (50.0, 50.0)
        } else {
            let current_k = (2.0 * prev_k + rsv) / 3.0;
            let current_d = (2.0 * prev_d + current_k) / 3.0;
            (current_k, current_d)
        };
        k.push(current_k);
        d.push(current_d);
        j.push(3.0 * current_k - 2.0 * current_d);
        prev_k = current_k;
        prev_d = current_d;
    }
    (k, d, j)
}

fn rolling_extreme(values: &[f64], window: usize, op: fn(f64, f64) -> f64) -> Vec<f64> {
    (0..values.len())
        .map(|idx| {
            let start = idx.saturating_sub(window - 1);
            values[start..=idx]
                .iter()
                .copied()
                .reduce(op)
                .unwrap_or(f64::NAN)
        })
        .collect()
}

fn filter_turnover_top_pool(
    prepared: &[PreparedRow],
    pick_date: NaiveDate,
    top_m: usize,
) -> Vec<PreparedRow> {
    let mut ranked = prepared
        .iter()
        .filter(|row| row.trade_date == pick_date)
        .filter(|row| {
            row.ma25
                .zip(row.ma60)
                .is_some_and(|(ma25, ma60)| ma25 > ma60)
        })
        .map(|row| (row.turnover_n, row.ts_code.as_str()))
        .collect::<Vec<_>>();
    ranked.sort_by(|left, right| right.0.total_cmp(&left.0).then(left.1.cmp(right.1)));
    let pool = ranked
        .into_iter()
        .take(top_m)
        .map(|(_turnover, code)| code)
        .collect::<std::collections::BTreeSet<_>>();
    prepared
        .iter()
        .filter(|row| pool.contains(row.ts_code.as_str()))
        .cloned()
        .collect()
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct ResolvedCustomPool {
    path: PathBuf,
    codes: Vec<String>,
}

fn resolve_custom_pool(request: &ScreenRequest) -> anyhow::Result<ResolvedCustomPool> {
    let pool_file = request
        .pool_file
        .clone()
        .or_else(|| std::env::var_os("STOCK_SELECT_POOL_FILE").map(PathBuf::from))
        .unwrap_or_else(|| request.runtime_root.join("custom-pool.txt"));
    let content = std::fs::read_to_string(&pool_file).map_err(|err| {
        anyhow::anyhow!("Missing custom pool file: {}: {err}", pool_file.display())
    })?;
    let mut codes = Vec::new();
    for token in content.split_whitespace() {
        if let Some(code) = normalize_stock_code_token(token)
            && !codes.contains(&code)
        {
            codes.push(code);
        }
    }
    if codes.is_empty() {
        anyhow::bail!("Custom pool must contain at least one stock code.");
    }
    Ok(ResolvedCustomPool {
        path: pool_file,
        codes,
    })
}

fn filter_custom_pool(
    prepared: &[PreparedRow],
    pick_date: NaiveDate,
    codes: &[String],
) -> anyhow::Result<Vec<PreparedRow>> {
    let available = prepared
        .iter()
        .filter(|row| row.trade_date == pick_date)
        .map(|row| row.ts_code.as_str())
        .collect::<std::collections::BTreeSet<_>>();
    let effective = codes
        .iter()
        .filter(|code| available.contains(code.as_str()))
        .cloned()
        .collect::<std::collections::BTreeSet<_>>();
    if effective.is_empty() {
        anyhow::bail!("Effective custom pool is empty after prepared-data intersection.");
    }
    Ok(prepared
        .iter()
        .filter(|row| effective.contains(row.ts_code.as_str()))
        .cloned()
        .collect())
}

fn normalize_stock_code_token(token: &str) -> Option<String> {
    let upper = token.trim().to_ascii_uppercase();
    if upper.is_empty() {
        return None;
    }
    let digits = if upper.len() >= 6 && upper[..6].chars().all(|ch| ch.is_ascii_digit()) {
        upper[..6].to_string()
    } else {
        let chars = upper.chars().collect::<Vec<_>>();
        let mut found = None;
        for idx in 0..chars.len().saturating_sub(5) {
            let candidate = chars[idx..idx + 6].iter().collect::<String>();
            if candidate.chars().all(|ch| ch.is_ascii_digit()) {
                found = Some(candidate);
                break;
            }
        }
        found?
    };
    if upper.ends_with(".SH") || digits.starts_with('6') || digits.starts_with("688") {
        Some(format!("{digits}.SH"))
    } else {
        Some(format!("{digits}.SZ"))
    }
}

fn write_screen_result(runtime_root: &Path, result: &ScreenResult) -> anyhow::Result<PathBuf> {
    let path = candidate_output_path(runtime_root, result.pick_date, result.method);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(
        &path,
        serde_json::to_vec_pretty(&json!({
            "method": result.method,
            "pick_date": result.pick_date,
            "pool_source": result.pool_source,
            "pool_file": result.pool_file,
            "candidates": result.candidates,
            "generated_at": result.generated_at,
            "count": result.count,
            "stats": result.stats,
        }))?,
    )?;
    Ok(path)
}
