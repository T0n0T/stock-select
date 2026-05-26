use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::Context;
use chrono::NaiveDate;
use serde::Serialize;

use crate::cache::{atomic_write_json, candidate_output_path, load_prepared_cache};
use crate::config::screen_window;
use crate::model::{Method, PreparedRow, ScreenResult};

#[derive(Debug, Clone, PartialEq)]
pub struct NativeChartArgs {
    pub method: Method,
    pub pick_date: NaiveDate,
    pub runtime_root: PathBuf,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
struct ChartPayload {
    charts: Vec<ChartItem>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
struct ChartItem {
    code: String,
    out_path: String,
    rows: Vec<ChartRow>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
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

pub fn run_native_chart(args: NativeChartArgs) -> anyhow::Result<PathBuf> {
    let candidate_path = candidate_output_path(&args.runtime_root, args.pick_date, args.method);
    let candidate_payload: ScreenResult = serde_json::from_slice(
        &fs::read(&candidate_path)
            .with_context(|| format!("read candidate file {}", candidate_path.display()))?,
    )
    .with_context(|| format!("parse candidate file {}", candidate_path.display()))?;

    let (start_date, end_date) = screen_window(args.pick_date);
    let prepared = load_prepared_cache(
        &args.runtime_root,
        args.method,
        args.pick_date,
        start_date,
        end_date,
    )?
    .ok_or_else(|| {
        anyhow::anyhow!(
            "prepared cache not found for native chart; run screen first for {} {}",
            args.pick_date,
            args.method.as_str()
        )
    })?;

    let chart_dir = args.runtime_root.join("charts").join(format!(
        "{}.{}",
        args.pick_date.format("%Y-%m-%d"),
        args.method.as_str()
    ));
    fs::create_dir_all(&chart_dir)?;
    let histories = group_histories_by_code(&prepared, args.pick_date);
    let candidate_codes = candidate_payload
        .candidates
        .iter()
        .map(|candidate| candidate.code.as_str())
        .collect::<BTreeSet<_>>();
    let charts = candidate_payload
        .candidates
        .iter()
        .map(|candidate| {
            let history = histories.get(candidate.code.as_str()).ok_or_else(|| {
                anyhow::anyhow!("No price history found for candidate: {}", candidate.code)
            })?;
            Ok(ChartItem {
                code: candidate.code.clone(),
                out_path: chart_dir
                    .join(format!("{}_day.png", candidate.code))
                    .display()
                    .to_string(),
                rows: history
                    .iter()
                    .map(|row| chart_row_from_prepared(row))
                    .collect(),
            })
        })
        .collect::<anyhow::Result<Vec<_>>>()?;
    eprintln!("[chart] candidates={}", charts.len());
    if charts.len() != candidate_codes.len() {
        anyhow::bail!("candidate code set contains duplicates");
    }

    let payload_path = args.runtime_root.join("charts").join(format!(
        "{}.{}.payload.json",
        args.pick_date.format("%Y-%m-%d"),
        args.method.as_str()
    ));
    atomic_write_json(&payload_path, &ChartPayload { charts })?;
    run_chart_script(&payload_path)?;
    Ok(chart_dir)
}

fn run_chart_script(payload_path: &Path) -> anyhow::Result<()> {
    let script_path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("scripts/render_charts.py");
    let status = Command::new("uv")
        .args([
            "run",
            script_path
                .to_str()
                .ok_or_else(|| anyhow::anyhow!("invalid chart script path"))?,
            "--input",
            payload_path
                .to_str()
                .ok_or_else(|| anyhow::anyhow!("invalid chart payload path"))?,
        ])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .status()
        .context("spawn local chart renderer")?;
    if !status.success() {
        anyhow::bail!("local chart renderer failed with status {status}");
    }
    Ok(())
}

fn group_histories_by_code(
    rows: &[PreparedRow],
    pick_date: NaiveDate,
) -> BTreeMap<&str, Vec<&PreparedRow>> {
    let mut histories: BTreeMap<&str, Vec<&PreparedRow>> = BTreeMap::new();
    for row in rows.iter().filter(|row| row.trade_date <= pick_date) {
        histories.entry(row.ts_code.as_str()).or_default().push(row);
    }
    for history in histories.values_mut() {
        history.sort_by_key(|row| row.trade_date);
    }
    histories
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

#[cfg(test)]
mod tests {
    use chrono::NaiveDate;

    use super::*;

    #[test]
    fn groups_history_by_code_up_to_pick_date() {
        let pick = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
        let rows = vec![
            prepared("000001.SZ", 24),
            prepared("000002.SZ", 24),
            prepared("000001.SZ", 25),
            prepared("000001.SZ", 26),
        ];
        let histories = group_histories_by_code(&rows, pick);
        assert_eq!(histories["000001.SZ"].len(), 2);
        assert_eq!(histories["000002.SZ"].len(), 1);
    }

    fn prepared(code: &str, day: u32) -> PreparedRow {
        PreparedRow {
            ts_code: code.to_string(),
            trade_date: NaiveDate::from_ymd_opt(2026, 5, day).unwrap(),
            open: 1.0,
            high: 2.0,
            low: 0.5,
            close: 1.5,
            volume: 100.0,
            turnover_n: 1.0,
            k: 50.0,
            d: 50.0,
            j: 50.0,
            zxdq: Some(1.2),
            zxdkx: Some(1.1),
            dif: 0.1,
            dea: 0.05,
            macd_hist: 0.05,
            ma25: Some(1.0),
            ma60: Some(1.0),
            ma144: Some(1.0),
            chg_d: Some(0.0),
            weekly_ma_bull: true,
            max_vol_not_bearish: true,
            v_shrink: true,
            safe_mode: true,
            lt_filter: true,
            yellow_b1: false,
        }
    }
}
