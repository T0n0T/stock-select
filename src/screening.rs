use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::time::Instant;

use chrono::{Duration, NaiveDate};
use serde_json::json;

use crate::cache::{
    DbNativePreparedCacheStreamWriter, MIN_DB_NATIVE_WINDOW_TRADING_DAYS, candidate_output_path,
    load_prepared_dataset, prepared_cache_start_date as cache_prepared_cache_start_date,
    write_db_native_prepared_dataset, write_prepared_cache, write_prepared_dataset_for_mode,
};
use crate::db::{
    DB_NATIVE_FACTOR_COLUMNS, DB_NATIVE_PICK_DATE_FACTOR_COLUMNS,
    DB_NATIVE_THS_SECTOR_FACTOR_COLUMNS,
};
use crate::environment::{normalize_environment_state, prepared_market_state};
use crate::factors::registry::{
    RAW_MARKET_AMOUNT_FACTOR, build_candidate_factor_rows_from_refs,
    write_factor_artifact_with_db_data_gaps,
};
use crate::indicators::{kdj, macd, rolling_mean, rolling_sum, zx_lines};
use crate::intraday::{
    IntradaySnapshotProvider, MacdPeriodState, build_intraday_market_rows,
    build_intraday_market_rows_with_macd_states, fetch_rt_k_snapshot,
};
use crate::local_factors::enrich_local_market_factors;
use crate::model::{
    DbDataGap, DbDataGapReason, IntoMarketDataset, MarketRow, Method, PreparedDataset, PreparedRow,
    ScreenResult,
};
use crate::strategies::b2::run_b2_strategy_from_refs;
use crate::strategies::scm_pbm::{run_pbm_strategy_from_refs, run_scm_strategy_from_refs};
use crate::strategies::{StrategyOutput, sort_candidates};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PoolSource {
    TurnoverTop,
    Custom,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StreamOrder {
    SymbolAndDate,
    Unordered,
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
    pub duckdb_path: String,
    pub recompute: bool,
    pub write_prepared_cache: bool,
    pub pool_source: PoolSource,
    pub pool_file: Option<PathBuf>,
    pub export_factors: bool,
    pub environment_state: Option<String>,
}

pub fn screen_window(pick_date: NaiveDate) -> (NaiveDate, NaiveDate) {
    (prepared_cache_start_date(pick_date), pick_date)
}

pub fn prepared_cache_start_date(pick_date: NaiveDate) -> NaiveDate {
    cache_prepared_cache_start_date(pick_date)
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
    run_screen_with_loaders(request, loader, false)
}

pub fn run_db_native_screen_with_loader<F>(
    request: ScreenRequest,
    loader: F,
) -> anyhow::Result<PathBuf>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
{
    run_screen_with_loaders(request, loader, true)
}

pub fn run_db_native_screen_with_dataset_loader<F>(
    request: ScreenRequest,
    loader: F,
) -> anyhow::Result<PathBuf>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<crate::model::MarketDataset>,
{
    run_screen_with_loaders(request, loader, true)
}

pub fn run_db_native_screen_with_loaders<F, S>(
    request: ScreenRequest,
    loader: F,
    _macd_state_loader: S,
) -> anyhow::Result<PathBuf>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
    S: FnOnce(&str, &[String], NaiveDate) -> anyhow::Result<Vec<MacdPeriodState>>,
{
    run_screen_with_loaders(request, loader, true)
}

pub fn run_db_native_screen_with_dataset_loaders<F, S>(
    request: ScreenRequest,
    loader: F,
    _macd_state_loader: S,
) -> anyhow::Result<PathBuf>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<crate::model::MarketDataset>,
    S: FnOnce(&str, &[String], NaiveDate) -> anyhow::Result<Vec<MacdPeriodState>>,
{
    run_screen_with_loaders(request, loader, true)
}

pub fn run_db_native_scm_screen_with_stream_loader<F>(
    request: ScreenRequest,
    mut loader: F,
) -> anyhow::Result<PathBuf>
where
    F: for<'a> FnMut(
        &str,
        NaiveDate,
        NaiveDate,
        StreamOrder,
        &'a mut dyn FnMut(MarketRow) -> anyhow::Result<()>,
    ) -> anyhow::Result<BTreeMap<String, DbDataGap>>,
{
    if request.method != Method::Scm || !request.recompute {
        anyhow::bail!("streaming screen requires SCM recompute.");
    }
    let (start_date, end_date) = screen_window(request.pick_date);
    let mut cache_writer = if request.write_prepared_cache {
        Some(DbNativePreparedCacheStreamWriter::new(
            &request.runtime_root,
            request.method,
            request.pick_date,
            start_date,
            end_date,
            0,
            scm_prepared_cache_factor_keys(),
            BTreeMap::new(),
        )?)
    } else {
        None
    };
    let cache_write_started = Instant::now();
    let mut strategy_by_code = Vec::new();
    let mut pick_date_turnovers = Vec::new();
    let mut factor_history_rows = Vec::new();
    let mut factor_pick_date_rows = Vec::new();
    let summary = timed_stage("stream_prepare_strategy", || {
        stream_market_symbol_groups(
            &mut loader,
            &request.duckdb_path,
            start_date,
            end_date,
            |rows| {
                let prepared = prepare_symbol_rows(rows)?;
                let code = prepared[0].ts_code.clone();
                pick_date_turnovers.extend(
                    prepared
                        .iter()
                        .filter(|row| row.trade_date == request.pick_date)
                        .map(|row| (row.turnover_n, row.ts_code.clone())),
                );
                let references = prepared.iter().collect::<Vec<_>>();
                let strategy = run_screen_strategy(Method::Scm, &references, request.pick_date)?;
                if request.export_factors {
                    if !strategy.candidates.is_empty() {
                        factor_history_rows.extend(
                            prepared
                                .iter()
                                .filter(|row| row.trade_date < request.pick_date)
                                .cloned(),
                        );
                    }
                    factor_pick_date_rows.extend(
                        prepared
                            .iter()
                            .filter(|row| row.trade_date == request.pick_date)
                            .cloned(),
                    );
                }
                strategy_by_code.push((code, strategy));
                if let Some(writer) = cache_writer.as_mut() {
                    writer.write_rows(&prepared)?;
                }
                Ok(())
            },
        )
    })?;
    ensure_streamed_db_native_window(&summary, start_date, end_date)?;
    if let Some(writer) = cache_writer.as_mut() {
        writer.set_db_data_gaps(summary.db_data_gaps.clone());
    }
    if !summary.trade_dates.contains(&request.pick_date) {
        return Err(missing_pick_date_rows_error(
            request.pick_date,
            summary.trade_dates.first().copied(),
            summary.trade_dates.last().copied(),
            &request.runtime_root,
            request.method,
        ));
    }
    if let Some(writer) = cache_writer.take() {
        writer.finish(
            summary.row_count,
            summary.symbol_count,
            &summary.trade_dates,
        )?;
        eprintln!(
            "[screen] prepared cache wrote rows={} elapsed={:.3}s",
            summary.row_count,
            cache_write_started.elapsed().as_secs_f64()
        );
    }

    let (pool_codes, resolved_pool_file) = match request.pool_source {
        PoolSource::TurnoverTop => (scm_turnover_top_pool_codes(pick_date_turnovers, 5000), None),
        PoolSource::Custom => {
            let resolved = resolve_custom_pool(&request)?;
            let available = pick_date_turnovers
                .iter()
                .map(|(_, code)| code.as_str())
                .collect::<BTreeSet<_>>();
            let effective = resolved
                .codes
                .iter()
                .filter(|code| available.contains(code.as_str()))
                .cloned()
                .collect::<BTreeSet<_>>();
            if effective.is_empty() {
                anyhow::bail!("Effective custom pool is empty after prepared-data intersection.");
            }
            (effective, Some(resolved.path))
        }
    };
    let mut candidates = Vec::new();
    let mut stats = BTreeMap::new();
    for (code, output) in strategy_by_code {
        if !pool_codes.contains(code.as_str()) {
            continue;
        }
        for (key, value) in output.stats {
            *stats.entry(key).or_default() += value;
        }
        candidates.extend(output.candidates);
    }
    sort_candidates(&mut candidates);
    let count = stats.get("selected").copied().unwrap_or(0);
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
        count: Some(count),
        stats,
    };
    let output_path = timed_stage("write_candidates", || {
        write_screen_result(&request.runtime_root, &result)
    })?;
    if request.export_factors {
        timed_stage("export_factors", || {
            factor_history_rows
                .retain(|row| pool_codes.contains(row.ts_code.as_str()));
            factor_history_rows.extend(factor_pick_date_rows);
            let prepared_refs = factor_history_rows.iter().collect::<Vec<_>>();
            write_screen_factor_artifact(
                &request,
                &result.candidates,
                &prepared_refs,
                &output_path,
                false,
                &summary.db_data_gaps,
            )
        })?;
    }
    Ok(output_path)
}

#[derive(Debug, Clone, PartialEq)]
struct StreamedMarketSummary {
    row_count: usize,
    symbol_count: usize,
    trade_dates: BTreeSet<NaiveDate>,
    db_data_gaps: BTreeMap<String, DbDataGap>,
}

const LOCAL_PREPARED_FACTOR_KEYS: [&str; 8] = [
    "boll_width_pct",
    "bias1_qfq",
    "roc_qfq",
    "mtm_qfq",
    "psy_qfq",
    "wr_qfq",
    "dist_to_up_limit_pct",
    "dist_to_down_limit_pct",
];

fn scm_prepared_cache_factor_keys() -> Vec<String> {
    let mut factor_keys = HashSet::new();
    factor_keys.extend(DB_NATIVE_FACTOR_COLUMNS.iter().copied());
    factor_keys.extend(DB_NATIVE_PICK_DATE_FACTOR_COLUMNS.iter().copied());
    factor_keys.extend(DB_NATIVE_THS_SECTOR_FACTOR_COLUMNS.iter().copied());
    factor_keys.extend(LOCAL_PREPARED_FACTOR_KEYS);
    factor_keys.insert(RAW_MARKET_AMOUNT_FACTOR);
    factor_keys.remove("_source_close_qfq");
    let mut factor_keys = factor_keys
        .into_iter()
        .map(str::to_string)
        .collect::<Vec<_>>();
    factor_keys.sort_unstable();
    factor_keys
}

fn stream_market_symbol_groups<F, V>(
    loader: &mut F,
    duckdb_path: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
    visit: V,
) -> anyhow::Result<StreamedMarketSummary>
where
    F: for<'a> FnMut(
        &str,
        NaiveDate,
        NaiveDate,
        StreamOrder,
        &'a mut dyn FnMut(MarketRow) -> anyhow::Result<()>,
    ) -> anyhow::Result<BTreeMap<String, DbDataGap>>,
    V: FnMut(Vec<MarketRow>) -> anyhow::Result<()>,
{
    let mut current_code: Option<String> = None;
    let mut previous_date = None;
    let mut rows_for_symbol = Vec::new();
    let mut row_count = 0;
    let mut symbol_count = 0;
    let mut trade_dates = BTreeSet::new();
    let mut visit = visit;
    let db_data_gaps = loader(
        duckdb_path,
        start_date,
        end_date,
        StreamOrder::SymbolAndDate,
        &mut |row| {
            if let Some(code) = current_code.as_deref() {
                match row.ts_code.as_str().cmp(code) {
                    std::cmp::Ordering::Less => {
                        anyhow::bail!("streamed market rows are not ordered by ts_code");
                    }
                    std::cmp::Ordering::Greater => {
                        visit(std::mem::take(&mut rows_for_symbol))?;
                        symbol_count += 1;
                        current_code = Some(row.ts_code.clone());
                        previous_date = None;
                    }
                    std::cmp::Ordering::Equal => {}
                }
            } else {
                current_code = Some(row.ts_code.clone());
            }
            if previous_date.is_some_and(|date| row.trade_date < date) {
                anyhow::bail!("streamed market rows are not ordered by trade_date");
            }
            previous_date = Some(row.trade_date);
            trade_dates.insert(row.trade_date);
            row_count += 1;
            rows_for_symbol.push(row);
            Ok(())
        },
    )?;
    if !rows_for_symbol.is_empty() {
        visit(rows_for_symbol)?;
        symbol_count += 1;
    }
    Ok(StreamedMarketSummary {
        row_count,
        symbol_count,
        trade_dates,
        db_data_gaps,
    })
}

fn ensure_streamed_db_native_window(
    summary: &StreamedMarketSummary,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<()> {
    if summary.row_count == 0 {
        anyhow::bail!("No market rows found between {start_date} and {end_date}.");
    }
    let actual_start = summary.trade_dates.first().copied();
    let actual_end = summary.trade_dates.last().copied();
    if actual_start.is_some_and(|actual_start| actual_start >= start_date)
        && actual_end == Some(end_date)
        && u32::try_from(summary.trade_dates.len())
            .is_ok_and(|len| len >= MIN_DB_NATIVE_WINDOW_TRADING_DAYS)
    {
        Ok(())
    } else {
        anyhow::bail!(
            "DB-native joined prepared window has {} trading dates over {:?}..{:?}; expected requested prepared window {}..{}.",
            summary.trade_dates.len(),
            actual_start,
            actual_end,
            start_date,
            end_date
        );
    }
}

fn scm_turnover_top_pool_codes(mut ranked: Vec<(f64, String)>, top_m: usize) -> BTreeSet<String> {
    ranked.sort_by(|left, right| right.0.total_cmp(&left.0).then(left.1.cmp(&right.1)));
    ranked
        .into_iter()
        .take(top_m)
        .map(|(_, code)| code)
        .collect()
}

fn format_stage_line(stage: &str, elapsed: std::time::Duration) -> String {
    format!(
        "[screen] stage={stage} elapsed={:.3}s",
        elapsed.as_secs_f64()
    )
}

fn timed_stage<T>(stage: &str, run: impl FnOnce() -> anyhow::Result<T>) -> anyhow::Result<T> {
    let started = Instant::now();
    let output = run();
    eprintln!("{}", format_stage_line(stage, started.elapsed()));
    output
}

fn run_screen_with_loaders<F, D>(
    request: ScreenRequest,
    loader: F,
    db_native_source: bool,
) -> anyhow::Result<PathBuf>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<D>,
    D: IntoMarketDataset,
{
    let (start_date, end_date) = screen_window(request.pick_date);
    let prepared = if request.recompute {
        load_and_prepare(&request, start_date, end_date, loader, db_native_source)?
    } else {
        match timed_stage("load_cache", || {
            load_prepared_dataset(
                &request.runtime_root,
                request.method,
                request.pick_date,
                start_date,
                end_date,
            )
        })? {
            Some(dataset) => dataset,
            None => load_and_prepare(&request, start_date, end_date, loader, db_native_source)?,
        }
    };
    if !prepared
        .rows
        .iter()
        .any(|row| row.trade_date == request.pick_date)
    {
        anyhow::bail!(missing_pick_date_rows_message(
            request.pick_date,
            &prepared.rows,
            &request.runtime_root,
            request.method,
        ));
    }

    let (pool_codes, resolved_pool_file) = timed_stage("pool", || {
        Ok(match request.pool_source {
            PoolSource::TurnoverTop => (
                filter_turnover_top_pool_codes(
                    &prepared.rows,
                    request.method,
                    request.pick_date,
                    5000,
                ),
                None,
            ),
            PoolSource::Custom => {
                let resolved = resolve_custom_pool(&request)?;
                (
                    filter_custom_pool_codes(&prepared.rows, request.pick_date, &resolved.codes)?,
                    Some(resolved.path),
                )
            }
        })
    })?;
    let pool = pool_refs(&prepared.rows, &pool_codes);
    let strategy_output = timed_stage("strategy", || {
        run_screen_strategy(request.method, &pool, request.pick_date)
    })?;
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
    let output_path = timed_stage("write_candidates", || {
        write_screen_result(&request.runtime_root, &result)
    })?;
    if request.export_factors {
        timed_stage("export_factors", || {
            let prepared_refs = prepared.rows.iter().collect::<Vec<_>>();
            write_screen_factor_artifact(
                &request,
                &result.candidates,
                &prepared_refs,
                &output_path,
                false,
                &prepared.db_data_gaps,
            )
        })?;
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
        |_duckdb_path, pick_date| Ok(pick_date - Duration::days(1)),
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
    let previous_trade_date = previous_trade_date_loader(&request.duckdb_path, request.pick_date)?;
    let start_date = prepared_cache_start_date(previous_trade_date);
    let snapshot = fetch_rt_k_snapshot(provider, request.pick_date, fallback_trade_time)?;
    let history = history_loader(&request.duckdb_path, start_date, previous_trade_date)?;
    if history.is_empty() {
        anyhow::bail!("No market rows found between {start_date} and {previous_trade_date}.");
    }
    let market_rows = build_intraday_market_rows(history, &snapshot, request.pick_date);
    let prepared = prepare_rows(market_rows)?;
    write_intraday_screen_output(request, fallback_trade_time, start_date, prepared)
}

pub fn run_db_native_intraday_screen_with_loaders<P, Prev, F, D, S>(
    request: ScreenRequest,
    provider: &P,
    fallback_trade_time: &str,
    previous_trade_date_loader: Prev,
    history_loader: F,
    macd_state_loader: S,
) -> anyhow::Result<PathBuf>
where
    P: IntradaySnapshotProvider,
    Prev: FnOnce(&str, NaiveDate) -> anyhow::Result<NaiveDate>,
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<D>,
    D: IntoMarketDataset,
    S: FnOnce(&str, &[String], NaiveDate) -> anyhow::Result<Vec<MacdPeriodState>>,
{
    let previous_trade_date = previous_trade_date_loader(&request.duckdb_path, request.pick_date)?;
    let start_date = prepared_cache_start_date(previous_trade_date);
    let snapshot = fetch_rt_k_snapshot(provider, request.pick_date, fallback_trade_time)?;
    let history_dataset = history_loader(&request.duckdb_path, start_date, previous_trade_date)?
        .into_market_dataset();
    if history_dataset.rows.is_empty() {
        anyhow::bail!("No market rows found between {start_date} and {previous_trade_date}.");
    }
    let period_state_unavailable =
        db_table_unavailable(&history_dataset.db_data_gaps, "calc_indicator_state");
    let history = history_dataset.rows;
    let universe = db_native_intraday_history_universe(&history, previous_trade_date);
    let supported_snapshot = snapshot
        .iter()
        .filter(|row| universe.contains(row.ts_code.as_str()))
        .cloned()
        .collect::<Vec<_>>();
    let skipped_non_universe = snapshot.len().saturating_sub(supported_snapshot.len());
    let symbols = supported_snapshot
        .iter()
        .map(|row| row.ts_code.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    let (macd_states, covered_symbols) = if period_state_unavailable {
        (
            Vec::new(),
            symbols.iter().map(String::as_str).collect::<BTreeSet<_>>(),
        )
    } else {
        let states = macd_state_loader(&request.duckdb_path, &symbols, request.pick_date)?;
        let covered = intraday_macd_covered_symbols(&symbols, &states);
        (states, covered)
    };
    let skipped_missing_macd_state = supported_snapshot
        .iter()
        .filter(|row| !covered_symbols.contains(row.ts_code.as_str()))
        .count();
    let macd_covered_snapshot = supported_snapshot
        .into_iter()
        .filter(|row| covered_symbols.contains(row.ts_code.as_str()))
        .collect::<Vec<_>>();
    let qfq_symbols = intraday_live_qfq_price_symbols(&history, request.pick_date);
    let skipped_missing_live_qfq_price = macd_covered_snapshot
        .iter()
        .filter(|row| !qfq_symbols.contains(row.ts_code.as_str()))
        .count();
    let live_macd_snapshot = macd_covered_snapshot
        .into_iter()
        .filter(|row| qfq_symbols.contains(row.ts_code.as_str()))
        .collect::<Vec<_>>();
    let market_rows = build_intraday_market_rows_with_macd_states(
        history,
        &live_macd_snapshot,
        request.pick_date,
        &macd_states,
    );
    let prepared = PreparedDataset {
        rows: prepare_rows(market_rows)?,
        db_data_gaps: history_dataset.db_data_gaps,
    };
    write_intraday_screen_output_with_extra_stats(
        request,
        fallback_trade_time,
        start_date,
        prepared,
        BTreeMap::from([
            (
                "intraday_snapshot_skipped_non_universe".to_string(),
                skipped_non_universe,
            ),
            (
                "intraday_snapshot_skipped_missing_macd_state".to_string(),
                skipped_missing_macd_state,
            ),
            (
                "intraday_snapshot_skipped_missing_live_qfq_price".to_string(),
                skipped_missing_live_qfq_price,
            ),
        ]),
    )
}

fn db_native_intraday_history_universe(
    history: &[MarketRow],
    previous_trade_date: NaiveDate,
) -> BTreeSet<&str> {
    let previous_day = history
        .iter()
        .filter(|row| row.trade_date == previous_trade_date)
        .map(|row| row.ts_code.as_str())
        .collect::<BTreeSet<_>>();
    if previous_day.is_empty() {
        history
            .iter()
            .map(|row| row.ts_code.as_str())
            .collect::<BTreeSet<_>>()
    } else {
        previous_day
    }
}

fn intraday_macd_covered_symbols<'a>(
    symbols: &'a [String],
    states: &[MacdPeriodState],
) -> BTreeSet<&'a str> {
    const REQUIRED_PERIODS: [&str; 3] = ["daily", "weekly", "monthly"];
    symbols
        .iter()
        .filter_map(|symbol| {
            let covered = REQUIRED_PERIODS.iter().all(|period_type| {
                states.iter().any(|state| {
                    state.ts_code == *symbol
                        && state.period_type == *period_type
                        && state.ema12.is_finite()
                        && state.ema26.is_finite()
                        && state.dea.is_finite()
                })
            });
            covered.then_some(symbol.as_str())
        })
        .collect()
}

fn intraday_live_qfq_price_symbols(history: &[MarketRow], trade_date: NaiveDate) -> BTreeSet<&str> {
    history
        .iter()
        .filter(|row| row.trade_date <= trade_date)
        .filter(|row| {
            row.adj_factor
                .is_some_and(|value| value.is_finite() && value > 0.0)
        })
        .map(|row| row.ts_code.as_str())
        .collect()
}

fn write_intraday_screen_output(
    request: ScreenRequest,
    fallback_trade_time: &str,
    start_date: NaiveDate,
    prepared: Vec<PreparedRow>,
) -> anyhow::Result<PathBuf> {
    write_intraday_screen_output_with_extra_stats(
        request,
        fallback_trade_time,
        start_date,
        PreparedDataset::complete(prepared),
        BTreeMap::new(),
    )
}

fn write_intraday_screen_output_with_extra_stats(
    request: ScreenRequest,
    fallback_trade_time: &str,
    start_date: NaiveDate,
    prepared: PreparedDataset,
    extra_stats: BTreeMap<String, usize>,
) -> anyhow::Result<PathBuf> {
    let metadata_start_date = prepared
        .rows
        .iter()
        .map(|row| row.trade_date)
        .min()
        .unwrap_or(start_date);
    write_prepared_dataset_for_mode(
        &request.runtime_root,
        request.method,
        request.pick_date,
        metadata_start_date,
        request.pick_date,
        true,
        &prepared,
    )?;
    let (pool_codes, resolved_pool_file) = match request.pool_source {
        PoolSource::TurnoverTop => (
            filter_turnover_top_pool_codes(&prepared.rows, request.method, request.pick_date, 5000),
            None,
        ),
        PoolSource::Custom => {
            let resolved = resolve_custom_pool(&request)?;
            (
                filter_custom_pool_codes(&prepared.rows, request.pick_date, &resolved.codes)?,
                Some(resolved.path),
            )
        }
    };
    let pool = pool_refs(&prepared.rows, &pool_codes);
    let strategy_output = run_screen_strategy(request.method, &pool, request.pick_date)?;
    let mut stats = strategy_output.stats;
    stats.extend(extra_stats);
    let count = stats.get("selected").copied().unwrap_or(0);
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
        stats,
    };
    let output_path =
        intraday_candidate_output_path(&request.runtime_root, request.pick_date, request.method);
    if let Some(parent) = output_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&output_path, serde_json::to_vec_pretty(&result)?)?;
    if request.export_factors {
        let prepared_refs = prepared.rows.iter().collect::<Vec<_>>();
        write_screen_factor_artifact(
            &request,
            &result.candidates,
            &prepared_refs,
            &output_path,
            true,
            &prepared.db_data_gaps,
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
        message.push_str(" Intraday artifacts exist for this date; use --intraday for intraday selection, or refresh the DB-native stock-cache daily prepared cache after stock-cache coverage is available.");
    } else {
        message.push_str(" Refresh the DB-native stock-cache daily prepared cache after stock-cache coverage is available.");
    }
    message
}

fn missing_pick_date_rows_error(
    pick_date: NaiveDate,
    earliest: Option<NaiveDate>,
    latest: Option<NaiveDate>,
    runtime_root: &Path,
    method: Method,
) -> anyhow::Error {
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
        message.push_str(" Intraday artifacts exist for this date; use --intraday for intraday selection, or refresh the DB-native stock-cache daily prepared cache after stock-cache coverage is available.");
    } else {
        message.push_str(" Refresh the DB-native stock-cache daily prepared cache after stock-cache coverage is available.");
    }
    anyhow::anyhow!(message)
}

fn write_screen_factor_artifact(
    request: &ScreenRequest,
    candidates: &[crate::model::Candidate],
    prepared_rows: &[&PreparedRow],
    candidate_artifact: &Path,
    intraday: bool,
    db_data_gaps: &BTreeMap<String, DbDataGap>,
) -> anyhow::Result<PathBuf> {
    let artifact_key = screen_artifact_key(request.pick_date, intraday);
    let environment_state = match request.environment_state.as_deref() {
        Some(state) => Some(normalize_environment_state(state)?),
        None => prepared_market_state(prepared_rows.iter().copied(), request.pick_date),
    };
    let rows = build_candidate_factor_rows_from_refs(
        candidates,
        prepared_rows,
        request.method,
        environment_state.as_deref(),
    );
    write_factor_artifact_with_db_data_gaps(
        &request.runtime_root,
        request.method,
        &artifact_key,
        &rows,
        Some(candidate_artifact),
        db_data_gaps,
    )
}

fn screen_artifact_key(pick_date: NaiveDate, intraday: bool) -> String {
    if intraday {
        format!("{}.intraday", pick_date.format("%Y-%m-%d"))
    } else {
        pick_date.format("%Y-%m-%d").to_string()
    }
}

fn run_screen_strategy(
    method: Method,
    rows: &[&PreparedRow],
    pick_date: NaiveDate,
) -> anyhow::Result<StrategyOutput> {
    match method {
        Method::B2 => Ok(run_b2_strategy_from_refs(rows, pick_date)),
        Method::Scm => Ok(run_scm_strategy_from_refs(rows, pick_date)),
        Method::Pbm => Ok(run_pbm_strategy_from_refs(rows, pick_date)),
    }
}

#[cfg(test)]
mod tests {
    use super::{format_stage_line, front_adjust_rows};
    use crate::model::MarketRow;
    use chrono::NaiveDate;
    use std::collections::BTreeMap;

    #[test]
    fn qfq_source_bars_are_not_adjusted_twice() {
        let day1 = NaiveDate::from_ymd_opt(2026, 1, 2).unwrap();
        let day2 = NaiveDate::from_ymd_opt(2026, 1, 5).unwrap();
        let mut rows = vec![
            MarketRow {
                ts_code: "000001.SZ".to_string(),
                trade_date: day1,
                open: 9.0,
                high: 11.0,
                low: 8.0,
                close: 10.0,
                vol: 100.0,
                turnover_rate: None,
                adj_factor: Some(1.0),
                db_factors: BTreeMap::from([
                    ("_source_price_basis_qfq".to_string(), 1.0),
                    ("rolling_ma25_qfq".to_string(), 8.0),
                ]),
            },
            MarketRow {
                ts_code: "000001.SZ".to_string(),
                trade_date: day2,
                open: 19.0,
                high: 21.0,
                low: 18.0,
                close: 20.0,
                vol: 100.0,
                turnover_rate: None,
                adj_factor: Some(2.0),
                db_factors: BTreeMap::from([("_source_price_basis_qfq".to_string(), 1.0)]),
            },
        ];

        front_adjust_rows(&mut rows).unwrap();

        assert_eq!(rows[0].close, 10.0);
        assert_eq!(rows[0].db_factors["rolling_ma25_qfq"], 8.0);
        assert!(!rows[0].db_factors.contains_key("_source_price_basis_qfq"));
    }

    #[test]
    fn stage_timing_line_reports_seconds_with_three_decimals() {
        assert_eq!(
            format_stage_line("prepare", std::time::Duration::from_millis(1500)),
            "[screen] stage=prepare elapsed=1.500s"
        );
    }
}

/// Builds the EOD prepared window for `pick_date` in memory, without writing any cache.
/// Returns `None` when the window is empty or does not satisfy the DB-native window contract,
/// mirroring what a missing or unusable prepared cache would report.
pub fn load_db_native_prepared_window_with_loader<F, D>(
    duckdb_path: &str,
    pick_date: NaiveDate,
    loader: F,
) -> anyhow::Result<Option<PreparedDataset>>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<D>,
    D: IntoMarketDataset,
{
    let (start_date, end_date) = screen_window(pick_date);
    let market_dataset = loader(duckdb_path, start_date, end_date)?.into_market_dataset();
    if market_dataset.rows.is_empty() {
        return Ok(None);
    }
    let prepared = PreparedDataset {
        rows: prepare_rows(market_dataset.rows)?,
        db_data_gaps: market_dataset.db_data_gaps,
    };
    if ensure_db_native_prepared_window(&prepared.rows, start_date, end_date).is_err() {
        return Ok(None);
    }
    Ok(Some(prepared))
}

pub fn load_db_native_prepared_window(
    duckdb_path: &str,
    pick_date: NaiveDate,
) -> anyhow::Result<Option<PreparedDataset>> {
    load_db_native_prepared_window_with_loader(
        duckdb_path,
        pick_date,
        crate::db::fetch_db_native_daily_dataset,
    )
}

fn load_and_prepare<F, D>(
    request: &ScreenRequest,
    start_date: NaiveDate,
    end_date: NaiveDate,
    loader: F,
    db_native_source: bool,
) -> anyhow::Result<PreparedDataset>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<D>,
    D: IntoMarketDataset,
{
    let market_dataset = timed_stage("load_db", || {
        Ok(loader(&request.duckdb_path, start_date, end_date)?.into_market_dataset())
    })?;
    if market_dataset.rows.is_empty() {
        anyhow::bail!("No market rows found between {start_date} and {end_date}.");
    }
    let prepared = PreparedDataset {
        rows: timed_stage("prepare_rows", || prepare_rows(market_dataset.rows))?,
        db_data_gaps: market_dataset.db_data_gaps,
    };
    if db_native_source {
        ensure_db_native_prepared_window(&prepared.rows, start_date, end_date)?;
    }
    if !prepared.rows.iter().any(|row| row.trade_date == end_date) {
        return Ok(prepared);
    }
    if !request.write_prepared_cache {
        eprintln!(
            "[screen] prepared cache write skipped rows={}",
            prepared.rows.len()
        );
        return Ok(prepared);
    }
    let write_cache_started = Instant::now();
    if db_native_source {
        write_db_native_prepared_dataset(
            &request.runtime_root,
            request.method,
            request.pick_date,
            start_date,
            end_date,
            0,
            &prepared,
        )?;
    } else {
        write_prepared_cache(
            &request.runtime_root,
            request.method,
            request.pick_date,
            start_date,
            end_date,
            &prepared.rows,
        )?;
    }
    eprintln!(
        "[screen] prepared cache wrote rows={} elapsed={:.3}s",
        prepared.rows.len(),
        write_cache_started.elapsed().as_secs_f64()
    );
    Ok(prepared)
}

fn ensure_db_native_prepared_window(
    prepared: &[PreparedRow],
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<()> {
    let trade_dates = prepared
        .iter()
        .map(|row| row.trade_date)
        .collect::<BTreeSet<_>>();
    if trade_dates
        .first()
        .copied()
        .is_some_and(|actual_start| actual_start >= start_date)
        && trade_dates.last().copied() == Some(end_date)
        && u32::try_from(trade_dates.len())
            .is_ok_and(|len| len >= MIN_DB_NATIVE_WINDOW_TRADING_DAYS)
    {
        Ok(())
    } else {
        anyhow::bail!(
            "DB-native joined prepared window has {} trading dates over {:?}..{:?}; expected requested prepared window {}..{}.",
            trade_dates.len(),
            trade_dates.first(),
            trade_dates.last(),
            start_date,
            end_date
        );
    }
}

fn db_table_unavailable(db_data_gaps: &BTreeMap<String, DbDataGap>, table: &str) -> bool {
    db_data_gaps.get(table).is_some_and(|gap| {
        matches!(
            gap.reason,
            DbDataGapReason::MissingTable | DbDataGapReason::SchemaMismatch
        )
    })
}

fn prepare_rows(mut rows: Vec<MarketRow>) -> anyhow::Result<Vec<PreparedRow>> {
    rows.sort_unstable_by(|left, right| {
        left.ts_code
            .cmp(&right.ts_code)
            .then(left.trade_date.cmp(&right.trade_date))
    });
    let mut prepared = Vec::with_capacity(rows.len());
    let mut remaining = rows.into_iter().peekable();
    while let Some(first_row) = remaining.next() {
        let mut rows = vec![first_row];
        while remaining
            .peek()
            .is_some_and(|row| row.ts_code == rows[0].ts_code)
        {
            rows.push(remaining.next().expect("peeked market row"));
        }
        prepared.extend(prepare_symbol_rows(rows)?);
    }
    Ok(prepared)
}

fn prepare_market_rows_for_symbol(rows: &mut [MarketRow]) -> anyhow::Result<Vec<f64>> {
    let turnover_daily = rows
        .iter()
        .map(|row| ((row.open + row.close) / 2.0) * row.vol)
        .collect::<Vec<_>>();
    front_adjust_rows(rows)?;
    enrich_local_market_factors(rows);
    for (row, amount) in rows.iter_mut().zip(&turnover_daily) {
        if amount.is_finite() {
            row.db_factors
                .insert(RAW_MARKET_AMOUNT_FACTOR.to_string(), *amount);
        }
    }
    Ok(turnover_daily)
}

fn prepare_symbol_rows(mut rows: Vec<MarketRow>) -> anyhow::Result<Vec<PreparedRow>> {
    let turnover_daily = prepare_market_rows_for_symbol(&mut rows)?;
    let high = rows.iter().map(|row| row.high).collect::<Vec<_>>();
    let low = rows.iter().map(|row| row.low).collect::<Vec<_>>();
    let close = rows.iter().map(|row| row.close).collect::<Vec<_>>();
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
    Ok(rows
        .into_iter()
        .enumerate()
        .map(|(idx, row)| PreparedRow {
            ts_code: row.ts_code,
            trade_date: row.trade_date,
            open: row.open,
            high: row.high,
            low: row.low,
            close: row.close,
            volume: row.vol,
            turnover_n: turnover_n[idx],
            turnover_rate: row.turnover_rate,
            k: db_factor_or(&row.db_factors, "kdj_k_qfq", k[idx]),
            d: db_factor_or(&row.db_factors, "kdj_d_qfq", d[idx]),
            j: db_factor_or(&row.db_factors, "kdj_j_qfq", j[idx]),
            zxdq: Some(zxdq[idx]),
            zxdkx: zxdkx[idx],
            dif: db_factor_or(&row.db_factors, "macd_daily_dif", dif[idx]),
            dea: db_factor_or(&row.db_factors, "macd_daily_dea", dea[idx]),
            macd_hist: db_factor_or(&row.db_factors, "macd_daily_hist", macd_hist[idx]),
            ma25: db_factor_option_or(&row.db_factors, "rolling_ma25_qfq", ma25[idx]),
            ma60: ma60[idx],
            ma144: db_factor_option_or(&row.db_factors, "rolling_ma144_qfq", ma144[idx]),
            chg_d: (idx > 0).then(|| (row.close - close[idx - 1]) / close[idx - 1] * 100.0),
            weekly_ma_bull: false,
            max_vol_not_bearish: true,
            v_shrink: false,
            safe_mode: true,
            lt_filter: true,
            db_factors: row.db_factors,
        })
        .collect())
}

fn db_factor_or(factors: &BTreeMap<String, f64>, key: &str, fallback: f64) -> f64 {
    factors
        .get(key)
        .copied()
        .filter(|value| value.is_finite())
        .unwrap_or(fallback)
}

fn db_factor_option_or(
    factors: &BTreeMap<String, f64>,
    key: &str,
    fallback: Option<f64>,
) -> Option<f64> {
    factors
        .get(key)
        .copied()
        .filter(|value| value.is_finite())
        .or(fallback)
}

fn front_adjust_rows(rows: &mut [MarketRow]) -> anyhow::Result<()> {
    if rows
        .iter()
        .any(|row| row.db_factors.contains_key("_source_price_basis_qfq"))
    {
        for row in rows {
            row.db_factors.remove("_source_price_basis_qfq");
        }
        return Ok(());
    }
    let has_qfq_reference = rows
        .iter()
        .any(|row| row.db_factors.contains_key("_source_close_qfq"));
    let latest_factor = if has_qfq_reference {
        rows.last().and_then(|row| valid_adj_factor(row.adj_factor))
    } else {
        rows.iter()
            .rev()
            .find_map(|row| valid_adj_factor(row.adj_factor))
    };
    let qfq_multiplier = if has_qfq_reference {
        let multiplier = rows.iter().rev().find_map(|row| {
            let reference = valid_adj_factor(row.db_factors.get("_source_close_qfq").copied())?;
            let close = valid_adj_factor(Some(row.close))?;
            let adjustment = if Some(row.trade_date) == rows.last().map(|last| last.trade_date) {
                1.0
            } else {
                valid_adj_factor(row.adj_factor)? / latest_factor?
            };
            valid_adj_factor(Some(close / reference * adjustment))
        });
        Some(multiplier.ok_or_else(|| anyhow::anyhow!(
            "Cannot align DB qfq price basis for {}: no usable close_qfq reference in the window.",
            rows[0].ts_code,
        ))?)
    } else {
        None
    };
    for row in rows {
        let reference = row.db_factors.remove("_source_close_qfq");
        let multiplier = match (valid_adj_factor(row.adj_factor), latest_factor) {
            (Some(adj_factor), Some(latest_factor)) => adj_factor / latest_factor,
            _ => match (
                valid_adj_factor(reference),
                qfq_multiplier,
                valid_adj_factor(Some(row.close)),
            ) {
                (Some(reference), Some(qfq_multiplier), Some(close)) => {
                    reference * qfq_multiplier / close
                }
                _ if qfq_multiplier.is_some() && row.close.is_finite() && row.close > 0.0 => {
                    anyhow::bail!(
                        "Cannot align DB qfq price basis for {} on {}: missing adj_factor and close_qfq.",
                        row.ts_code,
                        row.trade_date
                    );
                }
                _ => 1.0,
            },
        };
        row.open = adjust_price(row.open, multiplier);
        row.high = adjust_price(row.high, multiplier);
        row.low = adjust_price(row.low, multiplier);
        row.close = adjust_price(row.close, multiplier);
        if let Some(chip_vwap) = row.db_factors.get_mut("chip_vwap") {
            *chip_vwap = adjust_price(*chip_vwap, multiplier);
        }
        if let Some(qfq_multiplier) = qfq_multiplier {
            let has_live_macd = row.db_factors.contains_key("intraday_price_live_qfq");
            for (key, value) in &mut row.db_factors {
                if is_db_qfq_price_factor(key) && !(has_live_macd && key.starts_with("macd_")) {
                    *value = adjust_price(*value, qfq_multiplier);
                }
            }
        }
    }
    Ok(())
}

fn is_db_qfq_price_factor(key: &str) -> bool {
    matches!(
        key,
        "_czsc_last_bi_high"
            | "_czsc_last_bi_low"
            | "_czsc_last_bi_mid"
            | "_czsc_latest_zs_zg"
            | "_czsc_latest_zs_zd"
            | "_czsc_latest_zs_zz"
            | "_czsc_recent_peak_high"
            | "_czsc_post_peak_first_bear_open"
            | "_czsc_post_peak_first_bear_high"
            | "_czsc_post_peak_first_bear_low"
            | "_czsc_post_peak_first_bear_close"
            | "boll_upper_qfq"
            | "boll_mid_qfq"
            | "boll_lower_qfq"
            | "mtm_qfq"
            | "tushare_macd_dif_qfq"
            | "tushare_macd_dea_qfq"
            | "tushare_macd_qfq"
            | "macd_daily_dif"
            | "macd_daily_dea"
            | "macd_daily_hist"
            | "macd_weekly_dif"
            | "macd_weekly_dea"
            | "macd_weekly_hist"
            | "macd_monthly_dif"
            | "macd_monthly_dea"
            | "macd_monthly_hist"
            | "rolling_ma25_qfq"
            | "rolling_ma144_qfq"
            | "rolling_ma220_qfq"
            | "rolling_high_20_qfq"
            | "rolling_high_90_qfq"
            | "rolling_low_90_qfq"
            | "rolling_high_120_qfq"
            | "rolling_low_120_qfq"
    )
}

fn valid_adj_factor(value: Option<f64>) -> Option<f64> {
    value.filter(|value| value.is_finite() && *value > 0.0)
}

fn adjust_price(value: f64, multiplier: f64) -> f64 {
    if value.is_finite() {
        value * multiplier
    } else {
        value
    }
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
        Method::B2 => row
            .ma25
            .zip(row.ma60)
            .is_some_and(|(ma25, ma60)| ma25 > ma60),
        Method::Scm | Method::Pbm => true,
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
