use std::fs;
use std::fs::{File, OpenOptions};
use std::io::ErrorKind;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration as StdDuration, Instant};

use anyhow::Context;
use chrono::{Duration, NaiveDate};
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::engine::artifacts::write_selection_json;
use crate::model::MarketRow;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EnvironmentEvaluation {
    pub state: String,
    pub score_based_state: String,
    pub rule_based_state: String,
    pub vote_based_state: String,
    pub evaluate_date: NaiveDate,
    pub source: String,
    pub reason: String,
    pub total_score: f64,
    pub score_based_total: f64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EnvironmentRecord {
    pub pick_date: NaiveDate,
    pub state: String,
    pub score_based_state: String,
    pub rule_based_state: String,
    pub vote_based_state: String,
    pub evaluate_date: NaiveDate,
    pub source: String,
    pub reason: String,
    pub total_score: f64,
    pub score_based_total: f64,
    pub manual_override: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ResolvedEnvironment {
    pub state: String,
    pub interval_start: Option<NaiveDate>,
    pub interval_end: Option<NaiveDate>,
    pub reason: Option<String>,
    pub source: String,
}

pub fn ensure_market_environment<F>(
    runtime_root: &Path,
    pick_date: NaiveDate,
    manual_state: Option<String>,
    manual_reason: Option<String>,
    evaluator: F,
) -> anyhow::Result<ResolvedEnvironment>
where
    F: FnOnce() -> anyhow::Result<EnvironmentEvaluation>,
{
    if let Some(state) = manual_state {
        let normalized = normalize_environment_state(&state)?;
        let record = EnvironmentRecord {
            pick_date,
            state: normalized.clone(),
            score_based_state: normalized.clone(),
            rule_based_state: normalized.clone(),
            vote_based_state: normalized,
            evaluate_date: pick_date,
            source: "manual_override".to_string(),
            reason: manual_reason.unwrap_or_default(),
            total_score: 0.0,
            score_based_total: 0.0,
            manual_override: true,
        };
        upsert_environment_record(runtime_root, record)?;
        return resolve_market_environment(runtime_root, pick_date);
    }

    let evaluation = match evaluator() {
        Ok(evaluation) => evaluation,
        Err(err) => {
            if let Ok(resolved) = resolve_market_environment(runtime_root, pick_date) {
                eprintln!(
                    "[environment] evaluation failed for {pick_date}, using persisted state={} source={}",
                    resolved.state, resolved.source
                );
                eprintln!("[environment] evaluation error: {err:#}");
                return Ok(resolved);
            }
            return Err(err);
        }
    };
    let record = EnvironmentRecord {
        pick_date,
        state: normalize_environment_state(&evaluation.state)?,
        score_based_state: normalize_environment_state(&evaluation.score_based_state)?,
        rule_based_state: normalize_environment_state(&evaluation.rule_based_state)?,
        vote_based_state: normalize_environment_state(&evaluation.vote_based_state)?,
        evaluate_date: evaluation.evaluate_date,
        source: evaluation.source,
        reason: evaluation.reason,
        total_score: evaluation.total_score,
        score_based_total: evaluation.score_based_total,
        manual_override: false,
    };
    upsert_environment_record(runtime_root, record)?;
    resolve_market_environment(runtime_root, pick_date)
}

pub fn resolve_intraday_market_environment(
    runtime_root: &Path,
    pick_date: NaiveDate,
    manual_state: Option<String>,
    manual_reason: Option<String>,
    previous_trade_date: Option<NaiveDate>,
) -> anyhow::Result<ResolvedEnvironment> {
    if let Some(state) = manual_state {
        let state = normalize_environment_state(&state)?;
        eprintln!("[environment] intraday state={state} source=manual_override");
        return Ok(ResolvedEnvironment {
            state,
            interval_start: None,
            interval_end: None,
            reason: manual_reason,
            source: "manual_override".to_string(),
        });
    }
    let lookup_date = previous_trade_date.unwrap_or_else(|| pick_date - Duration::days(1));
    let resolved = resolve_market_environment(runtime_root, lookup_date).with_context(|| {
        format!(
            "intraday requires --environment-state or a persisted previous trade day environment for {lookup_date}"
        )
    })?;
    eprintln!(
        "[environment] intraday state={} source={} fallback_date={} hint=use --environment-state to override",
        resolved.state, resolved.source, lookup_date
    );
    Ok(resolved)
}

pub fn resolve_market_environment(
    runtime_root: &Path,
    pick_date: NaiveDate,
) -> anyhow::Result<ResolvedEnvironment> {
    let records = load_environment_records(runtime_root)?;
    let intervals = build_intervals(&records);
    intervals
        .into_iter()
        .filter(|interval| {
            interval.start <= pick_date && interval.end.is_none_or(|end| pick_date <= end)
        })
        .max_by_key(|interval| {
            (
                interval.manual_override,
                interval.start,
                interval.evaluated_at,
            )
        })
        .map(|interval| ResolvedEnvironment {
            state: interval.state,
            interval_start: Some(interval.start),
            interval_end: interval.end,
            reason: Some(interval.reason).filter(|reason| !reason.is_empty()),
            source: interval.source,
        })
        .ok_or_else(|| {
            anyhow::anyhow!("No market environment interval covers pick_date {pick_date}.")
        })
}

pub fn ensure_market_environment_for_test<F>(
    runtime_root: &Path,
    pick_date: NaiveDate,
    manual_state: Option<String>,
    manual_reason: Option<String>,
    evaluator: F,
) -> anyhow::Result<ResolvedEnvironment>
where
    F: FnOnce() -> anyhow::Result<EnvironmentEvaluation>,
{
    ensure_market_environment(
        runtime_root,
        pick_date,
        manual_state,
        manual_reason,
        evaluator,
    )
}

pub fn resolve_market_environment_for_test(
    runtime_root: &Path,
    pick_date: NaiveDate,
) -> anyhow::Result<ResolvedEnvironment> {
    resolve_market_environment(runtime_root, pick_date)
}

pub fn resolve_intraday_market_environment_for_test(
    runtime_root: &Path,
    pick_date: NaiveDate,
    manual_state: Option<String>,
    manual_reason: Option<String>,
    previous_trade_date: Option<NaiveDate>,
) -> anyhow::Result<ResolvedEnvironment> {
    resolve_intraday_market_environment(
        runtime_root,
        pick_date,
        manual_state,
        manual_reason,
        previous_trade_date,
    )
}

pub fn evaluate_market_environment(
    pick_date: NaiveDate,
    sse_history: &[MarketRow],
    cn2000_history: &[MarketRow],
) -> anyhow::Result<EnvironmentEvaluation> {
    let sse = score_index_environment(pick_date, sse_history, "SSE")?;
    let cn2000 = score_index_environment(pick_date, cn2000_history, "CN2000")?;
    let total_score = round2(sse.total_score + cn2000.total_score);
    let score_based_state = score_based_state(total_score);
    let rule_based_state = rule_based_state(&sse.state_hint, &cn2000.state_hint);
    let vote_based_state = vote_based_state(&[sse.state_hint.as_str(), cn2000.state_hint.as_str()]);
    let state = score_based_state.to_string();
    let reason = match state.as_str() {
        "strong" => format!(
            "SSE {}; CN2000 {}; 双指数共振偏强",
            sse.state_hint, cn2000.state_hint
        ),
        "weak" => format!(
            "SSE {}; CN2000 {}; 双指数共振偏弱",
            sse.state_hint, cn2000.state_hint
        ),
        _ => format!(
            "SSE {}; CN2000 {}; 修复或分化，环境中立",
            sse.state_hint, cn2000.state_hint
        ),
    };
    Ok(EnvironmentEvaluation {
        state,
        score_based_state: score_based_state.to_string(),
        rule_based_state,
        vote_based_state,
        evaluate_date: pick_date,
        source: "scheduled".to_string(),
        reason,
        total_score,
        score_based_total: total_score,
    })
}

#[derive(Debug, Clone, PartialEq)]
struct IndexEnvironmentScore {
    total_score: f64,
    state_hint: String,
}

fn score_index_environment(
    pick_date: NaiveDate,
    history: &[MarketRow],
    label: &str,
) -> anyhow::Result<IndexEnvironmentScore> {
    let rows = history
        .iter()
        .filter(|row| row.trade_date <= pick_date && row.close.is_finite())
        .cloned()
        .collect::<Vec<_>>();
    if rows.len() < 60 || rows.last().is_none_or(|row| row.trade_date != pick_date) {
        anyhow::bail!("Insufficient {label} history for market environment evaluation.");
    }
    let close = rows.iter().map(|row| row.close).collect::<Vec<_>>();
    let ma25 = mean_tail(&close, 25);
    let ma60 = mean_tail(&close, 60);
    let latest = *close.last().unwrap_or(&f64::NAN);
    let ma25_prev = mean_range(&close, close.len() - 26, close.len() - 1);
    let ma60_prev = mean_range(&close, close.len() - 61, close.len() - 1);
    let (dif, dea, hist) = macd(&close, 12, 26, 9);
    let latest_hist = *hist.last().unwrap_or(&0.0);
    let prev_hist = hist
        .get(hist.len().saturating_sub(2))
        .copied()
        .unwrap_or(latest_hist);
    let latest_dea = *dea.last().unwrap_or(&0.0);
    let prev_dea = dea
        .get(dea.len().saturating_sub(2))
        .copied()
        .unwrap_or(latest_dea);
    let latest_dif = *dif.last().unwrap_or(&0.0);

    let trend_score = if latest >= ma25 && ma25 >= ma60 && ma25 >= ma25_prev && ma60 >= ma60_prev {
        4.0
    } else if latest >= ma25 && ma25 >= ma25_prev {
        2.0
    } else if latest < ma60 && ma25 < ma25_prev && ma60 < ma60_prev {
        -5.0
    } else if latest < ma25 && ma25 < ma25_prev {
        -3.0
    } else {
        0.0
    };
    let macd_score = if latest_dea < 0.0 && latest_dea > prev_dea && latest_hist > 0.0 {
        4.0
    } else if latest_dea > 0.0 && latest_dea > prev_dea && latest_hist > 0.0 {
        4.5
    } else if latest_dea > 0.0 && latest_hist < 0.0 {
        -3.0
    } else if latest_hist < 0.0 && latest_hist < prev_hist {
        -2.5
    } else {
        0.0
    };
    let box_score = if latest >= max_tail(&close, 60) * 0.98 {
        1.0
    } else if latest <= min_tail(&close, 60) * 1.05 {
        -1.0
    } else {
        0.0
    };
    let total_score = round3(trend_score + macd_score + box_score);
    let state_hint = if macd_score >= 4.0 && trend_score >= 2.0 {
        "strong"
    } else if (macd_score <= -2.5 && trend_score <= -2.0)
        || latest_dif < latest_dea && trend_score < 0.0
    {
        "weak"
    } else {
        "neutral"
    }
    .to_string();
    Ok(IndexEnvironmentScore {
        total_score,
        state_hint,
    })
}

fn upsert_environment_record(runtime_root: &Path, record: EnvironmentRecord) -> anyhow::Result<()> {
    let _lock = EnvironmentLock::acquire(runtime_root)?;
    let mut records = load_environment_records(runtime_root).unwrap_or_default();
    records.retain(|item| item.pick_date != record.pick_date);
    records.push(record);
    records.sort_by_key(|item| item.pick_date);
    write_environment_records(runtime_root, &records)
}

struct EnvironmentLock {
    path: PathBuf,
    _file: File,
}

impl EnvironmentLock {
    fn acquire(runtime_root: &Path) -> anyhow::Result<Self> {
        fs::create_dir_all(environment_dir(runtime_root))?;
        let path = environment_dir(runtime_root).join(".environment.lock");
        let started = Instant::now();
        loop {
            match OpenOptions::new().write(true).create_new(true).open(&path) {
                Ok(file) => return Ok(Self { path, _file: file }),
                Err(err) if err.kind() == ErrorKind::AlreadyExists => {
                    if started.elapsed() > StdDuration::from_secs(30) {
                        anyhow::bail!("Timed out waiting for environment lock: {}", path.display());
                    }
                    thread::sleep(StdDuration::from_millis(50));
                }
                Err(err) => {
                    return Err(err)
                        .with_context(|| format!("create environment lock {}", path.display()));
                }
            }
        }
    }
}

impl Drop for EnvironmentLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

fn load_environment_records(runtime_root: &Path) -> anyhow::Result<Vec<EnvironmentRecord>> {
    let path = history_jsonl_path(runtime_root);
    if !path.exists() {
        return Ok(Vec::new());
    }
    fs::read_to_string(&path)
        .with_context(|| format!("read environment history {}", path.display()))?
        .lines()
        .filter(|line| !line.trim().is_empty())
        .map(|line| Ok(serde_json::from_str::<EnvironmentRecord>(line)?))
        .collect()
}

fn write_environment_records(
    runtime_root: &Path,
    records: &[EnvironmentRecord],
) -> anyhow::Result<()> {
    fs::create_dir_all(environment_dir(runtime_root))?;
    fs::create_dir_all(daily_dir(runtime_root))?;
    for entry in fs::read_dir(daily_dir(runtime_root))? {
        let path = entry?.path();
        if path.extension().and_then(|value| value.to_str()) == Some("json") {
            fs::remove_file(path)?;
        }
    }
    let history = records
        .iter()
        .map(|record| serde_json::to_string(record).expect("environment record serializes"))
        .collect::<Vec<_>>()
        .join("\n")
        + if records.is_empty() { "" } else { "\n" };
    fs::write(history_jsonl_path(runtime_root), history)?;
    for record in records {
        write_selection_json(
            &daily_dir(runtime_root).join(format!(
                "{}.{}.json",
                record.pick_date.format("%Y-%m-%d"),
                record.state
            )),
            record,
        )?;
    }
    let daily = records
        .iter()
        .map(|record| json!({"pick_date": record.pick_date, "state": record.state, "source": record.source, "reason": record.reason}))
        .collect::<Vec<_>>();
    let intervals = build_intervals(records)
        .into_iter()
        .map(|interval| json!({"state": interval.state, "start_date": interval.start, "end_date": interval.end, "evaluated_at": interval.evaluated_at, "source": interval.source, "manual_override": interval.manual_override, "reason": interval.reason}))
        .collect::<Vec<_>>();
    write_selection_json(
        &latest_snapshot_path(runtime_root),
        &json!({"daily": daily, "intervals": intervals}),
    )?;
    Ok(())
}

#[derive(Debug, Clone)]
struct EnvironmentInterval {
    state: String,
    start: NaiveDate,
    end: Option<NaiveDate>,
    evaluated_at: NaiveDate,
    source: String,
    manual_override: bool,
    reason: String,
}

fn build_intervals(records: &[EnvironmentRecord]) -> Vec<EnvironmentInterval> {
    let mut intervals: Vec<EnvironmentInterval> = Vec::new();
    for record in records {
        if let Some(last) = intervals.last_mut() {
            if last.state == record.state && last.manual_override == record.manual_override {
                last.end = Some(record.pick_date);
                last.evaluated_at = record.evaluate_date;
                last.source = record.source.clone();
                last.reason = record.reason.clone();
                continue;
            }
            last.end = Some(record.pick_date - Duration::days(1));
        }
        intervals.push(EnvironmentInterval {
            state: record.state.clone(),
            start: record.pick_date,
            end: None,
            evaluated_at: record.evaluate_date,
            source: record.source.clone(),
            manual_override: record.manual_override,
            reason: record.reason.clone(),
        });
    }
    intervals
}

fn normalize_environment_state(value: &str) -> anyhow::Result<String> {
    let normalized = value.trim().to_ascii_lowercase();
    if matches!(normalized.as_str(), "weak" | "neutral" | "strong") {
        Ok(normalized)
    } else {
        anyhow::bail!("Unsupported environment state '{value}', expected weak, neutral, or strong")
    }
}

fn score_based_state(total_score: f64) -> &'static str {
    if total_score >= 10.0 {
        "strong"
    } else if total_score <= -4.0 {
        "weak"
    } else {
        "neutral"
    }
}

fn rule_based_state(sse: &str, cn2000: &str) -> String {
    if (sse == "strong" || cn2000 == "strong") && sse != "weak" && cn2000 != "weak" {
        "strong".to_string()
    } else if (sse == "weak" && cn2000 != "strong") || (cn2000 == "weak" && sse != "strong") {
        "weak".to_string()
    } else {
        "neutral".to_string()
    }
}

fn vote_based_state(states: &[&str]) -> String {
    let strong = states.iter().filter(|state| **state == "strong").count();
    let weak = states.iter().filter(|state| **state == "weak").count();
    if strong > weak && strong > 0 {
        "strong".to_string()
    } else if weak > strong && weak > 0 {
        "weak".to_string()
    } else {
        "neutral".to_string()
    }
}

fn mean_tail(values: &[f64], len: usize) -> f64 {
    mean_range(values, values.len().saturating_sub(len), values.len())
}

fn mean_range(values: &[f64], start: usize, end: usize) -> f64 {
    let slice = &values[start.min(values.len())..end.min(values.len())];
    let mut total = 0.0;
    let mut count = 0.0;
    for value in slice.iter().copied().filter(|value| value.is_finite()) {
        total += value;
        count += 1.0;
    }
    if count == 0.0 {
        f64::NAN
    } else {
        total / count
    }
}

fn max_tail(values: &[f64], len: usize) -> f64 {
    values
        .iter()
        .rev()
        .take(len)
        .copied()
        .filter(|value| value.is_finite())
        .fold(f64::NEG_INFINITY, f64::max)
}

fn min_tail(values: &[f64], len: usize) -> f64 {
    values
        .iter()
        .rev()
        .take(len)
        .copied()
        .filter(|value| value.is_finite())
        .fold(f64::INFINITY, f64::min)
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

fn ema(values: &[f64], span: usize) -> Vec<f64> {
    assert!(span > 0, "span must be positive");
    if values.is_empty() {
        return Vec::new();
    }
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

fn round2(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}

fn round3(value: f64) -> f64 {
    (value * 1000.0).round() / 1000.0
}

fn environment_dir(runtime_root: &Path) -> PathBuf {
    runtime_root.join("environment")
}

fn daily_dir(runtime_root: &Path) -> PathBuf {
    environment_dir(runtime_root).join("daily")
}

fn history_jsonl_path(runtime_root: &Path) -> PathBuf {
    environment_dir(runtime_root).join("history.jsonl")
}

fn latest_snapshot_path(runtime_root: &Path) -> PathBuf {
    environment_dir(runtime_root).join("latest.json")
}
