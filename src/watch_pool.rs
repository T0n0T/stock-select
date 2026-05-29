use std::collections::BTreeMap;
use std::fs;
use std::fs::OpenOptions;
use std::io::ErrorKind;
use std::path::{Path, PathBuf};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::Context;
use chrono::NaiveDate;
use serde_json::Value;

use crate::model::Method;

const WATCH_POOL_HEADER: &str =
    "method,pick_date,code,verdict,total_score,signal_type,comment,recorded_at";

#[derive(Debug, Clone, PartialEq)]
pub struct WatchPoolRow {
    pub method: String,
    pub pick_date: NaiveDate,
    pub code: String,
    pub verdict: String,
    pub total_score: f64,
    pub signal_type: String,
    pub comment: String,
    pub recorded_at: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RecordWatchArgs {
    pub method: Method,
    pub pick_date: NaiveDate,
    pub runtime_root: PathBuf,
    pub summary_path: PathBuf,
    pub trade_dates: Vec<NaiveDate>,
    pub window_trading_days: usize,
    pub recorded_at: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RecordWatchResult {
    pub path: PathBuf,
    pub imported: usize,
    pub refreshed: usize,
    pub trimmed: usize,
    pub cutoff_trade_date: NaiveDate,
}

pub fn record_watch_from_summary(args: RecordWatchArgs) -> anyhow::Result<RecordWatchResult> {
    if args.window_trading_days == 0 {
        anyhow::bail!("--record-window-trading-days must be positive");
    }
    let cutoff_trade_date =
        cutoff_trade_date(&args.trade_dates, args.pick_date, args.window_trading_days)?;
    let summary: Value = serde_json::from_slice(
        &fs::read(&args.summary_path)
            .with_context(|| format!("read review summary {}", args.summary_path.display()))?,
    )
    .with_context(|| format!("parse review summary {}", args.summary_path.display()))?;
    let incoming = summary_to_watch_rows(
        &summary,
        args.method,
        args.pick_date,
        args.recorded_at.as_str(),
    )?;
    let path = watch_pool_path(&args.runtime_root);
    let _lock = WatchPoolLock::acquire(&path)?;
    let mut rows = load_watch_pool(&path)?;
    let before_merge_count = rows.len();
    let mut by_key: BTreeMap<(String, String), WatchPoolRow> = rows
        .drain(..)
        .map(|row| ((row.method.clone(), row.code.clone()), row))
        .collect();
    let mut refreshed = 0;
    for row in incoming.iter().cloned() {
        if by_key
            .insert((row.method.clone(), row.code.clone()), row)
            .is_some()
        {
            refreshed += 1;
        }
    }
    let before_trim_count = by_key.len();
    let mut merged = by_key
        .into_values()
        .filter(|row| row.pick_date >= cutoff_trade_date)
        .collect::<Vec<_>>();
    let trimmed = before_trim_count.saturating_sub(merged.len());
    sort_watch_rows(&mut merged);
    write_watch_pool(&path, &merged)?;
    Ok(RecordWatchResult {
        path,
        imported: incoming.len(),
        refreshed: refreshed.min(before_merge_count),
        trimmed,
        cutoff_trade_date,
    })
}

struct WatchPoolLock {
    path: PathBuf,
}

impl WatchPoolLock {
    fn acquire(csv_path: &Path) -> anyhow::Result<Self> {
        if let Some(parent) = csv_path.parent() {
            fs::create_dir_all(parent)?;
        }
        let lock_path = csv_path.with_extension("csv.lock");
        let started = Instant::now();
        loop {
            match OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&lock_path)
            {
                Ok(_) => return Ok(Self { path: lock_path }),
                Err(err) if err.kind() == ErrorKind::AlreadyExists => {
                    if started.elapsed() > Duration::from_secs(30) {
                        anyhow::bail!(
                            "Timed out waiting for watch pool lock: {}",
                            lock_path.display()
                        );
                    }
                    thread::sleep(Duration::from_millis(50));
                }
                Err(err) => {
                    return Err(err).with_context(|| {
                        format!("create watch pool lock {}", lock_path.display())
                    });
                }
            }
        }
    }
}

impl Drop for WatchPoolLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}

pub fn watch_pool_path(runtime_root: &Path) -> PathBuf {
    runtime_root.join("watch_pool.csv")
}

pub fn load_watch_pool(path: &Path) -> anyhow::Result<Vec<WatchPoolRow>> {
    if !path.exists() {
        return Ok(Vec::new());
    }
    let content = fs::read_to_string(path)
        .with_context(|| format!("read watch pool csv {}", path.display()))?;
    let mut rows = Vec::new();
    for (index, line) in content.lines().enumerate() {
        if index == 0 && line.trim() == WATCH_POOL_HEADER {
            continue;
        }
        if line.trim().is_empty() {
            continue;
        }
        let fields = parse_csv_line(line);
        if fields.len() < 8 {
            anyhow::bail!(
                "invalid watch pool csv row {} in {}",
                index + 1,
                path.display()
            );
        }
        rows.push(WatchPoolRow {
            method: fields[0].trim().to_ascii_lowercase(),
            pick_date: NaiveDate::parse_from_str(fields[1].trim(), "%Y-%m-%d")
                .with_context(|| format!("parse watch pool pick_date '{}'", fields[1]))?,
            code: fields[2].trim().to_string(),
            verdict: fields[3].trim().to_ascii_uppercase(),
            total_score: fields[4].trim().parse::<f64>().unwrap_or(0.0),
            signal_type: fields[5].trim().to_string(),
            comment: fields[6].trim().to_string(),
            recorded_at: fields[7].trim().to_string(),
        });
    }
    Ok(rows)
}

fn write_watch_pool(path: &Path, rows: &[WatchPoolRow]) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut content = String::from(WATCH_POOL_HEADER);
    content.push('\n');
    for row in rows {
        content.push_str(&format!(
            "{},{},{},{},{},{},{},{}\n",
            csv_escape(row.method.as_str()),
            row.pick_date.format("%Y-%m-%d"),
            csv_escape(row.code.as_str()),
            csv_escape(row.verdict.as_str()),
            row.total_score,
            csv_escape(row.signal_type.as_str()),
            csv_escape(row.comment.as_str()),
            csv_escape(row.recorded_at.as_str()),
        ));
    }
    let temp_path = path.with_extension("csv.tmp");
    fs::write(&temp_path, content)?;
    fs::rename(temp_path, path)?;
    Ok(())
}

fn summary_to_watch_rows(
    summary: &Value,
    method: Method,
    pick_date: NaiveDate,
    recorded_at: &str,
) -> anyhow::Result<Vec<WatchPoolRow>> {
    let mut rows = Vec::new();
    for section in ["recommendations", "excluded"] {
        let Some(items) = summary.get(section).and_then(Value::as_array) else {
            continue;
        };
        for item in items {
            let Some(code) = item.get("code").and_then(Value::as_str) else {
                continue;
            };
            let verdict = item
                .get("verdict")
                .and_then(Value::as_str)
                .unwrap_or("")
                .trim()
                .to_ascii_uppercase();
            if !matches!(verdict.as_str(), "PASS" | "WATCH") {
                continue;
            }
            rows.push(WatchPoolRow {
                method: method.as_str().to_string(),
                pick_date,
                code: code.trim().to_string(),
                verdict,
                total_score: item
                    .get("total_score")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
                signal_type: item
                    .get("signal_type")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .trim()
                    .to_string(),
                comment: item
                    .get("comment")
                    .and_then(Value::as_str)
                    .unwrap_or("")
                    .trim()
                    .to_string(),
                recorded_at: recorded_at.to_string(),
            });
        }
    }
    Ok(rows)
}

fn cutoff_trade_date(
    trade_dates: &[NaiveDate],
    pick_date: NaiveDate,
    window_trading_days: usize,
) -> anyhow::Result<NaiveDate> {
    let mut dates = trade_dates
        .iter()
        .copied()
        .filter(|date| *date <= pick_date)
        .collect::<Vec<_>>();
    dates.sort();
    dates.dedup();
    if dates.is_empty() {
        anyhow::bail!("No trade dates found on or before {pick_date}");
    }
    let offset = window_trading_days.saturating_sub(1);
    let index = dates.len().saturating_sub(1 + offset);
    Ok(dates[index])
}

fn sort_watch_rows(rows: &mut [WatchPoolRow]) {
    rows.sort_by(|left, right| {
        right
            .pick_date
            .cmp(&left.pick_date)
            .then_with(|| {
                right
                    .total_score
                    .partial_cmp(&left.total_score)
                    .unwrap_or(std::cmp::Ordering::Equal)
            })
            .then_with(|| left.method.cmp(&right.method))
            .then_with(|| left.code.cmp(&right.code))
    });
}

fn parse_csv_line(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut current = String::new();
    let mut chars = line.chars().peekable();
    let mut in_quotes = false;
    while let Some(ch) = chars.next() {
        match ch {
            '"' if in_quotes && chars.peek() == Some(&'"') => {
                current.push('"');
                chars.next();
            }
            '"' => in_quotes = !in_quotes,
            ',' if !in_quotes => {
                fields.push(current);
                current = String::new();
            }
            _ => current.push(ch),
        }
    }
    fields.push(current);
    fields
}

fn csv_escape(value: &str) -> String {
    if value.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_string()
    }
}
