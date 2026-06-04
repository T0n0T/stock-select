use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};

use anyhow::Context;
use chrono::{Local, NaiveDate};
use clap::{Args, CommandFactory, Parser, Subcommand};
use clap_complete::{Shell, generate};
use serde::Serialize;
use serde_json::json;
use stock_select::cache::load_prepared_cache_for_mode;
use stock_select::config::{resolve_config_value, resolve_runtime_root};
use stock_select::db::{
    fetch_daily_window, fetch_index_history, fetch_instrument_info, resolve_previous_trade_date,
};
use stock_select::engine::artifacts::{
    SelectionRunPaths, read_selection_json, write_selection_json,
};
use stock_select::engine::b2::artifact_key_for_run;
use stock_select::engine::capability::ensure_model_run_supported;
use stock_select::engine::presentation::{
    fill_missing_display_instrument_info, format_display_lines, limit_display_rows,
};
use stock_select::engine::run::{SelectionRunRequest, run_selection};
use stock_select::engine::types::{DisplayRow, LlmAnnotation};
use stock_select::environment::{
    ResolvedEnvironment, ensure_market_environment, evaluate_market_environment,
    resolve_intraday_market_environment,
};
use stock_select::intraday::TushareRestProvider;
use stock_select::model::{InstrumentInfo, MarketRow, Method, PreparedRow};
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
}

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
    let result = run_selection(SelectionRunRequest {
        method: args.method.method,
        pick_date,
        runtime_root: runtime_root.clone(),
        intraday: args.method.intraday,
        candidates_path,
        model_path: args.model_path.clone(),
        model_feature_metadata_path: args.model_feature_metadata_path.clone(),
        environment: Some(environment.clone()),
        record: args.record,
        record_window_trading_days: args.record_window_trading_days,
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
                record: args.record,
                record_window_trading_days: args.record_window_trading_days,
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
                record: args.record,
                record_window_trading_days: args.record_window_trading_days,
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

    let resolved =
        ensure_market_environment(runtime_root, pick_date, manual_state, manual_reason, || {
            if dsn.trim().is_empty() {
                anyhow::bail!("A database DSN is required for market environment evaluation.");
            }
            let start_date = pick_date - chrono::Duration::days(180);
            let sse = fetch_index_history(dsn, "000001.SH", start_date, pick_date)
                .context("fetch SSE index history for market environment")?;
            let cn2000 = fetch_index_history(dsn, "399303.SZ", start_date, pick_date)
                .context("fetch CN2000 index history for market environment")?;
            evaluate_market_environment(pick_date, &sse, &cn2000)
        })?;
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
    Ok(())
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
            json!({
                "code": row.code,
                "name": row.name,
                "industry": row.industry,
                "model_rank": row.model_rank,
                "model_score": row.model_score,
                "chart_path": deterministic_chart_path(method, artifact_key, &row.code),
                "llm_instruction": "Annotate risk only; do not change model_rank.",
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

    if let Some(pick_date) = args.pick_date {
        let artifact_key = artifact_key_for_run(pick_date, intraday);
        let paths = SelectionRunPaths::new(&runtime_root, method, &artifact_key);
        let display_path = paths.display_path();
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
    }

    limit_display_rows(Vec::new(), args.limit)?;
    print_stub("review-list", args.method)
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

fn print_stub(command: &str, args: MethodArgs) -> anyhow::Result<()> {
    let intraday = if args.intraday { " intraday" } else { "" };
    println!(
        "{command} {method}{intraday}: model-first review is not implemented yet",
        method = args.method
    );
    Ok(())
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
        }];

        fill_review_list_names(&mut rows, Some("   "), |_dsn, _codes| {
            panic!("blank DSN must not trigger instrument name loading")
        })
        .unwrap();
    }
}
