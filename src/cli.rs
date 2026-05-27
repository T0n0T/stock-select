use std::collections::BTreeMap;
use std::io;
use std::path::PathBuf;
use std::str::FromStr;
use std::time::Instant;

use anyhow::Context;
use chrono::{Duration, NaiveDate};
use clap::{CommandFactory, Parser, Subcommand};
use clap_complete::Shell;
use serde_json::Value;

use crate::cache::{
    atomic_write_json, intraday_candidate_output_path, load_prepared_cache,
    write_intraday_prepared_cache, write_prepared_cache,
};
use crate::config::{
    default_runtime_root, resolve_config_value, resolve_dsn_from_env, screen_window,
};
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
use crate::progress::ProgressReporter;
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
    AnalyzeSymbol(AnalyzeSymbolArgs),
    Completions(CompletionsArgs),
}

#[derive(Debug, Parser)]
pub struct CompletionsArgs {
    #[arg(value_parser = clap::value_parser!(Shell))]
    shell: Shell,
}

#[derive(Debug, Parser)]
pub struct ScreenArgs {
    #[arg(long)]
    method: Method,
    #[arg(long)]
    pick_date: Option<NaiveDate>,
    #[arg(long)]
    intraday: bool,
    #[arg(long, env = "TUSHARE_TOKEN", hide_env_values = true)]
    tushare_token: Option<String>,
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
    #[arg(long = "no-progress", default_value_t = true, action = clap::ArgAction::SetFalse)]
    progress: bool,
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
    #[arg(long, default_value_t = 4)]
    chart_workers: usize,
    #[arg(long = "no-progress", default_value_t = true, action = clap::ArgAction::SetFalse)]
    progress: bool,
}

#[derive(Debug, Parser)]
pub struct ReviewArgs {
    #[arg(long)]
    method: Method,
    #[arg(long)]
    pick_date: Option<NaiveDate>,
    #[arg(long)]
    intraday: bool,
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
    pub intraday: bool,
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
    #[arg(long, env = "TUSHARE_TOKEN", hide_env_values = true)]
    tushare_token: Option<String>,
    #[arg(long)]
    recompute: bool,
    #[arg(long, default_value = "turnover-top")]
    pool_source: PoolSource,
    #[arg(long)]
    pool_file: Option<PathBuf>,
    #[arg(long, default_value_t = 4)]
    chart_workers: usize,
    #[arg(long = "no-progress", default_value_t = true, action = clap::ArgAction::SetFalse)]
    progress: bool,
}

#[derive(Debug, Parser, Clone)]
pub struct AnalyzeSymbolArgs {
    #[arg(long)]
    pub method: Method,
    #[arg(long)]
    pub symbol: String,
    #[arg(long)]
    pub pick_date: Option<NaiveDate>,
    #[arg(long)]
    pub dsn: Option<String>,
    #[arg(long)]
    pub runtime_root: Option<PathBuf>,
    #[arg(long)]
    pub environment_state: Option<String>,
    #[arg(long)]
    pub environment_reason: Option<String>,
}

#[derive(Debug, Clone)]
pub struct IntradayScreenArgs {
    pub method: Method,
    pub trade_date: NaiveDate,
    pub run_id: String,
    pub dsn: Option<String>,
    pub runtime_root: Option<PathBuf>,
    pub recompute: bool,
    pub pool_source: PoolSource,
    pub pool_file: Option<PathBuf>,
    pub tushare_token: Option<String>,
    pub progress: bool,
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
        Commands::Screen(args) => run_screen_command(args).map(|path| {
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
        Commands::AnalyzeSymbol(args) => run_analyze_symbol(args).map(|path| {
            println!("{}", path.display());
        }),
        Commands::Completions(args) => {
            write_completion_script(args.shell, &mut io::stdout());
            Ok(())
        }
    }
}

pub fn generate_completion_script(shell: &str) -> anyhow::Result<String> {
    let shell = shell
        .parse::<Shell>()
        .map_err(|_| anyhow::anyhow!("unsupported completion shell: {shell}"))?;
    let mut output = Vec::new();
    write_completion_script(shell, &mut output);
    String::from_utf8(output).context("completion script is not valid UTF-8")
}

fn write_completion_script<W: io::Write>(shell: Shell, writer: &mut W) {
    let mut command = Cli::command();
    clap_complete::generate(shell, &mut command, "stock-select-rs", writer);
}

pub fn run_analyze_symbol(args: AnalyzeSymbolArgs) -> anyhow::Result<PathBuf> {
    run_analyze_symbol_with_loaders(
        args,
        |dsn, symbol, start, end| crate::db::fetch_symbol_history(dsn, symbol, start, end),
        |dsn, symbol| crate::db::fetch_latest_symbol_trade_date(dsn, symbol),
        |code, rows, out_path| crate::native_chart::render_single_chart(code, rows, out_path),
    )
}

pub fn run_analyze_symbol_with_loaders<Load, Latest, Render>(
    args: AnalyzeSymbolArgs,
    history_loader: Load,
    latest_date_loader: Latest,
    chart_renderer: Render,
) -> anyhow::Result<PathBuf>
where
    Load: FnOnce(&str, &str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
    Latest: FnOnce(&str, &str) -> anyhow::Result<NaiveDate>,
    Render: FnOnce(&str, &[PreparedRow], &std::path::Path) -> anyhow::Result<()>,
{
    if !matches!(args.method, Method::B1 | Method::B2) {
        anyhow::bail!("analyze-symbol is currently implemented only for b1 and b2");
    }
    let symbol = normalize_stock_code_token(&args.symbol)
        .ok_or_else(|| anyhow::anyhow!("Unsupported ts_code: {}", args.symbol))?;
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let dsn = resolve_dsn_from_env(args.dsn.as_deref())?;
    let pick_date = match args.pick_date {
        Some(pick_date) => pick_date,
        None => latest_date_loader(&dsn, &symbol)?,
    };
    let start_date = pick_date - Duration::days(366);
    let history = history_loader(&dsn, &symbol, start_date, pick_date)?;
    if history.is_empty() {
        anyhow::bail!("No daily history found for symbol: {symbol}");
    }
    if !history
        .iter()
        .any(|row| row.ts_code == symbol && row.trade_date == pick_date)
    {
        anyhow::bail!("No end-of-day data found for symbol {symbol} on pick_date {pick_date}.");
    }
    let prepared = prepare_rows(&history);
    let prepared_history = prepared
        .iter()
        .filter(|row| row.ts_code == symbol && row.trade_date <= pick_date)
        .cloned()
        .collect::<Vec<_>>();
    if prepared_history.is_empty() {
        anyhow::bail!("Prepared history not found for symbol: {symbol}");
    }
    let strategy = run_strategy(args.method, &prepared_history, pick_date);
    let selected = strategy
        .candidates
        .iter()
        .find(|candidate| candidate.code == symbol);
    let signal = selected.and_then(|candidate| candidate.signal.clone());
    let result_dir = runtime_root.join("ad_hoc").join(format!(
        "{}.{}.{}",
        pick_date.format("%Y-%m-%d"),
        args.method.as_str(),
        symbol
    ));
    std::fs::create_dir_all(&result_dir)?;
    let chart_path = result_dir.join(format!("{symbol}_day.png"));
    chart_renderer(&symbol, &prepared_history, &chart_path)?;
    let baseline_review = crate::native_review::build_single_symbol_baseline_review(
        args.method,
        &symbol,
        pick_date,
        &prepared_history,
        &chart_path,
        signal.as_deref(),
        args.environment_state,
        args.environment_reason,
    )?;
    let latest = prepared_history
        .iter()
        .rev()
        .find(|row| row.trade_date == pick_date)
        .ok_or_else(|| {
            anyhow::anyhow!("No prepared row found for symbol {symbol} on {pick_date}")
        })?;
    let payload = serde_json::json!({
        "code": symbol,
        "pick_date": pick_date,
        "method": args.method.as_str(),
        "signal": signal,
        "selected_as_candidate": selected.is_some(),
        "screen_conditions": analyze_symbol_screen_conditions(args.method, selected.is_some(), &strategy.stats),
        "latest_metrics": {
            "trade_date": pick_date,
            "open": round3(latest.open),
            "high": round3(latest.high),
            "low": round3(latest.low),
            "close": round3(latest.close),
            "volume": round3(latest.volume),
            "j": round3(latest.j),
        },
        "baseline_review": baseline_review,
        "chart_path": chart_path.canonicalize().unwrap_or(chart_path.clone()).display().to_string(),
    });
    let result_path = result_dir.join("result.json");
    atomic_write_json(&result_path, &payload)?;
    Ok(result_path)
}

fn analyze_symbol_screen_conditions(
    method: Method,
    selected: bool,
    stats: &std::collections::BTreeMap<String, usize>,
) -> serde_json::Value {
    serde_json::json!({
        "eligible": stats.get("eligible").copied().unwrap_or(0) > 0,
        "selected": selected,
        "first_failed_condition": if selected {
            None
        } else {
            resolve_analyze_symbol_failed_condition(method, stats)
        },
    })
}

fn resolve_analyze_symbol_failed_condition(
    method: Method,
    stats: &std::collections::BTreeMap<String, usize>,
) -> Option<String> {
    let ordered = match method {
        Method::B1 => vec![
            "fail_insufficient_history",
            "fail_j",
            "fail_close_zxdkx",
            "fail_zxdq_zxdkx",
            "fail_weekly_ma",
            "fail_max_vol",
            "fail_chg_cap",
            "fail_v_shrink",
            "fail_safe_mode",
            "fail_lt_filter",
        ],
        Method::B2 => vec!["fail_insufficient_history", "fail_no_signal"],
        Method::Dribull => vec![],
    };
    ordered
        .into_iter()
        .find(|key| stats.get(*key).copied().unwrap_or(0) > 0)
        .map(|key| key.trim_start_matches("fail_").to_string())
}

fn round3(value: f64) -> f64 {
    (value * 1000.0).round() / 1000.0
}

pub fn run_intraday_screen_with_provider<P, Prev, Load>(
    args: IntradayScreenArgs,
    provider: &P,
    fallback_trade_time: &str,
    previous_trade_date_loader: Prev,
    history_loader: Load,
) -> anyhow::Result<PathBuf>
where
    P: crate::intraday::IntradaySnapshotProvider,
    Prev: FnOnce(&str, NaiveDate) -> anyhow::Result<NaiveDate>,
    Load: FnOnce(&str, NaiveDate, NaiveDate) -> anyhow::Result<Vec<MarketRow>>,
{
    let started = Instant::now();
    let progress = ProgressReporter::new(args.progress);
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let dsn = resolve_dsn_from_env(args.dsn.as_deref())?;
    progress.step(
        "screen",
        "intraday-snapshot",
        "start",
        [
            ("trade_date", args.trade_date.to_string()),
            ("run_id", args.run_id.clone()),
        ],
    );
    let previous_trade_date = previous_trade_date_loader(&dsn, args.trade_date)?;
    let start_date = previous_trade_date - Duration::days(366);
    let snapshot =
        crate::intraday::fetch_rt_k_snapshot(provider, args.trade_date, fallback_trade_time)?;
    progress.step(
        "screen",
        "intraday-snapshot",
        "done",
        [
            ("rows", snapshot.len().to_string()),
            ("previous_trade_date", previous_trade_date.to_string()),
        ],
    );
    progress.step(
        "screen",
        "fetch-history",
        "start",
        [("window", format!("{start_date}..{previous_trade_date}"))],
    );
    let history = history_loader(&dsn, start_date, previous_trade_date)?;
    if history.is_empty() {
        anyhow::bail!("No market rows found between {start_date} and {previous_trade_date}.");
    }
    progress.step(
        "screen",
        "fetch-history",
        "done",
        [("rows", history.len().to_string())],
    );
    let market_rows =
        crate::intraday::build_intraday_market_rows(history, &snapshot, args.trade_date);
    progress.step(
        "screen",
        "prepare",
        "start",
        [("rows", market_rows.len().to_string())],
    );
    let prepared = prepare_rows(&market_rows);
    write_intraday_prepared_cache(
        &runtime_root,
        args.method,
        args.trade_date,
        start_date,
        previous_trade_date,
        &args.run_id,
        &prepared,
    )?;
    progress.step(
        "screen",
        "prepare",
        "done",
        [("rows", prepared.len().to_string())],
    );

    if !prepared.iter().any(|row| row.trade_date == args.trade_date) {
        anyhow::bail!(
            "No prepared rows found for intraday trade_date {}.",
            args.trade_date
        );
    }

    progress.step(
        "screen",
        "pool",
        "start",
        [("source", args.pool_source.as_str().to_string())],
    );
    let pool_selection = filter_pool(
        &prepared,
        args.trade_date,
        args.pool_source,
        args.pool_file.clone(),
        &runtime_root,
    )?;
    progress.step(
        "screen",
        "pool",
        "done",
        [
            ("source", args.pool_source.as_str().to_string()),
            (
                "symbols",
                unique_symbol_count(&pool_selection.rows).to_string(),
            ),
        ],
    );
    progress.step(
        "screen",
        "strategy",
        "start",
        [("method", args.method.as_str().to_string())],
    );
    let strategy = run_strategy(args.method, &pool_selection.rows, args.trade_date);
    progress.step(
        "screen",
        "strategy",
        "done",
        [
            ("method", args.method.as_str().to_string()),
            ("candidates", strategy.candidates.len().to_string()),
        ],
    );
    let mut result = build_screen_result_with_pool(
        args.method,
        args.trade_date,
        args.pool_source.as_str().to_string(),
        pool_selection
            .pool_file
            .map(|path| path.to_string_lossy().to_string()),
        strategy.candidates,
        strategy.stats,
    );
    result.mode = Some("intraday_snapshot".to_string());
    result.trade_date = Some(args.trade_date);
    result.fetched_at = Some(args.run_id.clone());
    result.run_id = Some(args.run_id.clone());
    result.source = Some("tushare_rt_k".to_string());
    let artifact_key = intraday_artifact_key(args.trade_date);
    let output_path = intraday_candidate_output_path(&runtime_root, &artifact_key, args.method);
    atomic_write_json(&output_path, &result)?;
    progress.step(
        "screen",
        "write-candidates",
        "done",
        [
            ("candidates", result.candidates.len().to_string()),
            ("path", output_path.display().to_string()),
            ("artifact_key", artifact_key),
            ("run_id", args.run_id.clone()),
        ],
    );
    progress.step(
        "screen",
        "total",
        "done",
        [(
            "elapsed_s",
            format!("{:.3}", started.elapsed().as_secs_f64()),
        )],
    );
    eprintln!(
        "[screen] intraday wrote {} elapsed={:.3}s",
        output_path.display(),
        started.elapsed().as_secs_f64()
    );
    Ok(output_path)
}

pub fn run_chart(args: ChartArgs) -> anyhow::Result<PathBuf> {
    let started = Instant::now();
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let output_path = run_native_chart(NativeChartArgs {
        method: args.method,
        pick_date: args.pick_date,
        runtime_root,
        codes: None,
        chart_workers: args.chart_workers,
        artifact_key: None,
        intraday: false,
        progress: args.progress,
    })?;
    eprintln!(
        "[chart] total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(output_path)
}

fn run_screen_command(args: ScreenArgs) -> anyhow::Result<PathBuf> {
    if args.intraday {
        if args.pick_date.is_some() {
            anyhow::bail!("--pick-date and --intraday are mutually exclusive.");
        }
        let trade_date = current_local_date();
        let run_id = format_intraday_run_id();
        let token = resolve_tushare_token(args.tushare_token.as_deref())?;
        let provider = crate::intraday::TushareRestProvider::new(token)?;
        let fallback_trade_time = current_local_time_string();
        return run_intraday_screen_with_provider(
            IntradayScreenArgs {
                method: args.method,
                trade_date,
                run_id,
                dsn: args.dsn,
                runtime_root: args.runtime_root,
                recompute: args.recompute,
                pool_source: args.pool_source,
                pool_file: args.pool_file,
                tushare_token: args.tushare_token,
                progress: args.progress,
            },
            &provider,
            &fallback_trade_time,
            |dsn, trade_date| crate::db::resolve_previous_trade_date(dsn, trade_date),
            |dsn, start, end| crate::db::fetch_daily_window(dsn, start, end),
        );
    }
    let pick_date = require_pick_date(args.pick_date)?;
    run_screen(
        ScreenArgs {
            pick_date: Some(pick_date),
            ..args
        },
        |dsn, start, end| crate::db::fetch_daily_window(dsn, start, end),
    )
}

pub fn run_review(args: ReviewArgs) -> anyhow::Result<PathBuf> {
    if args.intraday {
        anyhow::bail!(
            "review --intraday is not implemented yet; use run --intraday after intraday review is wired"
        );
    }
    let pick_date = require_pick_date(args.pick_date)?;
    let started = Instant::now();
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let (environment_state, environment_reason) = resolve_review_environment_args(
        &runtime_root,
        pick_date,
        args.dsn.as_deref(),
        args.environment_state,
        args.environment_reason,
    )?;
    let output_path = run_native_review(NativeReviewArgs {
        method: args.method,
        pick_date,
        runtime_root,
        environment_state,
        environment_reason,
        llm_min_baseline_score: args.llm_min_baseline_score,
        llm_review_limit: args.llm_review_limit,
        require_chart_files: true,
        artifact_key: None,
        intraday: false,
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
        args.intraday,
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
    intraday: bool,
    verdict: &str,
) -> anyhow::Result<Vec<Value>> {
    let normalized = normalize_verdict(verdict)?;
    let review_key = if intraday {
        format!("{}.intraday", pick_date.format("%Y-%m-%d"))
    } else {
        pick_date.format("%Y-%m-%d").to_string()
    };
    let summary_path = runtime_root
        .join("reviews")
        .join(format!("{}.{}", review_key, method.as_str()))
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
    if args.review.intraday {
        return run_intraday_hybrid(args);
    }
    let pick_date = require_pick_date(args.review.pick_date)?;
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
            pick_date: Some(pick_date),
            intraday: false,
            tushare_token: None,
            dsn: args.review.dsn.clone(),
            runtime_root: Some(runtime_root.clone()),
            recompute: args.recompute,
            pool_source: args.pool_source,
            pool_file: args.pool_file.clone(),
            progress: args.progress,
        },
        |dsn, start, end| crate::db::fetch_daily_window(dsn, start, end),
    )?;
    eprintln!(
        "[run] screen wrote {} elapsed={:.3}s",
        screen_path.display(),
        screen_started.elapsed().as_secs_f64()
    );

    let review_started = Instant::now();
    let summary_path = run_native_review(NativeReviewArgs {
        method,
        pick_date,
        runtime_root: runtime_root.clone(),
        environment_state,
        environment_reason,
        llm_min_baseline_score: args.review.llm_min_baseline_score,
        llm_review_limit: args.review.llm_review_limit,
        require_chart_files: false,
        artifact_key: None,
        intraday: false,
    })?;
    eprintln!(
        "[run] review elapsed={:.3}s",
        review_started.elapsed().as_secs_f64()
    );

    if args.review.llm_min_baseline_score.is_some() || args.review.llm_review_limit.is_some() {
        let chart_started = Instant::now();
        let chart_codes = load_llm_review_task_codes(&summary_path)?;
        run_native_chart(NativeChartArgs {
            method,
            pick_date,
            runtime_root: runtime_root.clone(),
            codes: Some(chart_codes),
            chart_workers: args.chart_workers,
            artifact_key: None,
            intraday: false,
            progress: args.progress,
        })?;
        eprintln!(
            "[run] chart elapsed={:.3}s",
            chart_started.elapsed().as_secs_f64()
        );
    } else {
        eprintln!("[run] chart skipped reason=no-llm-review-threshold");
    }
    eprintln!(
        "[run] total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(())
}

fn run_intraday_hybrid(args: RunArgs) -> anyhow::Result<()> {
    if args.review.pick_date.is_some() {
        anyhow::bail!("--pick-date and --intraday are mutually exclusive.");
    }
    let started = Instant::now();
    let runtime_root = args
        .review
        .runtime_root
        .clone()
        .unwrap_or_else(default_runtime_root);
    let method = args.review.method;
    let trade_date = current_local_date();
    let run_id = format_intraday_run_id();
    let token = resolve_tushare_token(args.tushare_token.as_deref())?;
    let provider = crate::intraday::TushareRestProvider::new(token)?;
    let fallback_trade_time = current_local_time_string();

    let screen_started = Instant::now();
    let screen_path = run_intraday_screen_with_provider(
        IntradayScreenArgs {
            method,
            trade_date,
            run_id: run_id.clone(),
            dsn: args.review.dsn.clone(),
            runtime_root: Some(runtime_root.clone()),
            recompute: args.recompute,
            pool_source: args.pool_source,
            pool_file: args.pool_file.clone(),
            tushare_token: args.tushare_token.clone(),
            progress: args.progress,
        },
        &provider,
        &fallback_trade_time,
        |dsn, trade_date| crate::db::resolve_previous_trade_date(dsn, trade_date),
        |dsn, start, end| crate::db::fetch_daily_window(dsn, start, end),
    )?;
    eprintln!(
        "[run] intraday screen wrote {} run_id={} elapsed={:.3}s",
        screen_path.display(),
        run_id,
        screen_started.elapsed().as_secs_f64()
    );

    let (environment_state, environment_reason) = resolve_review_environment_args(
        &runtime_root,
        trade_date,
        args.review.dsn.as_deref(),
        args.review.environment_state.clone(),
        args.review.environment_reason.clone(),
    )?;
    let review_started = Instant::now();
    let summary_path = run_native_review(NativeReviewArgs {
        method,
        pick_date: trade_date,
        runtime_root: runtime_root.clone(),
        environment_state,
        environment_reason,
        llm_min_baseline_score: args.review.llm_min_baseline_score,
        llm_review_limit: args.review.llm_review_limit,
        require_chart_files: false,
        artifact_key: Some(intraday_artifact_key(trade_date)),
        intraday: true,
    })?;
    eprintln!(
        "[run] intraday review elapsed={:.3}s",
        review_started.elapsed().as_secs_f64()
    );

    if args.review.llm_min_baseline_score.is_some() || args.review.llm_review_limit.is_some() {
        let chart_started = Instant::now();
        let chart_codes = load_llm_review_task_codes(&summary_path)?;
        run_native_chart(NativeChartArgs {
            method,
            pick_date: trade_date,
            runtime_root: runtime_root.clone(),
            codes: Some(chart_codes),
            chart_workers: args.chart_workers,
            artifact_key: Some(intraday_artifact_key(trade_date)),
            intraday: true,
            progress: args.progress,
        })?;
        eprintln!(
            "[run] intraday chart elapsed={:.3}s",
            chart_started.elapsed().as_secs_f64()
        );
    } else {
        eprintln!("[run] intraday chart skipped reason=no-llm-review-threshold");
    }
    eprintln!(
        "[run] intraday total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(())
}

fn load_llm_review_task_codes(summary_path: &std::path::Path) -> anyhow::Result<Vec<String>> {
    let review_dir = summary_path
        .parent()
        .ok_or_else(|| anyhow::anyhow!("summary path has no parent: {}", summary_path.display()))?;
    let tasks_path = review_dir.join("llm_review_tasks.json");
    let payload: Value = serde_json::from_slice(
        &std::fs::read(&tasks_path)
            .with_context(|| format!("read llm review tasks {}", tasks_path.display()))?,
    )
    .with_context(|| format!("parse llm review tasks {}", tasks_path.display()))?;
    Ok(payload
        .get("tasks")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|task| task.get("code").and_then(Value::as_str))
        .map(str::to_string)
        .collect())
}

fn resolve_tushare_token(cli_token: Option<&str>) -> anyhow::Result<String> {
    resolve_config_value(cli_token, "TUSHARE_TOKEN")
        .ok_or_else(|| anyhow::anyhow!("A Tushare token is required for intraday mode."))
}

fn require_pick_date(pick_date: Option<NaiveDate>) -> anyhow::Result<NaiveDate> {
    pick_date.ok_or_else(|| anyhow::anyhow!("--pick-date is required unless --intraday is set."))
}

fn current_local_date() -> NaiveDate {
    chrono::Local::now().date_naive()
}

fn current_local_time_string() -> String {
    chrono::Local::now().format("%H:%M:%S").to_string()
}

fn intraday_artifact_key(trade_date: NaiveDate) -> String {
    format!("{}.intraday", trade_date.format("%Y-%m-%d"))
}

fn format_intraday_run_id() -> String {
    chrono::Local::now()
        .format("%Y-%m-%dT%H-%M-%S-%6f%:z")
        .to_string()
        .replace(':', "-")
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
    let progress = ProgressReporter::new(args.progress);
    if args.intraday {
        anyhow::bail!("run_screen handles EOD only; use run_screen_command for --intraday");
    }
    let pick_date = require_pick_date(args.pick_date)?;
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    let dsn = resolve_dsn_from_env(args.dsn.as_deref())?;
    let (start_date, end_date) = screen_window(pick_date);
    progress.step(
        "screen",
        "load-prepared",
        "start",
        [
            ("pick_date", pick_date.to_string()),
            ("window", format!("{start_date}..{end_date}")),
        ],
    );

    let prepared = if !args.recompute {
        match load_prepared_cache(&runtime_root, args.method, pick_date, start_date, end_date) {
            Ok(Some(rows)) => {
                eprintln!("[screen] reuse prepared rows={}", rows.len());
                progress.step(
                    "screen",
                    "load-prepared",
                    "done",
                    [
                        ("rows", rows.len().to_string()),
                        ("source", "cache".to_string()),
                    ],
                );
                rows
            }
            Ok(None) => load_and_prepare(
                &runtime_root,
                args.method,
                pick_date,
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
                    pick_date,
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
            pick_date,
            start_date,
            end_date,
            &dsn,
            loader,
        )?
    };
    progress.step(
        "screen",
        "prepare",
        "done",
        [("rows", prepared.len().to_string())],
    );

    if !prepared.iter().any(|row| row.trade_date == pick_date) {
        anyhow::bail!("No prepared rows found for pick_date {}.", pick_date);
    }

    let pool_started = Instant::now();
    progress.step(
        "screen",
        "pool",
        "start",
        [("source", args.pool_source.as_str().to_string())],
    );
    let pool_selection = filter_pool(
        &prepared,
        pick_date,
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
    progress.step(
        "screen",
        "pool",
        "done",
        [
            ("source", args.pool_source.as_str().to_string()),
            (
                "symbols",
                unique_symbol_count(&pool_selection.rows).to_string(),
            ),
        ],
    );

    let strategy_started = Instant::now();
    progress.step(
        "screen",
        "strategy",
        "start",
        [("method", args.method.as_str().to_string())],
    );
    let strategy = run_strategy(args.method, &pool_selection.rows, pick_date);
    eprintln!(
        "[screen] strategy method={} candidates={} elapsed={:.3}s",
        args.method.as_str(),
        strategy.candidates.len(),
        strategy_started.elapsed().as_secs_f64()
    );
    progress.step(
        "screen",
        "strategy",
        "done",
        [
            ("method", args.method.as_str().to_string()),
            ("candidates", strategy.candidates.len().to_string()),
        ],
    );
    let result = build_screen_result_with_pool(
        args.method,
        pick_date,
        args.pool_source.as_str().to_string(),
        pool_selection
            .pool_file
            .map(|path| path.to_string_lossy().to_string()),
        strategy.candidates,
        strategy.stats,
    );
    let output_path = write_screen_result(&runtime_root, &result)?;
    progress.step(
        "screen",
        "write-candidates",
        "done",
        [
            ("candidates", result.candidates.len().to_string()),
            ("path", output_path.display().to_string()),
        ],
    );
    eprintln!(
        "[screen] total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    progress.step(
        "screen",
        "total",
        "done",
        [(
            "elapsed_s",
            format!("{:.3}", started.elapsed().as_secs_f64()),
        )],
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
        None => resolve_config_value(None, "STOCK_SELECT_POOL_FILE")
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
            pick_date: Some(pick),
            intraday: false,
            tushare_token: None,
            dsn: Some("postgresql://example".to_string()),
            runtime_root: Some(temp.path().to_path_buf()),
            recompute: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            progress: false,
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
