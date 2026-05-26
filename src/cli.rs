use std::path::PathBuf;
use std::time::Instant;

use anyhow::Context;
use chrono::NaiveDate;
use clap::{Parser, Subcommand};

use crate::cache::{load_prepared_cache, write_prepared_cache};
use crate::config::{default_runtime_root, resolve_dsn_from_env, screen_window};
use crate::model::{MarketRow, Method, PreparedRow};
use crate::native_chart::{NativeChartArgs, run_native_chart};
use crate::native_review::{NativeReviewArgs, run_native_review};
use crate::output::{build_screen_result, write_screen_result};
use crate::prepare::prepare_rows;
use crate::python_bridge::{PythonBridge, PythonStage, PythonStageArgs};
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
    #[arg(long)]
    native: bool,
}

#[derive(Debug, Parser)]
pub struct RunArgs {
    #[command(flatten)]
    review: ReviewArgs,
    #[arg(long)]
    recompute: bool,
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
    if args.native {
        let runtime_root = args
            .runtime_root
            .clone()
            .unwrap_or_else(default_runtime_root);
        return run_native_review(NativeReviewArgs {
            method: args.method,
            pick_date: args.pick_date,
            runtime_root,
            environment_state: args.environment_state.clone(),
            environment_reason: args.environment_reason.clone(),
            llm_min_baseline_score: args.llm_min_baseline_score,
            llm_review_limit: args.llm_review_limit,
        });
    }
    let bridge = PythonBridge::default_project();
    run_review_with(args, |stage, stage_args| {
        bridge.run_stage(stage, stage_args)
    })
}

pub fn run_review_with<F>(args: ReviewArgs, mut runner: F) -> anyhow::Result<PathBuf>
where
    F: FnMut(PythonStage, PythonStageArgs<'_>) -> anyhow::Result<()>,
{
    let started = Instant::now();
    let runtime_root = args.runtime_root.unwrap_or_else(default_runtime_root);
    runner(
        PythonStage::Review,
        PythonStageArgs {
            method: args.method,
            pick_date: args.pick_date,
            dsn: args.dsn.as_deref(),
            runtime_root: &runtime_root,
            environment_state: args.environment_state.as_deref(),
            environment_reason: args.environment_reason.as_deref(),
            llm_min_baseline_score: args.llm_min_baseline_score,
            llm_review_limit: args.llm_review_limit,
        },
    )?;
    let output_path = runtime_root
        .join("reviews")
        .join(format!(
            "{}.{}",
            args.pick_date.format("%Y-%m-%d"),
            args.method.as_str()
        ))
        .join("summary.json");
    eprintln!(
        "[review] total elapsed={:.3}s",
        started.elapsed().as_secs_f64()
    );
    Ok(output_path)
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

    let screen_started = Instant::now();
    let screen_path = run_screen(
        ScreenArgs {
            method,
            pick_date,
            dsn: args.review.dsn.clone(),
            runtime_root: Some(runtime_root.clone()),
            recompute: args.recompute,
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
    if method == Method::B1 {
        run_native_review(NativeReviewArgs {
            method,
            pick_date,
            runtime_root: runtime_root.clone(),
            environment_state: args.review.environment_state.clone(),
            environment_reason: args.review.environment_reason.clone(),
            llm_min_baseline_score: args.review.llm_min_baseline_score,
            llm_review_limit: args.review.llm_review_limit,
        })?;
    } else {
        let bridge = PythonBridge::default_project();
        bridge.run_stage(
            PythonStage::Review,
            PythonStageArgs {
                method,
                pick_date,
                dsn: args.review.dsn.as_deref(),
                runtime_root: &runtime_root,
                environment_state: args.review.environment_state.as_deref(),
                environment_reason: args.review.environment_reason.as_deref(),
                llm_min_baseline_score: args.review.llm_min_baseline_score,
                llm_review_limit: args.review.llm_review_limit,
            },
        )?;
    }
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
    let prepared_for_pick = filter_turnover_top_pool(&prepared, args.pick_date, 5000);
    eprintln!(
        "[screen] pool_source=turnover-top pool_size={} elapsed={:.3}s",
        unique_symbol_count(&prepared_for_pick),
        pool_started.elapsed().as_secs_f64()
    );

    let strategy_started = Instant::now();
    let strategy = run_strategy(args.method, &prepared_for_pick, args.pick_date);
    eprintln!(
        "[screen] strategy method={} candidates={} elapsed={:.3}s",
        args.method.as_str(),
        strategy.candidates.len(),
        strategy_started.elapsed().as_secs_f64()
    );
    let result = build_screen_result(
        args.method,
        args.pick_date,
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

    #[test]
    fn review_orchestration_forwards_environment_and_baseline_filters_to_runner() {
        let temp = tempfile::tempdir().unwrap();
        let pick = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
        let args = ReviewArgs {
            method: Method::B1,
            pick_date: pick,
            dsn: Some("postgresql://example".to_string()),
            runtime_root: Some(temp.path().to_path_buf()),
            environment_state: Some("weak".to_string()),
            environment_reason: Some("SSE neutral; CN2000 neutral; 双指数共振偏弱".to_string()),
            llm_min_baseline_score: Some(4.25),
            llm_review_limit: Some(3),
            native: false,
        };
        let mut calls = Vec::new();
        let path = run_review_with(args, |stage, stage_args| {
            calls.push((
                stage,
                stage_args.method,
                stage_args.pick_date,
                stage_args.dsn.map(str::to_string),
                stage_args.runtime_root.to_path_buf(),
                stage_args.environment_state.map(str::to_string),
                stage_args.environment_reason.map(str::to_string),
                stage_args.llm_min_baseline_score,
                stage_args.llm_review_limit,
            ));
            Ok(())
        })
        .unwrap();

        assert_eq!(path, temp.path().join("reviews/2026-05-25.b1/summary.json"));
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0].0, PythonStage::Review);
        assert_eq!(calls[0].1, Method::B1);
        assert_eq!(calls[0].2, pick);
        assert_eq!(calls[0].3.as_deref(), Some("postgresql://example"));
        assert_eq!(calls[0].4, temp.path());
        assert_eq!(calls[0].5.as_deref(), Some("weak"));
        assert_eq!(
            calls[0].6.as_deref(),
            Some("SSE neutral; CN2000 neutral; 双指数共振偏弱")
        );
        assert_eq!(calls[0].7, Some(4.25));
        assert_eq!(calls[0].8, Some(3));
    }
}
