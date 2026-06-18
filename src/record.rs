use std::collections::{BTreeMap, BTreeSet};
use std::fs::{File, OpenOptions};
use std::path::{Path, PathBuf};
use std::str::FromStr;
use std::sync::{Mutex, MutexGuard, OnceLock};
use std::{env, fs};

use chrono::NaiveDate;

use crate::config::{resolve_config_value, resolve_config_value_from};
use crate::engine::types::DisplayRow;
use crate::model::Method;

const RECORD_FILE_NAME: &str = "record.csv";
const RECORD_LOCK_FILE_NAME: &str = ".record.lock";
const RECORD_HEADER: &str = "code,name,method,selected_date,model_rank,model_score";
const DEFAULT_WINDOW_TRADING_DAYS: usize = 10;
const DEFAULT_RECORD_LIMIT: usize = 30;
static RECORD_PROCESS_LOCK: OnceLock<Mutex<()>> = OnceLock::new();

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RunRecordConfig {
    pub methods: BTreeSet<Method>,
    pub window_trading_days: usize,
    pub record_limit: usize,
}

impl RunRecordConfig {
    pub fn for_run(
        method: Method,
        cli_record: bool,
        cli_window_trading_days: Option<usize>,
    ) -> anyhow::Result<Option<Self>> {
        if cli_record {
            return Ok(Some(Self {
                methods: BTreeSet::from([method]),
                window_trading_days: resolve_window_trading_days(cli_window_trading_days)?,
                record_limit: resolve_record_limit()?,
            }));
        }

        let Some(methods_value) = resolve_record_methods_value()? else {
            return Ok(None);
        };
        let methods = parse_record_methods(&methods_value)?;
        if !methods.contains(&method) {
            return Ok(None);
        }

        Ok(Some(Self {
            methods,
            window_trading_days: resolve_window_trading_days(cli_window_trading_days)?,
            record_limit: resolve_record_limit()?,
        }))
    }
}

pub fn update_run_record(
    runtime_root: &Path,
    method: Method,
    selected_date: NaiveDate,
    display_rows: &[DisplayRow],
    window_trading_days: usize,
    record_limit: usize,
) -> anyhow::Result<usize> {
    let _lock = RecordLock::acquire(runtime_root)?;
    let path = record_path(runtime_root);
    let mut records = load_records(&path)?;
    for row in display_rows.iter().take(record_limit) {
        let incoming = RecordRow {
            code: row.code.clone(),
            name: row.name.clone().unwrap_or_default(),
            method,
            selected_date,
            model_rank: row.model_rank,
            model_score: row.model_score,
        };
        upsert_newest_record(&mut records, incoming);
    }
    prune_by_selected_date_window(&mut records, selected_date, window_trading_days);
    write_records(&path, records.values())?;
    Ok(records.len())
}

fn record_path(runtime_root: &Path) -> PathBuf {
    runtime_root.join(RECORD_FILE_NAME)
}

struct RecordLock {
    file: File,
    _guard: MutexGuard<'static, ()>,
}

impl RecordLock {
    fn acquire(runtime_root: &Path) -> anyhow::Result<Self> {
        let guard = RECORD_PROCESS_LOCK
            .get_or_init(|| Mutex::new(()))
            .lock()
            .map_err(|_| anyhow::anyhow!("record lock poisoned"))?;
        std::fs::create_dir_all(runtime_root)?;
        let file = OpenOptions::new()
            .create(true)
            .read(true)
            .write(true)
            .open(runtime_root.join(RECORD_LOCK_FILE_NAME))?;
        file.lock()?;
        Ok(Self {
            file,
            _guard: guard,
        })
    }
}

impl Drop for RecordLock {
    fn drop(&mut self) {
        let _ = self.file.unlock();
    }
}

fn parse_record_methods(value: &str) -> anyhow::Result<BTreeSet<Method>> {
    value
        .split([',', ';', ' ', '\n', '\t'])
        .map(str::trim)
        .filter(|item| !item.is_empty())
        .map(|item| Method::from_str(&item.to_ascii_lowercase()))
        .collect()
}

fn resolve_record_methods_value() -> anyhow::Result<Option<String>> {
    match env::var("STOCK_SELECT_RECORD_METHODS") {
        Ok(value) => return Ok(Some(value)),
        Err(env::VarError::NotPresent) => {}
        Err(env::VarError::NotUnicode(_)) => {
            anyhow::bail!("STOCK_SELECT_RECORD_METHODS is not valid UTF-8")
        }
    }
    let dotenv = fs::read_to_string(".env").unwrap_or_default();
    Ok(resolve_config_value_from(
        None,
        None,
        &dotenv,
        "STOCK_SELECT_RECORD_METHODS",
    ))
}

fn resolve_window_trading_days(cli_value: Option<usize>) -> anyhow::Result<usize> {
    if let Some(value) = cli_value {
        if value == 0 {
            anyhow::bail!("--record-window-trading-days must be a positive integer");
        }
        return Ok(value);
    }
    resolve_config_value(None, "STOCK_SELECT_RECORD_WINDOW_TRADING_DAYS")
        .map(|value| parse_window_trading_days(&value))
        .transpose()
        .map(|value| value.unwrap_or(DEFAULT_WINDOW_TRADING_DAYS))
}

fn parse_window_trading_days(value: &str) -> anyhow::Result<usize> {
    let parsed = parse_positive_usize(
        value,
        "STOCK_SELECT_RECORD_WINDOW_TRADING_DAYS must be a positive integer",
    )?;
    Ok(parsed)
}

fn resolve_record_limit() -> anyhow::Result<usize> {
    resolve_config_value(None, "STOCK_SELECT_RECORD_LIMIT")
        .map(|value| parse_record_limit(&value))
        .transpose()
        .map(|value| value.unwrap_or(DEFAULT_RECORD_LIMIT))
}

fn parse_record_limit(value: &str) -> anyhow::Result<usize> {
    parse_positive_usize(
        value,
        "STOCK_SELECT_RECORD_LIMIT must be a positive integer",
    )
}

fn parse_positive_usize(value: &str, message: &str) -> anyhow::Result<usize> {
    let parsed = value
        .trim()
        .parse::<usize>()
        .map_err(|_| anyhow::anyhow!(message.to_string()))?;
    if parsed == 0 {
        anyhow::bail!(message.to_string());
    }
    Ok(parsed)
}

fn load_records(path: &Path) -> anyhow::Result<BTreeMap<RecordKey, RecordRow>> {
    if !path.exists() {
        return Ok(BTreeMap::new());
    }
    let content = std::fs::read_to_string(path)?;
    let mut records = BTreeMap::new();
    for (index, line) in content.lines().enumerate() {
        if index == 0 && line.trim() == RECORD_HEADER {
            continue;
        }
        if line.trim().is_empty() {
            continue;
        }
        let row = parse_record_line(line)?;
        upsert_newest_record(&mut records, row);
    }
    Ok(records)
}

fn upsert_newest_record(records: &mut BTreeMap<RecordKey, RecordRow>, row: RecordRow) {
    let key = row.key();
    let should_replace = records
        .get(&key)
        .map(|existing| row.selected_date >= existing.selected_date)
        .unwrap_or(true);
    if should_replace {
        records.insert(key, row);
    }
}

fn parse_record_line(line: &str) -> anyhow::Result<RecordRow> {
    let fields = parse_csv_line(line);
    if fields.len() != 6 {
        anyhow::bail!("invalid record row field count: {}", fields.len());
    }
    let method = Method::from_str(&fields[2])?;
    let selected_date = NaiveDate::parse_from_str(&fields[3], "%Y-%m-%d")?;
    let model_rank = parse_optional_usize(&fields[4])?;
    let model_score = parse_optional_f64(&fields[5])?;
    Ok(RecordRow {
        code: fields[0].clone(),
        name: fields[1].clone(),
        method,
        selected_date,
        model_rank,
        model_score,
    })
}

fn parse_optional_usize(value: &str) -> anyhow::Result<Option<usize>> {
    if value.trim().is_empty() {
        return Ok(None);
    }
    Ok(Some(value.parse()?))
}

fn parse_optional_f64(value: &str) -> anyhow::Result<Option<f64>> {
    if value.trim().is_empty() {
        return Ok(None);
    }
    Ok(Some(value.parse()?))
}

fn prune_by_selected_date_window(
    records: &mut BTreeMap<RecordKey, RecordRow>,
    selected_date: NaiveDate,
    window_trading_days: usize,
) {
    let mut dates = records
        .values()
        .map(|row| row.selected_date)
        .collect::<BTreeSet<_>>();
    dates.insert(selected_date);
    let keep_from = dates
        .iter()
        .rev()
        .nth(window_trading_days.saturating_sub(1))
        .copied()
        .or_else(|| dates.iter().next().copied())
        .unwrap_or(selected_date);
    records.retain(|_, row| row.selected_date >= keep_from);
}

fn write_records<'a>(
    path: &Path,
    records: impl IntoIterator<Item = &'a RecordRow>,
) -> anyhow::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut rows = records.into_iter().collect::<Vec<_>>();
    rows.sort_by(|left, right| {
        right
            .selected_date
            .cmp(&left.selected_date)
            .then_with(|| {
                left.model_rank
                    .unwrap_or(usize::MAX)
                    .cmp(&right.model_rank.unwrap_or(usize::MAX))
            })
            .then_with(|| left.code.cmp(&right.code))
    });
    let mut content = String::from(RECORD_HEADER);
    content.push('\n');
    for row in rows {
        content.push_str(&format!(
            "{},{},{},{},{},{}\n",
            csv_escape(&row.code),
            csv_escape(&row.name),
            row.method.as_str(),
            row.selected_date,
            row.model_rank
                .map(|rank| rank.to_string())
                .unwrap_or_default(),
            row.model_score
                .map(|score| score.to_string())
                .unwrap_or_default(),
        ));
    }
    let temp_path = path.with_extension("csv.tmp");
    std::fs::write(&temp_path, content)?;
    std::fs::rename(temp_path, path)?;
    Ok(())
}

fn csv_escape(value: &str) -> String {
    if value.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value.to_string()
    }
}

fn parse_csv_line(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut current = String::new();
    let mut chars = line.chars().peekable();
    let mut quoted = false;
    while let Some(ch) = chars.next() {
        match ch {
            '"' if quoted && chars.peek() == Some(&'"') => {
                current.push('"');
                let _ = chars.next();
            }
            '"' => quoted = !quoted,
            ',' if !quoted => {
                fields.push(std::mem::take(&mut current));
            }
            _ => current.push(ch),
        }
    }
    fields.push(current);
    fields
}

#[derive(Debug, Clone, PartialEq)]
struct RecordRow {
    code: String,
    name: String,
    method: Method,
    selected_date: NaiveDate,
    model_rank: Option<usize>,
    model_score: Option<f64>,
}

impl RecordRow {
    fn key(&self) -> RecordKey {
        RecordKey {
            code: self.code.clone(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
struct RecordKey {
    code: String,
}
