use std::collections::BTreeMap;
use std::fs::File;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};

use chrono::{Local, NaiveDate};
use clap::{Args, CommandFactory, Parser, Subcommand};
use clap_complete::{Shell, generate};
use serde::Serialize;
use serde_json::json;
use stock_select::cache::load_prepared_cache_for_mode;
use stock_select::config::{resolve_config_value, resolve_runtime_root};
use stock_select::db::{fetch_daily_window, fetch_instrument_info, resolve_previous_trade_date};
use stock_select::engine::artifacts::{
    SelectionRunPaths, read_selection_json, write_selection_json,
};
use stock_select::engine::b2::artifact_key_for_run;
use stock_select::engine::capability::ensure_model_run_supported;
use stock_select::engine::presentation::{
    fill_missing_display_instrument_info, format_display_lines, limit_display_rows,
    review_signal_symbol,
};
use stock_select::engine::run::{SelectionRunRequest, run_selection};
use stock_select::engine::types::{DisplayRow, LlmAnnotation};
use stock_select::environment::{
    ResolvedEnvironment, ensure_market_environment, normalize_environment_state,
    persist_prepared_market_environment, prepared_market_state,
    resolve_intraday_market_environment, resolve_market_environment,
};
use stock_select::intraday::TushareRestProvider;
use stock_select::model::{InstrumentInfo, MarketRow, Method, PreparedRow};
use stock_select::record::{RunRecordConfig, update_run_record};
use stock_select::screening::{
    PoolSource, ScreenRequest, run_intraday_screen_with_loaders, run_screen_with_loader,
};

#[derive(Debug, Parser)]
#[command(name = "stock-select-rs")]
#[command(about = "Rust acceleration path for stock-select screening")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Debug, Subcommand)]
enum Commands {
    Screen(ScreenArgs),
    Chart(ArtifactCommandArgs),
    CleanIntraday(CleanIntradayArgs),
    Review(ReviewArgs),
    ReviewMerge(ArtifactCommandArgs),
    ReviewList(ReviewListArgs),
    Run(RunArgs),
    Completions(CompletionsArgs),
}

#[derive(Debug, Args)]
struct MethodArgs {
    #[arg(long, default_value = "b2")]
    method: Method,

    #[arg(long)]
    intraday: bool,
}

#[derive(Debug, Args)]
struct ScreenArgs {
    #[command(flatten)]
    method: MethodArgs,

    #[arg(long)]
    runtime_root: Option<PathBuf>,

    #[arg(long)]
    dsn: Option<String>,

    #[arg(long)]
    tushare_token: Option<String>,

    #[arg(long)]
    pick_date: Option<NaiveDate>,

    #[arg(long)]
    recompute: bool,

    #[arg(long)]
    pool_file: Option<PathBuf>,

    #[arg(long, default_value = "turnover-top")]
    pool_source: PoolSource,

    #[arg(long)]
    export_factors: bool,

    #[arg(long)]
    environment_state: Option<String>,

    #[arg(long)]
    environment_reason: Option<String>,
}

#[derive(Debug, Args)]
struct ReviewListArgs {
    #[command(flatten)]
    method: MethodArgs,

    #[arg(long)]
    limit: Option<usize>,

    #[arg(long)]
    runtime_root: Option<PathBuf>,

    #[arg(long)]
    dsn: Option<String>,

    #[arg(long)]
    pick_date: Option<NaiveDate>,

    #[arg(long)]
    tushare_token: Option<String>,

    #[arg(long)]
    recompute: bool,

    #[arg(long)]
    pool_file: Option<PathBuf>,

    #[arg(long, default_value = "turnover-top")]
    pool_source: PoolSource,

    #[arg(long)]
    model_path: Option<PathBuf>,

    #[arg(long)]
    model_feature_metadata_path: Option<PathBuf>,

    #[arg(long)]
    environment_state: Option<String>,

    #[arg(long)]
    environment_reason: Option<String>,

    #[arg(long)]
    record: bool,

    #[arg(long)]
    record_window_trading_days: Option<usize>,
}

#[derive(Debug, Args)]
struct ArtifactCommandArgs {
    #[command(flatten)]
    method: MethodArgs,

    #[arg(long)]
    runtime_root: Option<PathBuf>,

    #[arg(long)]
    pick_date: Option<NaiveDate>,

    #[arg(long)]
    limit: Option<usize>,

    #[arg(long, default_value_t = 4)]
    chart_workers: usize,
}

#[derive(Debug, Args)]
struct ReviewArgs {
    #[command(flatten)]
    method: MethodArgs,

    #[arg(long)]
    runtime_root: Option<PathBuf>,

    #[arg(long)]
    pick_date: Option<NaiveDate>,

    #[arg(long)]
    limit: Option<usize>,

    #[arg(long)]
    environment_state: Option<String>,

    #[arg(long)]
    environment_reason: Option<String>,

    #[arg(long)]
    model_path: Option<PathBuf>,

    #[arg(long)]
    model_feature_metadata_path: Option<PathBuf>,

    #[arg(long)]
    record: bool,

    #[arg(long)]
    record_window_trading_days: Option<usize>,
}

#[derive(Debug, Args)]
struct CleanIntradayArgs {
    #[arg(long)]
    runtime_root: Option<PathBuf>,

    #[arg(long)]
    dry_run: bool,
}

#[derive(Debug, Default)]
struct ReviewTaskMetadata {
    environment_state: Option<String>,
    environment_reason: Option<String>,
    environment_source: Option<String>,
    environment_interval_start: Option<NaiveDate>,
    environment_interval_end: Option<NaiveDate>,
    model_path: Option<PathBuf>,
    model_feature_metadata_path: Option<PathBuf>,
    record: bool,
    record_window_trading_days: Option<usize>,
    record_limit: Option<usize>,
}

const REVIEW_TASK_INSTRUCTION: &str = "读取本行股票和 chart_path 日线图，按 A 股游资/短线复盘口径给出 annotation。重点看题材辨识度、龙虎榜/游资痕迹、涨停或连板接力潜力、量价承接、情绪周期、长上影/放量滞涨/高位派发等风险。只输出 KEEP/CAUTION/REJECT，不改变 model_rank；llm_comment 写一句中文短线结论；详细分析写入 llm_raw 对应 JSON，review-merge 会汇总为 HTML 报告。";
const MAX_RAW_REVIEW_REPORT_BYTES: usize = 16 * 1024;

#[derive(Debug, Args)]
struct CompletionsArgs {
    #[arg(long)]
    shell: Shell,
}

#[derive(Debug, Args)]
struct RunArgs {
    #[command(flatten)]
    method: MethodArgs,

    #[arg(long)]
    runtime_root: Option<PathBuf>,

    #[arg(long)]
    dsn: Option<String>,

    #[arg(long)]
    tushare_token: Option<String>,

    #[arg(long)]
    pick_date: Option<NaiveDate>,

    #[arg(long)]
    candidates_path: Option<PathBuf>,

    #[arg(long)]
    pool_file: Option<PathBuf>,

    #[arg(long, default_value = "turnover-top")]
    pool_source: PoolSource,

    #[arg(long, default_value_t = 4)]
    chart_workers: usize,

    #[arg(long)]
    llm_review_limit: Option<usize>,

    #[arg(long)]
    environment_state: Option<String>,

    #[arg(long)]
    environment_reason: Option<String>,

    #[arg(long)]
    model_path: Option<PathBuf>,

    #[arg(long)]
    model_feature_metadata_path: Option<PathBuf>,

    #[arg(long)]
    record: bool,

    #[arg(long)]
    record_window_trading_days: Option<usize>,

    #[arg(long)]
    recompute: bool,
}

#[derive(Debug, Serialize)]
struct ChartPayload {
    charts: Vec<ChartItem>,
}

#[derive(Debug, Serialize)]
struct ChartItem {
    code: String,
    out_path: String,
    rows: Vec<ChartRow>,
}

#[derive(Debug, Serialize)]
struct ChartRow {
    date: NaiveDate,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
    ma25: Option<f64>,
    zxdq: Option<f64>,
    zxdkx: Option<f64>,
    dif: f64,
    dea: f64,
    macd_hist: f64,
}

fn main() -> anyhow::Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Screen(args) => run_screen_command(args),
        Commands::Chart(args) => run_chart_command(args),
        Commands::CleanIntraday(args) => run_clean_intraday_command(args),
        Commands::Review(args) => run_review_command(args),
        Commands::ReviewMerge(args) => run_review_merge_command(args),
        Commands::ReviewList(args) => run_review_list(args),
        Commands::Run(args) => run_selection_command(args),
        Commands::Completions(args) => {
            let mut command = Cli::command();
            generate(
                args.shell,
                &mut command,
                "stock-select-rs",
                &mut std::io::stdout(),
            );
            Ok(())
        }
    }
}

fn run_screen_command(args: ScreenArgs) -> anyhow::Result<()> {
    let pick_date = resolve_pick_date(args.pick_date, args.method.intraday, "screen")?;
    let runtime_root = resolve_runtime_root(args.runtime_root.as_deref());
    let dsn = resolve_config_value(args.dsn.as_deref(), "POSTGRES_DSN").unwrap_or_default();
    let environment_state = args
        .environment_state
        .as_deref()
        .map(normalize_environment_state)
        .transpose()?;
    let request = ScreenRequest {
        method: args.method.method,
        pick_date,
        runtime_root: runtime_root.clone(),
        dsn,
        recompute: args.recompute,
        pool_source: if args.pool_file.is_some() {
            PoolSource::Custom
        } else {
            args.pool_source
        },
        pool_file: args.pool_file,
        export_factors: args.export_factors,
        environment_state,
    };
    let path = if args.method.intraday {
        let token = resolve_config_value(args.tushare_token.as_deref(), "TUSHARE_TOKEN")
            .ok_or_else(|| anyhow::anyhow!("A Tushare token is required for intraday mode."))?;
        let provider = TushareRestProvider::new(token)?;
        run_intraday_screen_with_loaders(
            request,
            &provider,
            "15:00:00",
            resolve_previous_trade_date,
            fetch_daily_window_if_dsn,
        )?
    } else {
        run_screen_with_loader(request, fetch_daily_window_if_dsn)?
    };
    let display_path = path.strip_prefix(&runtime_root).unwrap_or(&path);
    println!("screen complete: {}", display_path.display());
    Ok(())
}

fn run_selection_command(args: RunArgs) -> anyhow::Result<()> {
    ensure_model_run_supported(args.method.method)?;
    let runtime_root = resolve_runtime_root(args.runtime_root.as_deref());
    let dsn = resolve_config_value(args.dsn.as_deref(), "POSTGRES_DSN").unwrap_or_default();
    let _tushare_token = resolve_config_value(args.tushare_token.as_deref(), "TUSHARE_TOKEN");
    let pick_date = resolve_pick_date(args.pick_date, args.method.intraday, "run")?;
    eprintln!(
        "[run] start method={} pick_date={} intraday={} runtime_root={}",
        args.method.method,
        pick_date,
        args.method.intraday,
        runtime_root.display()
    );
    let candidates_path = match args.candidates_path {
        Some(path) => {
            eprintln!("[run] candidates explicit path={}", path.display());
            path
        }
        None => {
            eprintln!("[run] candidates auto-screen start");
            let request = ScreenRequest {
                method: args.method.method,
                pick_date,
                runtime_root: runtime_root.clone(),
                dsn: dsn.clone(),
                recompute: args.recompute,
                pool_source: if args.pool_file.is_some() {
                    PoolSource::Custom
                } else {
                    args.pool_source
                },
                pool_file: args.pool_file,
                export_factors: false,
                environment_state: None,
            };
            let path = if args.method.intraday {
                let token = resolve_config_value(args.tushare_token.as_deref(), "TUSHARE_TOKEN")
                    .ok_or_else(|| {
                        anyhow::anyhow!("A Tushare token is required for intraday mode.")
                    })?;
                let provider = TushareRestProvider::new(token)?;
                run_intraday_screen_with_loaders(
                    request,
                    &provider,
                    "15:00:00",
                    resolve_previous_trade_date,
                    fetch_daily_window_if_dsn,
                )?
            } else {
                run_screen_with_loader(request, fetch_daily_window_if_dsn)?
            };
            let display_path = path.strip_prefix(&runtime_root).unwrap_or(&path);
            eprintln!(
                "[run] candidates auto-screen complete path={}",
                display_path.display()
            );
            path
        }
    };
    eprintln!("[run] selection start");
    let environment = resolve_command_environment(
        &runtime_root,
        pick_date,
        args.method.intraday,
        dsn.as_str(),
        args.environment_state.clone(),
        args.environment_reason.clone(),
    )?;
    let record_config = if args.method.intraday {
        None
    } else {
        RunRecordConfig::for_run(
            args.method.method,
            args.record,
            args.record_window_trading_days,
        )?
    };
    let result = run_selection(SelectionRunRequest {
        method: args.method.method,
        pick_date,
        runtime_root: runtime_root.clone(),
        intraday: args.method.intraday,
        candidates_path,
        model_path: args.model_path.clone(),
        model_feature_metadata_path: args.model_feature_metadata_path.clone(),
        environment: Some(environment.clone()),
        record: record_config.is_some(),
        record_window_trading_days: record_config
            .as_ref()
            .map(|config| config.window_trading_days),
        record_limit: record_config.as_ref().map(|config| config.record_limit),
    })?;
    let artifact_args = ArtifactCommandArgs {
        method: MethodArgs {
            method: args.method.method,
            intraday: args.method.intraday,
        },
        runtime_root: Some(runtime_root.clone()),
        pick_date: Some(pick_date),
        limit: args.llm_review_limit,
        chart_workers: args.chart_workers,
    };
    let artifact_key = artifact_key_for_run(pick_date, args.method.intraday);
    let paths = SelectionRunPaths::new(&runtime_root, args.method.method, &artifact_key);
    maybe_update_run_record(
        &runtime_root,
        &paths,
        args.method.method,
        pick_date,
        args.method.intraday,
        record_config.as_ref(),
    )?;
    if artifact_args.limit.is_some() {
        eprintln!("[run] chart start");
        match write_chart_artifacts(
            &runtime_root,
            &paths,
            args.method.method,
            &artifact_key,
            pick_date,
            args.method.intraday,
            artifact_args.chart_workers,
            artifact_args.limit,
        ) {
            Ok(rows) => eprintln!("[run] chart done rows={rows}"),
            Err(err) => eprintln!("[run] chart skipped reason={err}"),
        }
        eprintln!("[run] review task start");
        let rows = write_review_task_artifacts(
            &paths,
            args.method.method,
            &artifact_key,
            artifact_args.limit,
            &ReviewTaskMetadata {
                environment_state: Some(environment.state.clone()),
                environment_reason: environment
                    .reason
                    .clone()
                    .or_else(|| args.environment_reason.clone()),
                environment_source: Some(environment.source.clone()),
                environment_interval_start: environment.interval_start,
                environment_interval_end: environment.interval_end,
                model_path: args.model_path.clone(),
                model_feature_metadata_path: args.model_feature_metadata_path.clone(),
                record: record_config.is_some(),
                record_window_trading_days: record_config
                    .as_ref()
                    .map(|config| config.window_trading_days),
                record_limit: record_config.as_ref().map(|config| config.record_limit),
            },
        )?;
        eprintln!("[run] review task done rows={rows}");
        let _ = rows;
    } else {
        eprintln!("[run] chart skipped reason=no-llm-review-limit");
        write_empty_review_task_artifacts(
            &paths,
            args.method.method,
            &artifact_key,
            &ReviewTaskMetadata {
                environment_state: Some(environment.state.clone()),
                environment_reason: environment.reason.or(args.environment_reason),
                environment_source: Some(environment.source),
                environment_interval_start: environment.interval_start,
                environment_interval_end: environment.interval_end,
                model_path: args.model_path,
                model_feature_metadata_path: args.model_feature_metadata_path,
                record: record_config.is_some(),
                record_window_trading_days: record_config
                    .as_ref()
                    .map(|config| config.window_trading_days),
                record_limit: record_config.as_ref().map(|config| config.record_limit),
            },
        )?;
    }
    let display_run_dir = result
        .run_dir
        .strip_prefix(&runtime_root)
        .unwrap_or(&result.run_dir);
    println!(
        "selection run complete: {} rows={} artifact_key={}",
        display_run_dir.display(),
        result.rows,
        result.artifact_key
    );
    Ok(())
}

fn maybe_update_run_record(
    runtime_root: &Path,
    paths: &SelectionRunPaths,
    method: Method,
    pick_date: NaiveDate,
    intraday: bool,
    record_config: Option<&RunRecordConfig>,
) -> anyhow::Result<()> {
    if intraday {
        return Ok(());
    }
    let Some(config) = record_config else {
        return Ok(());
    };
    let rows = read_display_rows(paths)?;
    let count = update_run_record(
        runtime_root,
        method,
        pick_date,
        &rows,
        config.window_trading_days,
        config.record_limit,
    )?;
    eprintln!("[run] record updated rows={count}");
    Ok(())
}

fn run_clean_intraday_command(args: CleanIntradayArgs) -> anyhow::Result<()> {
    let runtime_root = resolve_runtime_root(args.runtime_root.as_deref());
    let artifacts = find_intraday_runtime_artifacts(&runtime_root)?;
    if args.dry_run {
        println!("clean-intraday dry-run: removable={}", artifacts.len());
        return Ok(());
    }
    let removed = remove_intraday_runtime_artifacts(&artifacts)?;
    println!("clean-intraday complete: removed={removed}");
    Ok(())
}

fn find_intraday_runtime_artifacts(runtime_root: &Path) -> anyhow::Result<Vec<PathBuf>> {
    let mut artifacts = Vec::new();
    for dir_name in ["candidates", "prepared", "factors", "charts", "select"] {
        let dir = runtime_root.join(dir_name);
        if !dir.exists() {
            continue;
        }
        for entry in std::fs::read_dir(&dir)? {
            let path = entry?.path();
            let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
                continue;
            };
            if !name.contains(".intraday.") {
                continue;
            }
            artifacts.push(path);
        }
    }
    artifacts.sort();
    Ok(artifacts)
}

fn remove_intraday_runtime_artifacts(paths: &[PathBuf]) -> anyhow::Result<usize> {
    for path in paths {
        remove_runtime_entry(path)?;
    }
    Ok(paths.len())
}

fn remove_runtime_entry(path: &Path) -> anyhow::Result<()> {
    let metadata = std::fs::symlink_metadata(path)?;
    if metadata.is_dir() {
        std::fs::remove_dir_all(path)?;
    } else {
        std::fs::remove_file(path)?;
    }
    Ok(())
}

fn resolve_pick_date(
    pick_date: Option<NaiveDate>,
    intraday: bool,
    command: &str,
) -> anyhow::Result<NaiveDate> {
    if let Some(pick_date) = pick_date {
        return Ok(pick_date);
    }
    if intraday {
        let inferred = Local::now().date_naive();
        eprintln!("[{command}] inferred pick_date={inferred} for intraday mode");
        return Ok(inferred);
    }
    anyhow::bail!("{command} requires --pick-date")
}

fn resolve_command_environment(
    runtime_root: &Path,
    pick_date: NaiveDate,
    intraday: bool,
    dsn: &str,
    manual_state: Option<String>,
    manual_reason: Option<String>,
) -> anyhow::Result<ResolvedEnvironment> {
    if intraday {
        let previous_trade_date = if dsn.trim().is_empty() {
            Some(pick_date - chrono::Duration::days(1))
        } else {
            resolve_previous_trade_date(dsn, pick_date).ok()
        };
        return resolve_intraday_market_environment(
            runtime_root,
            pick_date,
            manual_state,
            manual_reason,
            previous_trade_date,
        );
    }

    let resolved = if manual_state.is_some() {
        ensure_market_environment(runtime_root, pick_date, manual_state, manual_reason, || {
            unreachable!("manual environment state should not evaluate")
        })?
    } else if let Ok(resolved) = resolve_market_environment(runtime_root, pick_date) {
        resolved
    } else {
        resolve_prepared_market_environment(runtime_root, pick_date)?
    };
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
    Ok(resolved)
}

fn resolve_prepared_market_environment(
    runtime_root: &Path,
    pick_date: NaiveDate,
) -> anyhow::Result<ResolvedEnvironment> {
    let start_date = pick_date - chrono::Duration::days(366);
    let Some(rows) = load_prepared_cache_for_mode(
        runtime_root,
        Method::B2,
        pick_date,
        start_date,
        pick_date,
        false,
    )?
    else {
        anyhow::bail!(
            "No manual, persisted, or prepared market environment is available for {pick_date}."
        );
    };
    let state = prepared_market_state(&rows, pick_date).ok_or_else(|| {
        anyhow::anyhow!("Prepared cache has no usable market state for {pick_date}.")
    })?;
    persist_prepared_market_environment(
        runtime_root,
        pick_date,
        state,
        "derived from prepared market breadth factors".to_string(),
    )
}

fn run_chart_command(args: ArtifactCommandArgs) -> anyhow::Result<()> {
    let (runtime_root, paths, artifact_key, pick_date) =
        resolve_artifact_command_paths(&args, "chart")?;
    let rows = write_chart_artifacts(
        &runtime_root,
        &paths,
        args.method.method,
        &artifact_key,
        pick_date,
        args.method.intraday,
        args.chart_workers,
        None,
    )?;
    let chart_dir = chart_output_dir(&runtime_root, args.method.method, &artifact_key);
    let display_path = chart_dir.strip_prefix(&runtime_root).unwrap_or(&chart_dir);
    println!("chart complete: {} rows={}", display_path.display(), rows);
    Ok(())
}

fn write_chart_artifacts(
    runtime_root: &Path,
    paths: &SelectionRunPaths,
    method: Method,
    artifact_key: &str,
    pick_date: NaiveDate,
    intraday: bool,
    chart_workers: usize,
    limit: Option<usize>,
) -> anyhow::Result<usize> {
    let rows = limit_display_rows(read_display_rows(&paths)?, limit)?;
    let history_by_code = load_chart_histories(runtime_root, method, pick_date, intraday)?;
    let chart_dir = chart_output_dir(runtime_root, method, artifact_key);
    std::fs::create_dir_all(&chart_dir)?;
    let mut charts = Vec::new();
    for row in &rows {
        let history = history_by_code
            .get(row.code.as_str())
            .ok_or_else(|| anyhow::anyhow!("No price history found for candidate: {}", row.code))?;
        charts.push(ChartItem {
            code: row.code.clone(),
            out_path: chart_dir
                .join(format!("{}_day.png", row.code))
                .to_string_lossy()
                .to_string(),
            rows: history.iter().map(chart_row_from_prepared).collect(),
        });
    }
    let payload_paths =
        write_chart_payloads(runtime_root, method, artifact_key, charts, chart_workers)?;
    run_chart_renderers(&payload_paths)?;
    Ok(rows.len())
}

fn chart_output_dir(runtime_root: &Path, method: Method, artifact_key: &str) -> PathBuf {
    runtime_root
        .join("charts")
        .join(format!("{}.{}", artifact_key, method.as_str()))
}

fn deterministic_chart_path(method: Method, artifact_key: &str, code: &str) -> String {
    format!(
        "charts/{}.{}//{}_day.png",
        artifact_key,
        method.as_str(),
        code
    )
    .replace("//", "/")
}

fn write_chart_payloads(
    runtime_root: &Path,
    method: Method,
    artifact_key: &str,
    charts: Vec<ChartItem>,
    chart_workers: usize,
) -> anyhow::Result<Vec<PathBuf>> {
    cleanup_chart_payloads(runtime_root, method, artifact_key)?;
    let chunks = split_chart_items(charts, chart_workers);
    let chunk_count = chunks.len();
    let mut payload_paths = Vec::with_capacity(chunk_count);
    for (idx, chunk) in chunks.into_iter().enumerate() {
        let payload_path = if chunk_count == 1 {
            runtime_root.join("charts").join(format!(
                "{}.{}.payload.json",
                artifact_key,
                method.as_str()
            ))
        } else {
            runtime_root.join("charts").join(format!(
                "{}.{}.payload.part-{:02}-of-{:02}.json",
                artifact_key,
                method.as_str(),
                idx + 1,
                chunk_count
            ))
        };
        write_selection_json(&payload_path, &ChartPayload { charts: chunk })?;
        payload_paths.push(payload_path);
    }
    Ok(payload_paths)
}

fn cleanup_chart_payloads(
    runtime_root: &Path,
    method: Method,
    artifact_key: &str,
) -> anyhow::Result<()> {
    let charts_dir = runtime_root.join("charts");
    if !charts_dir.exists() {
        return Ok(());
    }
    let prefix = format!("{}.{}.payload", artifact_key, method.as_str());
    for entry in std::fs::read_dir(charts_dir)? {
        let path = entry?.path();
        let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
            continue;
        };
        if name.starts_with(&prefix) && name.ends_with(".json") {
            std::fs::remove_file(path)?;
        }
    }
    Ok(())
}

fn split_chart_items(charts: Vec<ChartItem>, chart_workers: usize) -> Vec<Vec<ChartItem>> {
    if charts.is_empty() {
        return vec![Vec::new()];
    }
    let worker_count = chart_workers.max(1).min(charts.len());
    let mut chunks = (0..worker_count).map(|_| Vec::new()).collect::<Vec<_>>();
    for (idx, chart) in charts.into_iter().enumerate() {
        chunks[idx % worker_count].push(chart);
    }
    chunks
        .into_iter()
        .filter(|chunk| !chunk.is_empty())
        .collect()
}

fn run_chart_renderers(payload_paths: &[PathBuf]) -> anyhow::Result<()> {
    if payload_paths.len() <= 1 {
        if let Some(path) = payload_paths.first() {
            let mut child = spawn_chart_renderer(path)?;
            wait_chart_renderer(path, &mut child)?;
        }
        remove_chart_payloads(payload_paths);
        return Ok(());
    }

    let mut children = Vec::with_capacity(payload_paths.len());
    for payload_path in payload_paths {
        children.push((payload_path.clone(), spawn_chart_renderer(payload_path)?));
    }
    let mut failures = Vec::new();
    for (payload_path, mut child) in children {
        if let Err(err) = wait_chart_renderer(&payload_path, &mut child) {
            failures.push(err.to_string());
        }
    }
    if !failures.is_empty() {
        anyhow::bail!("local chart renderer failed: {}", failures.join("; "));
    }
    remove_chart_payloads(payload_paths);
    Ok(())
}

fn remove_chart_payloads(payload_paths: &[PathBuf]) {
    for path in payload_paths {
        if path.exists() {
            let _ = std::fs::remove_file(path);
        }
    }
}

fn spawn_chart_renderer(payload_path: &Path) -> anyhow::Result<Child> {
    let payload = payload_path
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("invalid chart payload path"))?;
    if let Some(renderer) = std::env::var_os("STOCK_SELECT_CHART_RENDERER") {
        return Command::new(renderer)
            .args(["--input", payload])
            .spawn()
            .map_err(Into::into);
    }
    let script_path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("scripts/render_charts.py");
    let script = script_path
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("invalid chart script path"))?;
    Command::new("uv")
        .args(["run", script, "--input", payload])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .spawn()
        .map_err(Into::into)
}

fn wait_chart_renderer(payload_path: &Path, child: &mut Child) -> anyhow::Result<()> {
    let status = child.wait()?;
    if !status.success() {
        anyhow::bail!("{} status={status}", payload_path.display());
    }
    Ok(())
}

fn chart_row_from_prepared(row: &PreparedRow) -> ChartRow {
    ChartRow {
        date: row.trade_date,
        open: row.open,
        high: row.high,
        low: row.low,
        close: row.close,
        volume: row.volume,
        ma25: row.ma25,
        zxdq: row.zxdq,
        zxdkx: row.zxdkx,
        dif: row.dif,
        dea: row.dea,
        macd_hist: row.macd_hist,
    }
}

fn run_review_command(args: ReviewArgs) -> anyhow::Result<()> {
    ensure_model_run_supported(args.method.method)?;
    let pick_date = resolve_pick_date(args.pick_date, args.method.intraday, "review")?;
    let runtime_root = resolve_runtime_root(args.runtime_root.as_deref());
    let dsn = resolve_config_value(None, "POSTGRES_DSN").unwrap_or_default();
    let artifact_key = artifact_key_for_run(pick_date, args.method.intraday);
    let paths = SelectionRunPaths::new(&runtime_root, args.method.method, &artifact_key);
    let environment = resolve_command_environment(
        &runtime_root,
        pick_date,
        args.method.intraday,
        dsn.as_str(),
        args.environment_state.clone(),
        args.environment_reason.clone(),
    )?;
    let rows = write_review_task_artifacts(
        &paths,
        args.method.method,
        &artifact_key,
        args.limit,
        &ReviewTaskMetadata {
            environment_state: Some(environment.state.clone()),
            environment_reason: args.environment_reason.or(environment.reason.clone()),
            environment_source: Some(environment.source),
            environment_interval_start: environment.interval_start,
            environment_interval_end: environment.interval_end,
            model_path: args.model_path,
            model_feature_metadata_path: args.model_feature_metadata_path,
            record: args.record,
            record_window_trading_days: args.record_window_trading_days,
            record_limit: None,
        },
    )?;
    let tasks_path = paths.llm_tasks_path();
    let display_path = tasks_path
        .strip_prefix(&runtime_root)
        .unwrap_or(&tasks_path);
    println!(
        "review tasks complete: {} rows={}",
        display_path.display(),
        rows
    );
    Ok(())
}

fn write_review_task_artifacts(
    paths: &SelectionRunPaths,
    method: Method,
    artifact_key: &str,
    limit: Option<usize>,
    metadata: &ReviewTaskMetadata,
) -> anyhow::Result<usize> {
    let rows = limit_display_rows(read_display_rows(paths)?, limit)?;
    let task_rows = rows
        .iter()
        .map(|row| {
            let raw_response_path = format!(
                "select/{}.{}/llm_raw/{}.json",
                artifact_key,
                method.as_str(),
                row.code
            );
            let llm_report_path = format!(
                "select/{}.{}/llm_report.html",
                artifact_key,
                method.as_str()
            );
            json!({
                "code": row.code,
                "name": row.name,
                "industry": row.industry,
                "model_rank": row.model_rank,
                "model_score": row.model_score,
                "chart_path": deterministic_chart_path(method, artifact_key, &row.code),
                "raw_response_path": raw_response_path,
                "llm_report_path": llm_report_path,
                "llm_instruction": REVIEW_TASK_INSTRUCTION,
            })
        })
        .collect::<Vec<_>>();
    write_selection_json(
        &paths.llm_tasks_path(),
        &json!({
            "method": method.as_str(),
            "artifact_key": artifact_key,
            "environment": {
                "state": metadata.environment_state,
                "reason": metadata.environment_reason,
                "source": metadata.environment_source,
                "interval_start": metadata.environment_interval_start,
                "interval_end": metadata.environment_interval_end,
            },
            "model_path": metadata.model_path,
            "model_feature_metadata_path": metadata.model_feature_metadata_path,
            "record": {
                "enabled": metadata.record,
                "window_trading_days": metadata.record_window_trading_days,
                "limit": metadata.record_limit,
            },
            "rows": task_rows,
        }),
    )?;
    if !paths.llm_annotations_path().exists() {
        write_selection_json(
            &paths.llm_annotations_path(),
            &json!({
                "method": method.as_str(),
                "artifact_key": artifact_key,
                "rows": [],
            }),
        )?;
    }
    Ok(rows.len())
}

fn write_empty_review_task_artifacts(
    paths: &SelectionRunPaths,
    method: Method,
    artifact_key: &str,
    metadata: &ReviewTaskMetadata,
) -> anyhow::Result<()> {
    write_selection_json(
        &paths.llm_tasks_path(),
        &json!({
            "method": method.as_str(),
            "artifact_key": artifact_key,
            "environment": {
                "state": metadata.environment_state,
                "reason": metadata.environment_reason,
                "source": metadata.environment_source,
                "interval_start": metadata.environment_interval_start,
                "interval_end": metadata.environment_interval_end,
            },
            "model_path": metadata.model_path,
            "model_feature_metadata_path": metadata.model_feature_metadata_path,
            "record": {
                "enabled": metadata.record,
                "window_trading_days": metadata.record_window_trading_days,
                "limit": metadata.record_limit,
            },
            "rows": [],
        }),
    )?;
    if !paths.llm_annotations_path().exists() {
        write_selection_json(
            &paths.llm_annotations_path(),
            &json!({
                "method": method.as_str(),
                "artifact_key": artifact_key,
                "rows": [],
            }),
        )?;
    }
    Ok(())
}

fn run_review_merge_command(args: ArtifactCommandArgs) -> anyhow::Result<()> {
    let (runtime_root, paths, artifact_key, _pick_date) =
        resolve_artifact_command_paths(&args, "review-merge")?;
    let mut rows = read_display_rows(&paths)?;
    let annotations = read_annotations(&paths)?;
    let by_code = annotations
        .iter()
        .map(|annotation| (annotation.code.as_str(), annotation))
        .collect::<BTreeMap<_, _>>();
    for row in &mut rows {
        if let Some(annotation) = by_code.get(row.code.as_str()) {
            row.llm_action = Some(annotation.llm_action.clone());
            row.llm_risk_flags = annotation.llm_risk_flags.clone();
            row.llm_comment = annotation.llm_comment.clone();
        }
    }
    write_selection_json(
        &paths.display_path(),
        &json!({
            "method": args.method.method.as_str(),
            "artifact_key": artifact_key,
            "rows": rows,
        }),
    )?;
    write_llm_review_html_report(
        &runtime_root,
        &paths,
        args.method.method,
        &artifact_key,
        &rows,
        &annotations,
    )?;
    let display_path = paths.display_path();
    let display_path = display_path
        .strip_prefix(&runtime_root)
        .unwrap_or(&display_path);
    println!(
        "review-merge complete: {} rows={} annotations={}",
        display_path.display(),
        rows.len(),
        annotations.len()
    );
    Ok(())
}

fn write_llm_review_html_report(
    runtime_root: &Path,
    paths: &SelectionRunPaths,
    method: Method,
    artifact_key: &str,
    rows: &[DisplayRow],
    annotations: &[LlmAnnotation],
) -> anyhow::Result<()> {
    let task_rows = read_review_task_rows(paths).unwrap_or_default();
    let html = render_llm_review_html_report(
        runtime_root,
        paths,
        method,
        artifact_key,
        rows,
        annotations,
        &task_rows,
    );
    std::fs::write(paths.run_dir.join("llm_report.html"), html)?;
    Ok(())
}

fn read_review_task_rows(
    paths: &SelectionRunPaths,
) -> anyhow::Result<BTreeMap<String, serde_json::Value>> {
    let payload = read_selection_json(&paths.llm_tasks_path())?;
    let rows = payload
        .get("rows")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();
    Ok(rows
        .into_iter()
        .filter_map(|row| {
            let code = row.get("code")?.as_str()?.to_string();
            Some((code, row))
        })
        .collect())
}

fn render_llm_review_html_report(
    runtime_root: &Path,
    paths: &SelectionRunPaths,
    method: Method,
    artifact_key: &str,
    rows: &[DisplayRow],
    annotations: &[LlmAnnotation],
    task_rows: &BTreeMap<String, serde_json::Value>,
) -> String {
    let by_code = annotations
        .iter()
        .map(|annotation| (annotation.code.as_str(), annotation))
        .collect::<BTreeMap<_, _>>();
    let generated_at = Local::now().format("%Y-%m-%d %H:%M:%S");
    let mut html = String::new();
    html.push_str("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">");
    html.push_str("<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">");
    html.push_str("<title>LLM 游资复盘报告</title>");
    html.push_str("<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;background:#f6f7f9;color:#172033}.wrap{max-width:1180px;margin:0 auto;padding:24px}h1{margin:0 0 8px;font-size:28px}.meta{color:#667085;margin-bottom:20px}.grid{display:grid;gap:16px}.card{background:#fff;border:1px solid #d9dee8;border-radius:8px;padding:16px}.head{display:flex;gap:12px;align-items:center;justify-content:space-between;border-bottom:1px solid #edf0f5;padding-bottom:10px;margin-bottom:12px}.title{font-size:18px;font-weight:700}.signal{font-size:28px;font-weight:800}.signal.up{color:#b42318}.signal.flat{color:#8a5a00}.signal.down{color:#175cd3}.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin:12px 0}.kv div{background:#f8fafc;border:1px solid #eef2f6;border-radius:6px;padding:8px}.label{display:block;color:#667085;font-size:12px;margin-bottom:4px}.comment{font-size:15px;line-height:1.65}.flags span{display:inline-block;margin:0 6px 6px 0;padding:3px 8px;border-radius:999px;background:#eef4ff;color:#3538cd;font-size:12px}.chart{margin-top:12px}.chart img{max-width:100%;border:1px solid #d9dee8;border-radius:6px;background:#fff}.raw{white-space:pre-wrap;overflow:auto;max-height:260px;background:#111827;color:#e5e7eb;border-radius:6px;padding:12px;font-size:12px}.empty{color:#98a2b3}</style>");
    html.push_str("</head><body><main class=\"wrap\">");
    html.push_str(&format!(
        "<h1>LLM 游资复盘报告</h1><div class=\"meta\">method={} · artifact={} · generated={}</div><section class=\"grid\">",
        html_escape(method.as_str()),
        html_escape(artifact_key),
        html_escape(&generated_at.to_string())
    ));

    for row in rows {
        let annotation = by_code.get(row.code.as_str()).copied();
        let task = task_rows.get(&row.code);
        let action = row.llm_action.as_deref().unwrap_or("-");
        let signal = review_signal_symbol(row.llm_action.as_deref());
        let signal_class = match signal {
            "↑" => "up",
            "↓" => "down",
            "→" => "flat",
            _ => "",
        };
        let name = row.name.as_deref().unwrap_or("-");
        let industry = row.industry.as_deref().unwrap_or("-");
        let rank = row
            .model_rank
            .map(|value| value.to_string())
            .unwrap_or_else(|| "-".to_string());
        let score = row
            .model_score
            .map(|value| format!("{value:.6}"))
            .unwrap_or_else(|| "-".to_string());
        let confidence = annotation
            .and_then(|item| item.llm_confidence)
            .map(|value| format!("{value:.2}"))
            .unwrap_or_else(|| "-".to_string());
        let comment = row
            .llm_comment
            .as_deref()
            .filter(|value| !value.trim().is_empty())
            .unwrap_or("暂无子代理评价。");
        let flags = if row.llm_risk_flags.is_empty() {
            "<span class=\"empty\">-</span>".to_string()
        } else {
            row.llm_risk_flags
                .iter()
                .map(|flag| format!("<span>{}</span>", html_escape(flag)))
                .collect::<Vec<_>>()
                .join("")
        };
        let chart_path = task
            .and_then(|item| item.get("chart_path"))
            .and_then(|item| item.as_str());
        let chart_html = chart_path
            .map(|path| {
                let report_path = report_relative_runtime_path(path);
                format!(
                    "<div class=\"chart\"><img src=\"{}\" alt=\"{} 日线图\"></div>",
                    html_escape(&report_path),
                    html_escape(&row.code)
                )
            })
            .unwrap_or_else(|| "<div class=\"chart empty\">未找到 chart_path</div>".to_string());
        let raw_text = annotation
            .and_then(|item| item.raw_response_path.as_deref())
            .and_then(|path| read_raw_review_response(runtime_root, paths, path));
        let raw_html = raw_text
            .map(|text| format!("<pre class=\"raw\">{}</pre>", html_escape(&text)))
            .unwrap_or_else(|| "<div class=\"raw empty\">未提供原始子代理输出</div>".to_string());

        html.push_str(&format!(
            "<article class=\"card\"><div class=\"head\"><div class=\"title\">#{} {} {}</div><div class=\"signal {}\">{}</div></div>",
            html_escape(&rank),
            html_escape(&row.code),
            html_escape(name),
            signal_class,
            html_escape(signal)
        ));
        html.push_str(&format!(
            "<div class=\"kv\"><div><span class=\"label\">行业</span>{}</div><div><span class=\"label\">模型分</span>{}</div><div><span class=\"label\">动作</span>{}</div><div><span class=\"label\">置信度</span>{}</div></div>",
            html_escape(industry),
            html_escape(&score),
            html_escape(action),
            html_escape(&confidence)
        ));
        html.push_str(&format!(
            "<div class=\"flags\">{}</div><p class=\"comment\">{}</p>{}<h3>子代理原始输出</h3>{}</article>",
            flags,
            html_escape(comment),
            chart_html,
            raw_html
        ));
    }

    html.push_str("</section></main></body></html>\n");
    html
}

fn report_relative_runtime_path(path: &str) -> String {
    if path.starts_with('/') || path.starts_with("../") || path.starts_with("./") {
        path.to_string()
    } else {
        format!("../../{path}")
    }
}

fn read_raw_review_response(
    runtime_root: &Path,
    paths: &SelectionRunPaths,
    raw_response_path: &str,
) -> Option<String> {
    let path = Path::new(raw_response_path);
    if path.is_absolute() || raw_response_path.contains("..") {
        return Some(
            "raw_response_path 必须是 runtime 相对路径，且必须位于 llm_raw 目录。".to_string(),
        );
    }

    let normalized = raw_response_path.trim_start_matches("./");
    let run_dir_prefix = paths
        .run_dir
        .strip_prefix(runtime_root)
        .ok()
        .and_then(|path| path.to_str())
        .map(|path| path.replace('\\', "/"));
    let allowed = normalized.starts_with("llm_raw/")
        || run_dir_prefix
            .as_deref()
            .is_some_and(|prefix| normalized.starts_with(&format!("{prefix}/llm_raw/")));
    if !allowed {
        return Some(
            "raw_response_path 必须是 runtime 相对路径，且必须位于 llm_raw 目录。".to_string(),
        );
    }

    let candidates = [runtime_root.join(path), paths.run_dir.join(path)];
    candidates.into_iter().find_map(read_bounded_raw_response)
}

fn read_bounded_raw_response(path: PathBuf) -> Option<String> {
    let metadata = std::fs::metadata(&path).ok()?;
    if metadata.len() > MAX_RAW_REVIEW_REPORT_BYTES as u64 {
        return Some(format!(
            "原始子代理输出超过 {} KiB，HTML 报告不内嵌全文；请直接查看 raw_response_path 文件。",
            MAX_RAW_REVIEW_REPORT_BYTES / 1024
        ));
    }
    let mut file = File::open(path).ok()?;
    let mut content = String::new();
    file.read_to_string(&mut content).ok()?;
    Some(content)
}

fn html_escape(value: &str) -> String {
    let mut escaped = String::with_capacity(value.len());
    for ch in value.chars() {
        match ch {
            '&' => escaped.push_str("&amp;"),
            '<' => escaped.push_str("&lt;"),
            '>' => escaped.push_str("&gt;"),
            '"' => escaped.push_str("&quot;"),
            '\'' => escaped.push_str("&#39;"),
            _ => escaped.push(ch),
        }
    }
    escaped
}

fn resolve_artifact_command_paths(
    args: &ArtifactCommandArgs,
    command: &str,
) -> anyhow::Result<(PathBuf, SelectionRunPaths, String, NaiveDate)> {
    ensure_model_run_supported(args.method.method)?;
    let pick_date = resolve_pick_date(args.pick_date, args.method.intraday, command)?;
    let runtime_root = resolve_runtime_root(args.runtime_root.as_deref());
    let artifact_key = artifact_key_for_run(pick_date, args.method.intraday);
    let paths = SelectionRunPaths::new(&runtime_root, args.method.method, &artifact_key);
    Ok((runtime_root, paths, artifact_key, pick_date))
}

fn read_display_rows(paths: &SelectionRunPaths) -> anyhow::Result<Vec<DisplayRow>> {
    let payload = read_selection_json(&paths.display_path())?;
    Ok(serde_json::from_value(
        payload
            .get("rows")
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("display artifact missing rows"))?,
    )?)
}

fn read_annotations(paths: &SelectionRunPaths) -> anyhow::Result<Vec<LlmAnnotation>> {
    let payload = read_selection_json(&paths.llm_annotations_path())?;
    Ok(serde_json::from_value(
        payload
            .get("rows")
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("llm annotations artifact missing rows"))?,
    )?)
}

fn load_chart_histories(
    runtime_root: &std::path::Path,
    method: Method,
    pick_date: NaiveDate,
    intraday: bool,
) -> anyhow::Result<BTreeMap<String, Vec<PreparedRow>>> {
    let start_date = pick_date - chrono::Duration::days(366);
    let prepared = load_prepared_cache_for_mode(
        runtime_root,
        method,
        pick_date,
        start_date,
        pick_date,
        intraday,
    )?
    .ok_or_else(|| {
        anyhow::anyhow!(
            "prepared cache not found for chart; run screen first for {} {}",
            pick_date,
            method.as_str()
        )
    })?;
    let mut histories = BTreeMap::<String, Vec<PreparedRow>>::new();
    for row in prepared {
        histories.entry(row.ts_code.clone()).or_default().push(row);
    }
    for rows in histories.values_mut() {
        rows.sort_by_key(|row| row.trade_date);
    }
    Ok(histories)
}

fn run_review_list(args: ReviewListArgs) -> anyhow::Result<()> {
    run_review_list_with_name_loader(args, |dsn, codes| fetch_instrument_info(dsn, codes))
}

fn run_review_list_with_name_loader<F>(args: ReviewListArgs, name_loader: F) -> anyhow::Result<()>
where
    F: FnOnce(&str, &[String]) -> anyhow::Result<BTreeMap<String, InstrumentInfo>>,
{
    let method = args.method.method;
    let intraday = args.method.intraday;
    let runtime_root = resolve_runtime_root(args.runtime_root.as_deref());
    let dsn = resolve_config_value(args.dsn.as_deref(), "POSTGRES_DSN");

    // Resolve pick date early so we can check cache
    let pick_date = resolve_pick_date(args.pick_date, intraday, "review-list")?;
    let artifact_key = artifact_key_for_run(pick_date, intraday);
    let paths = SelectionRunPaths::new(&runtime_root, method, &artifact_key);
    let display_path = paths.display_path();

    // Try reading from cache first
    if display_path.exists() {
        let payload = read_selection_json(&display_path)?;
        let rows: Vec<DisplayRow> = serde_json::from_value(
            payload
                .get("rows")
                .cloned()
                .ok_or_else(|| anyhow::anyhow!("display artifact missing rows"))?,
        )?;
        let mut rows = limit_display_rows(rows, args.limit)?;
        fill_review_list_names(&mut rows, dsn.as_deref(), name_loader)?;
        for line in format_display_lines(&rows) {
            println!("{line}");
        }
        return Ok(());
    }

    // Model-first review: run screen + selection, then display
    let dsn_val = dsn.clone().unwrap_or_default();
    let candidates_path = {
        let request = ScreenRequest {
            method,
            pick_date,
            runtime_root: runtime_root.clone(),
            dsn: dsn_val.clone(),
            recompute: args.recompute,
            pool_source: if args.pool_file.is_some() {
                PoolSource::Custom
            } else {
                args.pool_source
            },
            pool_file: args.pool_file.clone(),
            export_factors: false,
            environment_state: None,
        };
        if intraday {
            let token = resolve_config_value(args.tushare_token.as_deref(), "TUSHARE_TOKEN")
                .ok_or_else(|| anyhow::anyhow!("A Tushare token is required for intraday mode."))?;
            let provider = TushareRestProvider::new(token)?;
            run_intraday_screen_with_loaders(
                request,
                &provider,
                "15:00:00",
                resolve_previous_trade_date,
                fetch_daily_window_if_dsn,
            )?
        } else {
            run_screen_with_loader(request, fetch_daily_window_if_dsn)?
        }
    };

    let environment = resolve_command_environment(
        &runtime_root,
        pick_date,
        intraday,
        &dsn_val,
        args.environment_state.clone(),
        args.environment_reason.clone(),
    )?;
    let record_config = if intraday {
        None
    } else {
        RunRecordConfig::for_run(method, args.record, args.record_window_trading_days)?
    };

    run_selection(SelectionRunRequest {
        method,
        pick_date,
        runtime_root: runtime_root.clone(),
        intraday,
        candidates_path,
        model_path: args.model_path.clone(),
        model_feature_metadata_path: args.model_feature_metadata_path.clone(),
        environment: Some(environment),
        record: record_config.is_some(),
        record_window_trading_days: record_config
            .as_ref()
            .map(|config| config.window_trading_days),
        record_limit: record_config.as_ref().map(|config| config.record_limit),
    })?;
    maybe_update_run_record(
        &runtime_root,
        &paths,
        method,
        pick_date,
        intraday,
        record_config.as_ref(),
    )?;

    // Read and display results from the now-existing artifact
    let payload = read_selection_json(&display_path)?;
    let rows: Vec<DisplayRow> = serde_json::from_value(
        payload
            .get("rows")
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("display artifact missing rows"))?,
    )?;
    let mut rows = limit_display_rows(rows, args.limit)?;
    fill_review_list_names(&mut rows, dsn.as_deref(), name_loader)?;
    for line in format_display_lines(&rows) {
        println!("{line}");
    }
    Ok(())
}

fn fill_review_list_names<F>(
    rows: &mut [DisplayRow],
    dsn: Option<&str>,
    name_loader: F,
) -> anyhow::Result<()>
where
    F: FnOnce(&str, &[String]) -> anyhow::Result<BTreeMap<String, InstrumentInfo>>,
{
    let Some(dsn) = dsn.filter(|value| !value.trim().is_empty()) else {
        return Ok(());
    };
    let codes = rows
        .iter()
        .filter(|row| {
            row.name
                .as_deref()
                .map(str::trim)
                .filter(|name| !name.is_empty())
                .is_none()
        })
        .map(|row| row.code.clone())
        .collect::<Vec<_>>();
    let instruments = name_loader(dsn, &codes)?;
    fill_missing_display_instrument_info(rows, &instruments);
    Ok(())
}

fn fetch_daily_window_if_dsn(
    dsn: &str,
    start_date: NaiveDate,
    end_date: NaiveDate,
) -> anyhow::Result<Vec<MarketRow>> {
    if dsn.trim().is_empty() {
        anyhow::bail!("A database DSN is required.");
    }
    fetch_daily_window(dsn, start_date, end_date)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn review_list_loads_instrument_info_for_missing_display_rows_only() {
        let temp = tempfile::tempdir().unwrap();
        let display_dir = temp.path().join("select/2026-05-25.b2");
        std::fs::create_dir_all(&display_dir).unwrap();
        std::fs::write(
            display_dir.join("display.json"),
            serde_json::to_vec_pretty(&json!({
                "rows": [
                    {"code": "000001.SZ", "name": null, "model_rank": 1, "model_score": 0.7, "llm_action": null, "llm_risk_flags": []},
                    {"code": "000002.SZ", "name": "已有名称", "industry": "已有行业", "model_rank": 2, "model_score": 0.6, "llm_action": null, "llm_risk_flags": []},
                    {"code": "000003.SZ", "name": "", "model_rank": 3, "model_score": 0.5, "llm_action": null, "llm_risk_flags": []}
                ]
            }))
            .unwrap(),
        )
        .unwrap();

        let args = ReviewListArgs {
            method: MethodArgs {
                method: Method::B2,
                intraday: false,
            },
            limit: Some(2),
            runtime_root: Some(temp.path().to_path_buf()),
            dsn: Some("postgres://example".to_string()),
            pick_date: Some(NaiveDate::from_ymd_opt(2026, 5, 25).unwrap()),
            tushare_token: None,
            recompute: false,
            pool_file: None,
            pool_source: PoolSource::TurnoverTop,
            model_path: None,
            model_feature_metadata_path: None,
            environment_state: None,
            environment_reason: None,
            record: false,
            record_window_trading_days: None,
        };

        run_review_list_with_name_loader(args, |dsn, codes| {
            assert_eq!(dsn, "postgres://example");
            assert_eq!(codes, &["000001.SZ".to_string()]);
            Ok(BTreeMap::from([(
                "000001.SZ".to_string(),
                InstrumentInfo {
                    name: Some("平安银行".to_string()),
                    industry: Some("银行".to_string()),
                },
            )]))
        })
        .unwrap();
    }

    #[test]
    fn review_list_name_fill_skips_blank_resolved_dsn() {
        let mut rows = vec![DisplayRow {
            code: "000001.SZ".to_string(),
            name: None,
            industry: None,
            model_rank: Some(1),
            model_score: Some(0.7),
            llm_action: None,
            llm_risk_flags: Vec::new(),
            llm_comment: None,
        }];

        fill_review_list_names(&mut rows, Some("   "), |_dsn, _codes| {
            panic!("blank DSN must not trigger instrument name loading")
        })
        .unwrap();
    }
}
