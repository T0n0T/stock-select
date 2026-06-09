use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::str::FromStr;

use chrono::{Duration, NaiveDate};
use serde_json::json;

use crate::cache::{
    candidate_output_path, load_prepared_cache, write_prepared_cache, write_prepared_cache_for_mode,
};
use crate::factors::registry::{build_candidate_factor_rows_from_refs, write_factor_artifact};
use crate::indicators::{kdj, macd, rolling_mean, rolling_sum, zx_lines};
use crate::intraday::{IntradaySnapshotProvider, build_intraday_market_rows, fetch_rt_k_snapshot};
use crate::local_factors::enrich_local_market_factors;
use crate::model::{MarketRow, Method, PreparedRow, ScreenResult};
use crate::strategies::StrategyOutput;
use crate::strategies::b2::run_b2_strategy_from_refs;
use crate::strategies::b3::run_b3_strategy_from_refs;
use crate::strategies::lsh::run_lsh_strategy_from_refs;

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
    ensure_screen_supported(request.method)?;
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
        anyhow::bail!(missing_pick_date_rows_message(
            request.pick_date,
            &prepared,
            &request.runtime_root,
            request.method,
        ));
    }

    let (pool_codes, resolved_pool_file) = match request.pool_source {
        PoolSource::TurnoverTop => (
            filter_turnover_top_pool_codes(&prepared, request.method, request.pick_date, 5000),
            None,
        ),
        PoolSource::Custom => {
            let resolved = resolve_custom_pool(&request)?;
            (
                filter_custom_pool_codes(&prepared, request.pick_date, &resolved.codes)?,
                Some(resolved.path),
            )
        }
    };
    let pool = pool_refs(&prepared, &pool_codes);
    let strategy_output = run_screen_strategy(request.method, &pool, request.pick_date)?;
    let count = strategy_output.stats.get("selected").copied().unwrap_or(0);
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
        candidates: strategy_output.candidates,
        generated_at: Some("0".to_string()),
        count: Some(count),
        stats: strategy_output.stats,
    };
    let output_path = write_screen_result(&request.runtime_root, &result)?;
    if request.export_factors {
        let prepared_refs = prepared.iter().collect::<Vec<_>>();
        write_screen_factor_artifact(
            &request,
            &result.candidates,
            &prepared_refs,
            &output_path,
            false,
        )?;
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
    ensure_screen_supported(request.method)?;
    let previous_trade_date = previous_trade_date_loader(&request.dsn, request.pick_date)?;
    let start_date = previous_trade_date - Duration::days(366);
    let snapshot = fetch_rt_k_snapshot(provider, request.pick_date, fallback_trade_time)?;
    let history = history_loader(&request.dsn, start_date, previous_trade_date)?;
    if history.is_empty() {
        anyhow::bail!("No market rows found between {start_date} and {previous_trade_date}.");
    }
    let market_rows = build_intraday_market_rows(history, &snapshot, request.pick_date);
    let prepared = prepare_rows(market_rows);
    write_prepared_cache_for_mode(
        &request.runtime_root,
        request.method,
        request.pick_date,
        start_date,
        request.pick_date,
        true,
        &prepared,
    )?;
    let (pool_codes, resolved_pool_file) = match request.pool_source {
        PoolSource::TurnoverTop => (
            filter_turnover_top_pool_codes(&prepared, request.method, request.pick_date, 5000),
            None,
        ),
        PoolSource::Custom => {
            let resolved = resolve_custom_pool(&request)?;
            (
                filter_custom_pool_codes(&prepared, request.pick_date, &resolved.codes)?,
                Some(resolved.path),
            )
        }
    };
    let pool = pool_refs(&prepared, &pool_codes);
    let strategy_output = run_screen_strategy(request.method, &pool, request.pick_date)?;
    let count = strategy_output.stats.get("selected").copied().unwrap_or(0);
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
        candidates: strategy_output.candidates,
        generated_at: Some("0".to_string()),
        count: Some(count),
        stats: strategy_output.stats,
    };
    let output_path =
        intraday_candidate_output_path(&request.runtime_root, request.pick_date, request.method);
    if let Some(parent) = output_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&output_path, serde_json::to_vec_pretty(&result)?)?;
    if request.export_factors {
        let prepared_refs = prepared.iter().collect::<Vec<_>>();
        write_screen_factor_artifact(
            &request,
            &result.candidates,
            &prepared_refs,
            &output_path,
            true,
        )?;
    }
    Ok(output_path)
}

fn missing_pick_date_rows_message(
    pick_date: NaiveDate,
    prepared: &[PreparedRow],
    runtime_root: &Path,
    method: Method,
) -> String {
    let latest = prepared.iter().map(|row| row.trade_date).max();
    let earliest = prepared.iter().map(|row| row.trade_date).min();
    let intraday_candidates = intraday_candidate_output_path(runtime_root, pick_date, method);
    let intraday_cache = crate::cache::prepared_cache_paths(runtime_root, pick_date, true);
    let mut message = format!("No prepared rows found for pick_date {pick_date}.");
    if let Some(latest) = latest {
        message.push_str(&format!(" latest cached trade_date is {latest}"));
        if let Some(earliest) = earliest {
            message.push_str(&format!("; cached window is {earliest}..{latest}"));
        }
        message.push('.');
    }
    if intraday_candidates.exists() || intraday_cache.data_path.exists() {
        message.push_str(" Intraday artifacts exist for this date; use --intraday for intraday selection, or refresh the post-market daily cache after daily_market is available.");
    } else {
        message.push_str(" Refresh the post-market daily cache after daily_market is available.");
    }
    message
}

fn write_screen_factor_artifact(
    request: &ScreenRequest,
    candidates: &[crate::model::Candidate],
    prepared_rows: &[&PreparedRow],
    candidate_artifact: &Path,
    intraday: bool,
) -> anyhow::Result<PathBuf> {
    let artifact_key = screen_artifact_key(request.pick_date, intraday);
    let rows = build_candidate_factor_rows_from_refs(
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

fn ensure_screen_supported(method: Method) -> anyhow::Result<()> {
    match method {
        Method::B2 | Method::B3 | Method::Lsh => Ok(()),
        _ => anyhow::bail!("{} screen is not implemented", method.as_str()),
    }
}

fn run_screen_strategy(
    method: Method,
    rows: &[&PreparedRow],
    pick_date: NaiveDate,
) -> anyhow::Result<StrategyOutput> {
    match method {
        Method::B2 => Ok(run_b2_strategy_from_refs(rows, pick_date)),
        Method::B3 => Ok(run_b3_strategy_from_refs(rows, pick_date)),
        Method::Lsh => Ok(run_lsh_strategy_from_refs(rows, pick_date)),
        _ => anyhow::bail!("{} screen is not implemented", method.as_str()),
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
    let prepared = prepare_rows(rows);
    if !prepared.iter().any(|row| row.trade_date == end_date) {
        return Ok(prepared);
    }
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

fn prepare_rows(mut rows: Vec<MarketRow>) -> Vec<PreparedRow> {
    enrich_local_market_factors(&mut rows);
    let mut grouped = BTreeMap::<String, Vec<MarketRow>>::new();
    for row in rows {
        let code = row.ts_code.clone();
        grouped.entry(code).or_default().push(row);
    }
    let mut prepared = Vec::with_capacity(grouped.values().map(Vec::len).sum());
    for (_code, mut rows) in grouped {
        rows.sort_by_key(|row| row.trade_date);
        let high = rows.iter().map(|row| row.high).collect::<Vec<_>>();
        let low = rows.iter().map(|row| row.low).collect::<Vec<_>>();
        let close = rows.iter().map(|row| row.close).collect::<Vec<_>>();
        let turnover_daily = rows
            .iter()
            .map(|row| ((row.open + row.close) / 2.0) * row.vol)
            .collect::<Vec<_>>();
        let turnover_n = rolling_sum(&turnover_daily, 43, 1)
            .into_iter()
            .map(|value| value.unwrap_or(0.0))
            .collect::<Vec<_>>();
        let (k, d, j) = kdj(&high, &low, &close, 9);
        let (dif, dea, macd_hist) = macd(&close, 12, 26, 9);
        let ma25 = rolling_mean(&close, 25, 25);
        let ma60 = rolling_mean(&close, 60, 60);
        let ma144 = rolling_mean(&close, 144, 144);
        let (zxdq, zxdkx) = zx_lines(&close);
        for (idx, row) in rows.into_iter().enumerate() {
            prepared.push(PreparedRow {
                ts_code: row.ts_code,
                trade_date: row.trade_date,
                open: row.open,
                high: row.high,
                low: row.low,
                close: row.close,
                volume: row.vol,
                turnover_n: turnover_n[idx],
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
                db_factors: row.db_factors,
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

fn filter_turnover_top_pool_codes(
    prepared: &[PreparedRow],
    method: Method,
    pick_date: NaiveDate,
    top_m: usize,
) -> BTreeSet<String> {
    let mut ranked = prepared
        .iter()
        .filter(|row| row.trade_date == pick_date)
        .filter(|row| turnover_top_pool_row_allowed(row, method))
        .map(|row| (row.turnover_n, row.ts_code.as_str()))
        .collect::<Vec<_>>();
    ranked.sort_by(|left, right| right.0.total_cmp(&left.0).then(left.1.cmp(right.1)));
    ranked
        .into_iter()
        .take(top_m)
        .map(|(_turnover, code)| code.to_string())
        .collect()
}

fn turnover_top_pool_row_allowed(row: &PreparedRow, method: Method) -> bool {
    match method {
        Method::B2 | Method::B3 => row
            .ma25
            .zip(row.ma60)
            .is_some_and(|(ma25, ma60)| ma25 > ma60),
        Method::Lsh => true,
        _ => true,
    }
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

fn filter_custom_pool_codes(
    prepared: &[PreparedRow],
    pick_date: NaiveDate,
    codes: &[String],
) -> anyhow::Result<BTreeSet<String>> {
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
    Ok(effective)
}

fn pool_refs<'a>(prepared: &'a [PreparedRow], pool: &BTreeSet<String>) -> Vec<&'a PreparedRow> {
    prepared
        .iter()
        .filter(|row| pool.contains(row.ts_code.as_str()))
        .collect()
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
