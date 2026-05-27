use std::collections::BTreeMap;
use std::path::PathBuf;
use std::str::FromStr;
use std::time::Instant;

use anyhow::Context;
use chrono::{Duration, NaiveDate};
use clap::{Parser, Subcommand};
use serde_json::Value;

use crate::cache::{load_prepared_cache, write_prepared_cache};
use crate::config::{default_runtime_root, resolve_dsn_from_env, screen_window};
use crate::market_environment::{
    EnvironmentEvaluation, ensure_market_environment, evaluate_market_environment,
};
use crate::model::{MarketRow, Method, PreparedRow};
use crate::native_chart::{NativeChartArgs, run_native_chart};
use crate::native_review::{
    NativeReviewArgs, NativeReviewMergeArgs, run_native_review, run_native_review_merge,
};
use crate::output::{build_screen_result_with_pool, write_screen_result};
use crate::prepare::prepare_rows;
use crate::strategies::run_strategy;

#[derive(Debug, Parser)]
#[command(name = "stock-select-rs")]
#[command(about = "Rust acceleration path for stock-select screening")]
pub struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    Screen(ScreenArgs),
    Chart(ChartArgs),
    Review(ReviewArgs),
    ReviewMerge(ReviewMergeArgs),
    ReviewList(ReviewListArgs),
    Run(RunArgs),
}

#[derive(Debug, Parser)]
pub struct ScreenArgs {
    #[arg(long)]
    method: Method,
    #[arg(long)]
    pick_date: NaiveDate,
    #[arg(long)]
    dsn: Option<String>,
    #[arg(long)]
    runtime_root: Option<PathBuf>,
    #[arg(long)]
    recompute: bool,
    #[arg(long, default_value = "turnover-top")]
    pool_source: PoolSource,
    #[arg(long)]
    pool_file: Option<PathBuf>,
}

#[derive(Debug, Parser)]
pub struct ChartArgs {
    #[arg(long)]
    method: Method,
    #[arg(long)]
    pick_date: NaiveDate,
    #[arg(long)]
    dsn: Option<String>,
    #[arg(long)]
    runtime_root: Option<PathBuf>,
}

#[derive(Debug, Parser)]
pub struct ReviewArgs {
    #[arg(long)]
    method: Method,
    #[arg(long)]
    pick_date: NaiveDate,
    #[arg(long)]
    dsn: Option<String>,
    #[arg(long)]
    runtime_root: Option<PathBuf>,
    #[arg(long)]
    environment_state: Option<String>,
    #[arg(long)]
    environment_reason: Option<String>,
    #[arg(long)]
    llm_min_baseline_score: Option<f64>,
    #[arg(long)]
    llm_review_limit: Option<usize>,
}

#[derive(Debug, Parser)]
pub struct ReviewMergeArgs {
    #[arg(long)]
    method: Method,
    #[arg(long)]
    pick_date: NaiveDate,
    #[arg(long)]
    runtime_root: Option<PathBuf>,
    #[arg(long, value_delimiter = ',')]
    codes: Option<Vec<String>>,
}

#[derive(Debug, Parser)]
pub struct ReviewListArgs {
    #[arg(long)]
    pub method: Method,
    #[arg(long)]
    pub pick_date: NaiveDate,
    #[arg(long)]
    pub runtime_root: Option<PathBuf>,
    #[arg(long)]
    pub dsn: Option<String>,
    #[arg(long)]
    pub verdict: String,
}

#[derive(Debug, Parser)]
pub struct RunArgs {
    #[command(flatten)]
    review: ReviewArgs,
    #[arg(long)]
    recompute: bool,
    #[arg(long, default_value = "turnover-top")]
    pool_source: PoolSource,
    #[arg(long)]
    pool_file: Option<PathBuf>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PoolSource {
    TurnoverTop,
    Custom,
}

impl PoolSource {
    fn as_str(self) -> &'static str {
        match self {
            Self::TurnoverTop => "turnover-top",
            Self::Custom => "custom",
        }
    }
}

impl FromStr for PoolSource {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value.trim().to_ascii_lowercase().as_str() {
            "turnover-top" => Ok(Self::TurnoverTop),
            "custom" => Ok(Self::Custom),
            other => Err(format!(
                "unsupported pool source '{other}', expected turnover-top or custom"
            )),
        }
    }
}

pub fn run() -> anyhow::Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Screen(args) => run_screen(args, |dsn, start, end| {
            crate::db::fetch_daily_window(dsn, start, end)
        })
        .map(|path| {
            eprintln!("[screen] wrote {}", path.display());
        }),
        Commands::Chart(args) => run_chart(args).map(|path| {
            eprintln!("[chart] wrote {}", path.display());
        }),
        Commands::Review(args) => run_review(args).map(|path| {
            eprintln!("[review] wrote {}", path.display());
        }),
        Commands::ReviewMerge(args) => run_review_merge(args).map(|path| {
            eprintln!("[review-merge] wrote {}", path.display());
        }),
        Commands::ReviewList(args) => run_review_list(args, |codes| {
            let dsn = resolve_dsn_from_env(None)?;
            crate::db::fetch_instrument_names(&dsn, codes)
        })
        .map(|output| {
            if !output.is_empty() {
                println!("{output}");
            }
        }),
        Commands::Run(args) => run_hybrid(args),
    }
}

pub fn run_chart(args: ChartArgs) -> anyhow::Result<PathBuf> {
    let started = Instant::now();
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let output_path = run_native_chart(NativeChartArgs {
        method: args.method,
        pick_date: args.pick_date,
        runtime_root,
    })?;
    eprintln!(
        "[chart] total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(output_path)
}

pub fn run_review(args: ReviewArgs) -> anyhow::Result<PathBuf> {
    let started = Instant::now();
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let (environment_state, environment_reason) = resolve_review_environment_args(
        &runtime_root,
        args.pick_date,
        args.dsn.as_deref(),
        args.environment_state,
        args.environment_reason,
    )?;
    let output_path = run_native_review(NativeReviewArgs {
        method: args.method,
        pick_date: args.pick_date,
        runtime_root,
        environment_state,
        environment_reason,
        llm_min_baseline_score: args.llm_min_baseline_score,
        llm_review_limit: args.llm_review_limit,
    })?;
    eprintln!(
        "[review] total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(output_path)
}

pub fn run_review_merge(args: ReviewMergeArgs) -> anyhow::Result<PathBuf> {
    let started = Instant::now();
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let output_path = run_native_review_merge(NativeReviewMergeArgs {
        method: args.method,
        pick_date: args.pick_date,
        runtime_root,
        codes: args.codes,
    })?;
    eprintln!(
        "[review-merge] total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(output_path)
}

pub fn run_review_list<F>(args: ReviewListArgs, name_loader: F) -> anyhow::Result<String>
where
    F: FnOnce(&[String]) -> anyhow::Result<BTreeMap<String, String>>,
{
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let reviews = load_reviews_for_verdict(
        &runtime_root,
        args.pick_date,
        args.method,
        args.verdict.as_str(),
    )?;
    let codes = reviews
        .iter()
        .filter_map(|review| review.get("code").and_then(Value::as_str))
        .map(str::to_string)
        .collect::<Vec<_>>();
    let names = if args.dsn.is_some() {
        let dsn = resolve_dsn_from_env(args.dsn.as_deref())?;
        crate::db::fetch_instrument_names(&dsn, &codes)?
    } else {
        name_loader(&codes).unwrap_or_default()
    };
    Ok(build_review_list_lines(&reviews, &names).join("\n"))
}

fn load_reviews_for_verdict(
    runtime_root: &std::path::Path,
    pick_date: NaiveDate,
    method: Method,
    verdict: &str,
) -> anyhow::Result<Vec<Value>> {
    let normalized = normalize_verdict(verdict)?;
    let summary_path = runtime_root
        .join("reviews")
        .join(format!(
            "{}.{}",
            pick_date.format("%Y-%m-%d"),
            method.as_str()
        ))
        .join("summary.json");
    let summary: Value = serde_json::from_slice(
        &std::fs::read(&summary_path)
            .with_context(|| format!("read review summary {}", summary_path.display()))?,
    )
    .with_context(|| format!("parse review summary {}", summary_path.display()))?;
    let mut reviews = Vec::new();
    for section in ["recommendations", "excluded"] {
        if let Some(items) = summary.get(section).and_then(Value::as_array) {
            for item in items {
                if item
                    .get("verdict")
                    .and_then(Value::as_str)
                    .is_some_and(|value| value.eq_ignore_ascii_case(&normalized))
                {
                    reviews.push(item.clone());
                }
            }
        }
    }
    Ok(reviews)
}

fn normalize_verdict(verdict: &str) -> anyhow::Result<String> {
    let normalized = verdict.trim().to_ascii_uppercase();
    if matches!(normalized.as_str(), "PASS" | "WATCH" | "FAIL") {
        Ok(normalized)
    } else {
        anyhow::bail!("unsupported verdict '{verdict}', expected PASS, WATCH, or FAIL")
    }
}

fn build_review_list_lines(reviews: &[Value], names: &BTreeMap<String, String>) -> Vec<String> {
    reviews
        .iter()
        .filter_map(|review| {
            let code = review.get("code").and_then(Value::as_str)?;
            let name = names.get(code).map(String::as_str).unwrap_or("-");
            let signal = review_signal(review);
            let signal_type = review
                .get("signal_type")
                .and_then(Value::as_str)
                .filter(|value| !value.trim().is_empty())
                .unwrap_or("-");
            Some(format!("{code}\t{name}\t{signal}\t{signal_type}"))
        })
        .collect()
}

fn review_signal(review: &Value) -> &str {
    review
        .get("signal")
        .and_then(Value::as_str)
        .or_else(|| {
            review
                .get("baseline_review")
                .and_then(|baseline| baseline.get("signal"))
                .and_then(Value::as_str)
        })
        .filter(|value| !value.trim().is_empty())
        .unwrap_or("-")
}

pub fn build_review_list_lines_for_test(
    reviews: &[Value],
    names: &BTreeMap<String, String>,
) -> Vec<String> {
    build_review_list_lines(reviews, names)
}

pub fn run_hybrid(args: RunArgs) -> anyhow::Result<()> {
    let started = Instant::now();
    let runtime_root = args
        .review
        .runtime_root
        .clone()
        .unwrap_or_else(default_runtime_root);
    let method = args.review.method;
    let pick_date = args.review.pick_date;
    let (environment_state, environment_reason) = resolve_review_environment_args(
        &runtime_root,
        pick_date,
        args.review.dsn.as_deref(),
        args.review.environment_state.clone(),
        args.review.environment_reason.clone(),
    )?;

    let screen_started = Instant::now();
    let screen_path = run_screen(
        ScreenArgs {
            method,
            pick_date,
            dsn: args.review.dsn.clone(),
            runtime_root: Some(runtime_root.clone()),
            recompute: args.recompute,
            pool_source: args.pool_source,
            pool_file: args.pool_file.clone(),
        },
        |dsn, start, end| crate::db::fetch_daily_window(dsn, start, end),
    )?;
    eprintln!(
        "[run] screen wrote {} elapsed={:.3}s",
        screen_path.display(),
        screen_started.elapsed().as_secs_f64()
    );

    let chart_started = Instant::now();
    run_native_chart(NativeChartArgs {
        method,
        pick_date,
        runtime_root: runtime_root.clone(),
    })?;
    eprintln!(
        "[run] chart elapsed={:.3}s",
        chart_started.elapsed().as_secs_f64()
    );

    let review_started = Instant::now();
    run_native_review(NativeReviewArgs {
        method,
        pick_date,
        runtime_root: runtime_root.clone(),
        environment_state,
        environment_reason,
        llm_min_baseline_score: args.review.llm_min_baseline_score,
        llm_review_limit: args.review.llm_review_limit,
    })?;
    eprintln!(
        "[run] review elapsed={:.3}s",
        review_started.elapsed().as_secs_f64()
    );
    eprintln!(
        "[run] total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(())
}

fn resolve_review_environment_args(
    runtime_root: &std::path::Path,
    pick_date: NaiveDate,
    dsn_arg: Option<&str>,
    manual_state: Option<String>,
    manual_reason: Option<String>,
) -> anyhow::Result<(Option<String>, Option<String>)> {
    resolve_review_environment_args_with_evaluator(
        runtime_root,
        pick_date,
        manual_state,
        manual_reason,
        || {
            let dsn = resolve_dsn_from_env(dsn_arg)?;
            let start_date = pick_date - Duration::days(180);
            let sse = crate::db::fetch_index_history(&dsn, "000001.SH", start_date, pick_date)
                .context("fetch SSE index history for market environment")?;
            let cn2000 = crate::db::fetch_index_history(&dsn, "399303.SZ", start_date, pick_date)
                .context("fetch CN2000 index history for market environment")?;
            evaluate_market_environment(pick_date, &sse, &cn2000)
        },
    )
}

fn resolve_review_environment_args_with_evaluator<F>(
    runtime_root: &std::path::Path,
    pick_date: NaiveDate,
    manual_state: Option<String>,
    manual_reason: Option<String>,
    evaluator: F,
) -> anyhow::Result<(Option<String>, Option<String>)>
where
    F: FnOnce() -> anyhow::Result<EnvironmentEvaluation>,
{
    let resolved = ensure_market_environment(
        runtime_root,
        pick_date,
        manual_state,
        manual_reason,
        evaluator,
    )?;
    eprintln!(
        "[environment] state={} source={} interval={}..{}",
        resolved.state,
        resolved.source,
        resolved
            .interval_start
            .map(|date| date.to_string())
            .unwrap_or_else(|| "-".to_string()),
        resolved
            .interval_end
            .map(|date| date.to_string())
            .unwrap_or_else(|| "-".to_string())
    );
    Ok((Some(resolved.state), resolved.reason))
}

pub fn resolve_review_environment_args_for_test<F>(
    runtime_root: &std::path::Path,
    pick_date: NaiveDate,
    manual_state: Option<String>,
    manual_reason: Option<String>,
    evaluator: F,
) -> anyhow::Result<(Option<String>, Option<String>)>
where
    F: FnOnce() -> anyhow::Result<EnvironmentEvaluation>,
{
    resolve_review_environment_args_with_evaluator(
        runtime_root,
        pick_date,
        manual_state,
        manual_reason,
        evaluator,
    )
}

pub fn run_screen<F>(args: ScreenArgs, loader: F) -> anyhow::Result<PathBuf>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
{
    let started = Instant::now();
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let dsn = resolve_dsn_from_env(args.dsn.as_deref())?;
    let (start_date, end_date) = screen_window(args.pick_date);

    let prepared = if !args.recompute {
        match load_prepared_cache(
            &runtime_root,
            args.method,
            args.pick_date,
            start_date,
            end_date,
        ) {
            Ok(Some(rows)) => {
                eprintln!("[screen] reuse prepared rows={}", rows.len());
                rows
            }
            Ok(None) => load_and_prepare(
                &runtime_root,
                args.method,
                args.pick_date,
                start_date,
                end_date,
                &dsn,
                loader,
            )?,
            Err(err) => {
                eprintln!("[screen] prepared reuse skipped reason={err}");
                load_and_prepare(
                    &runtime_root,
                    args.method,
                    args.pick_date,
                    start_date,
                    end_date,
                    &dsn,
                    loader,
                )?
            }
        }
    } else {
        load_and_prepare(
            &runtime_root,
            args.method,
            args.pick_date,
            start_date,
            end_date,
            &dsn,
            loader,
        )?
    };

    if !prepared.iter().any(|row| row.trade_date == args.pick_date) {
        anyhow::bail!("No prepared rows found for pick_date {}.", args.pick_date);
    }

    let pool_started = Instant::now();
    let pool_selection = filter_pool(
        &prepared,
        args.pick_date,
        args.pool_source,
        args.pool_file.clone(),
        &runtime_root,
    )?;
    eprintln!(
        "[screen] pool_source={} pool_size={} elapsed={:.3}s",
        args.pool_source.as_str(),
        unique_symbol_count(&pool_selection.rows),
        pool_started.elapsed().as_secs_f64()
    );

    let strategy_started = Instant::now();
    let strategy = run_strategy(args.method, &pool_selection.rows, args.pick_date);
    eprintln!(
        "[screen] strategy method={} candidates={} elapsed={:.3}s",
        args.method.as_str(),
        strategy.candidates.len(),
        strategy_started.elapsed().as_secs_f64()
    );
    let result = build_screen_result_with_pool(
        args.method,
        args.pick_date,
        args.pool_source.as_str().to_string(),
        pool_selection
            .pool_file
            .map(|path| path.to_string_lossy().to_string()),
        strategy.candidates,
        strategy.stats,
    );
    let output_path = write_screen_result(&runtime_root, &result)?;
    eprintln!(
        "[screen] total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(output_path)
}

struct PoolSelection {
    rows: Vec<PreparedRow>,
    pool_file: Option<PathBuf>,
}

fn filter_pool(
    prepared: &[PreparedRow],
    pick_date: NaiveDate,
    pool_source: PoolSource,
    pool_file: Option<PathBuf>,
    runtime_root: &std::path::Path,
) -> anyhow::Result<PoolSelection> {
    match pool_source {
        PoolSource::TurnoverTop => Ok(PoolSelection {
            rows: filter_turnover_top_pool(prepared, pick_date, 5000),
            pool_file: None,
        }),
        PoolSource::Custom => {
            let resolved = resolve_custom_pool_codes(pool_file, runtime_root)?;
            Ok(PoolSelection {
                rows: filter_custom_pool_rows(prepared, pick_date, &resolved.codes)?,
                pool_file: Some(resolved.path),
            })
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedCustomPool {
    pub path: PathBuf,
    pub codes: Vec<String>,
}

fn resolve_custom_pool_codes(
    pool_file: Option<PathBuf>,
    runtime_root: &std::path::Path,
) -> anyhow::Result<ResolvedCustomPool> {
    let path = match pool_file {
        Some(path) => expand_home(path),
        None => std::env::var("STOCK_SELECT_POOL_FILE")
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty())
            .map(|value| expand_home(PathBuf::from(value)))
            .unwrap_or_else(|| runtime_root.join("custom-pool.txt")),
    };
    let content = std::fs::read_to_string(&path).with_context(|| {
        format!(
            "Missing custom pool file: {}. Define a custom pool with --pool-file PATH, or set STOCK_SELECT_POOL_FILE, or create {}.",
            path.display(),
            runtime_root.join("custom-pool.txt").display()
        )
    })?;
    let mut codes = Vec::new();
    for token in content.split_whitespace() {
        if let Some(code) = normalize_stock_code_token(token) {
            if !codes.contains(&code) {
                codes.push(code);
            }
        }
    }
    if codes.is_empty() {
        anyhow::bail!(
            "Custom pool must contain at least one stock code. Provide codes separated by whitespace, for example: 603138 300058"
        );
    }
    Ok(ResolvedCustomPool { path, codes })
}

fn filter_custom_pool_rows(
    prepared: &[PreparedRow],
    pick_date: NaiveDate,
    pool_codes: &[String],
) -> anyhow::Result<Vec<PreparedRow>> {
    let available = prepared
        .iter()
        .filter(|row| row.trade_date == pick_date)
        .map(|row| row.ts_code.as_str())
        .collect::<std::collections::BTreeSet<_>>();
    let effective = pool_codes
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

pub fn resolve_custom_pool_codes_for_test(
    pool_file: Option<PathBuf>,
    runtime_root: &std::path::Path,
) -> anyhow::Result<ResolvedCustomPool> {
    resolve_custom_pool_codes(pool_file, runtime_root)
}

pub fn filter_custom_pool_rows_for_test(
    prepared: &[PreparedRow],
    pick_date: NaiveDate,
    pool_source: PoolSource,
    pool_file: Option<PathBuf>,
    runtime_root: &std::path::Path,
) -> anyhow::Result<Vec<PreparedRow>> {
    Ok(filter_pool(prepared, pick_date, pool_source, pool_file, runtime_root)?.rows)
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

fn expand_home(path: PathBuf) -> PathBuf {
    let Some(raw) = path.to_str() else {
        return path;
    };
    if raw == "~" {
        return std::env::var("HOME").map(PathBuf::from).unwrap_or(path);
    }
    if let Some(rest) = raw.strip_prefix("~/") {
        return std::env::var("HOME")
            .map(|home| PathBuf::from(home).join(rest))
            .unwrap_or(path);
    }
    path
}

fn filter_turnover_top_pool(
    prepared: &[PreparedRow],
    pick_date: NaiveDate,
    top_m: usize,
) -> Vec<PreparedRow> {
    if top_m == 0 {
        return Vec::new();
    }
    let mut ranked: Vec<(f64, &str)> = prepared
        .iter()
        .filter(|row| row.trade_date == pick_date)
        .filter(|row| match (row.ma25, row.ma60) {
            (Some(ma25), Some(ma60)) => ma25 > ma60,
            _ => false,
        })
        .map(|row| (row.turnover_n, row.ts_code.as_str()))
        .collect();
    ranked.sort_by(|left, right| {
        right
            .0
            .partial_cmp(&left.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(left.1.cmp(right.1))
    });
    let pool: std::collections::BTreeSet<&str> = ranked
        .into_iter()
        .take(top_m)
        .map(|(_turnover, code)| code)
        .collect();
    prepared
        .iter()
        .filter(|row| pool.contains(row.ts_code.as_str()))
        .cloned()
        .collect()
}

fn unique_symbol_count(rows: &[PreparedRow]) -> usize {
    rows.iter()
        .map(|row| row.ts_code.as_str())
        .collect::<std::collections::BTreeSet<_>>()
        .len()
}

fn load_and_prepare<F>(
    runtime_root: &std::path::Path,
    method: Method,
    pick_date: NaiveDate,
    start_date: NaiveDate,
    end_date: NaiveDate,
    dsn: &str,
    loader: F,
) -> anyhow::Result<Vec<crate::model::PreparedRow>>
where
    F: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
{
    let db_started = Instant::now();
    let market_rows = loader(dsn, start_date, end_date).context("fetch daily_market window")?;
    if market_rows.is_empty() {
        anyhow::bail!("No market rows found between {start_date} and {end_date}.");
    }
    eprintln!(
        "[screen] fetch rows={} elapsed={:.3}s",
        market_rows.len(),
        db_started.elapsed().as_secs_f64()
    );
    let prepare_started = Instant::now();
    let prepared = prepare_rows(&market_rows);
    write_prepared_cache(
        runtime_root,
        method,
        pick_date,
        start_date,
        end_date,
        &prepared,
    )?;
    eprintln!(
        "[screen] prepare rows={} elapsed={:.3}s",
        prepared.len(),
        prepare_started.elapsed().as_secs_f64()
    );
    Ok(prepared)
}

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

    use super::*;

    fn market_row(code: &str, day: u32, close: f64) -> MarketRow {
        MarketRow {
            ts_code: code.to_string(),
            trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
            open: close - 0.8,
            high: close,
            low: close - 1.0,
            close,
            vol: 100.0 + day as f64,
        }
    }

    #[test]
    fn screen_orchestration_writes_candidate_file_from_injected_rows() {
        let temp = tempfile::tempdir().unwrap();
        let pick = NaiveDate::from_ymd_opt(2026, 5, 3).unwrap();
        let args = ScreenArgs {
            method: Method::B2,
            pick_date: pick,
            dsn: Some("postgresql://example".to_string()),
            runtime_root: Some(temp.path().to_path_buf()),
            recompute: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
        };
        let path = run_screen(args, |_dsn, _start, _end| {
            Ok(vec![
                market_row("000001.SZ", 1, 10.0),
                market_row("000001.SZ", 2, 10.1),
                market_row("000001.SZ", 3, 10.6),
            ])
        })
        .unwrap();
        assert_eq!(path, temp.path().join("candidates/2026-05-03.b2.json"));
        assert!(path.exists());
    }

    #[test]
    fn turnover_top_pool_filters_by_pick_date_ma_alignment_and_rank() {
        fn prepared(code: &str, turnover_n: f64, ma25: f64, ma60: f64) -> PreparedRow {
            PreparedRow {
                ts_code: code.to_string(),
                trade_date: NaiveDate::from_ymd_opt(2026, 5, 3).unwrap(),
                open: 1.0,
                high: 1.0,
                low: 1.0,
                close: 1.0,
                volume: 1.0,
                turnover_n,
                k: 50.0,
                d: 50.0,
                j: 50.0,
                zxdq: Some(1.0),
                zxdkx: Some(1.0),
                dif: 0.0,
                dea: 0.0,
                macd_hist: 0.0,
                ma25: Some(ma25),
                ma60: Some(ma60),
                ma144: Some(1.0),
                chg_d: Some(1.0),
                weekly_ma_bull: true,
                max_vol_not_bearish: true,
                v_shrink: true,
                safe_mode: true,
                lt_filter: true,
                yellow_b1: false,
            }
        }
        let rows = vec![
            prepared("000001.SZ", 10.0, 2.0, 1.0),
            prepared("000002.SZ", 30.0, 2.0, 1.0),
            prepared("000003.SZ", 40.0, 1.0, 2.0),
            prepared("000004.SZ", 20.0, 2.0, 1.0),
        ];
        let filtered =
            filter_turnover_top_pool(&rows, NaiveDate::from_ymd_opt(2026, 5, 3).unwrap(), 2);
        let codes = filtered
            .iter()
            .map(|row| row.ts_code.as_str())
            .collect::<std::collections::BTreeSet<_>>();
        assert_eq!(
            codes,
            std::collections::BTreeSet::from(["000002.SZ", "000004.SZ"])
        );
    }
}
