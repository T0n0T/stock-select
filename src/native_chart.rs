use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use anyhow::Context;
use chrono::NaiveDate;
use serde::Serialize;

use crate::cache::{
    atomic_write_json, candidate_output_path, intraday_candidate_output_path,
    intraday_prepared_cache_data_path, load_prepared_cache,
};
use crate::config::screen_window;
use crate::model::{Method, PreparedRow, ScreenResult};
use crate::progress::ProgressReporter;

#[derive(Debug, Clone, PartialEq)]
pub struct NativeChartArgs {
    pub method: Method,
    pub pick_date: NaiveDate,
    pub runtime_root: PathBuf,
    pub codes: Option<Vec<String>>,
    pub chart_workers: usize,
    pub artifact_key: Option<String>,
    pub intraday: bool,
    pub progress: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
struct ChartPayload {
    charts: Vec<ChartItem>,
}

pub fn render_single_chart(
    code: &str,
    history: &[PreparedRow],
    out_path: &Path,
) -> anyhow::Result<()> {
    let payload_path = out_path.with_extension("payload.json");
    let item = ChartItem {
        code: code.to_string(),
        out_path: out_path.display().to_string(),
        rows: history.iter().map(chart_row_from_prepared).collect(),
    };
    atomic_write_json(&payload_path, &ChartPayload { charts: vec![item] })?;
    run_chart_script(&payload_path)?;
    let _ = fs::remove_file(payload_path);
    Ok(())
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
    let progress = ProgressReporter::new(args.progress);
    let candidate_path = if args.intraday {
        intraday_candidate_output_path(
            &args.runtime_root,
            args.artifact_key
                .as_deref()
                .ok_or_else(|| anyhow::anyhow!("intraday chart requires artifact_key"))?,
            args.method,
        )
    } else {
        candidate_output_path(&args.runtime_root, args.pick_date, args.method)
    };
    let candidate_payload: ScreenResult = serde_json::from_slice(
        &fs::read(&candidate_path)
            .with_context(|| format!("read candidate file {}", candidate_path.display()))?,
    )
    .with_context(|| format!("parse candidate file {}", candidate_path.display()))?;

    let prepared = if args.intraday {
        let data_path = intraday_prepared_cache_data_path(&args.runtime_root, args.pick_date);
        crate::cache::decode_prepared_cache_rows(&data_path)?
    } else {
        let (start_date, end_date) = screen_window(args.pick_date);
        load_prepared_cache(
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
        })?
    };

    let chart_key = args
        .artifact_key
        .clone()
        .unwrap_or_else(|| args.pick_date.format("%Y-%m-%d").to_string());
    let chart_dir =
        args.runtime_root
            .join("charts")
            .join(format!("{}.{}", chart_key, args.method.as_str()));
    fs::create_dir_all(&chart_dir)?;
    let histories = group_histories_by_code(&prepared, args.pick_date);
    let requested_codes = args
        .codes
        .map(|codes| codes.into_iter().collect::<BTreeSet<_>>());
    let charts = candidate_payload
        .candidates
        .iter()
        .filter(|candidate| should_render_chart(candidate.code.as_str(), requested_codes.as_ref()))
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
    progress.step(
        "chart",
        "payload",
        "done",
        [
            ("candidates", charts.len().to_string()),
            ("workers", args.chart_workers.to_string()),
        ],
    );
    if let Some(requested_codes) = requested_codes.as_ref() {
        let rendered_codes = charts
            .iter()
            .map(|item| item.code.as_str())
            .collect::<BTreeSet<_>>();
        let missing = requested_codes
            .iter()
            .filter(|code| !rendered_codes.contains(code.as_str()))
            .cloned()
            .collect::<Vec<_>>();
        if !missing.is_empty() {
            anyhow::bail!(
                "requested chart codes are not candidates: {}",
                missing.join(",")
            );
        }
    }

    let payload_paths = write_chart_payloads(
        &args.runtime_root,
        args.pick_date,
        args.method,
        charts,
        args.chart_workers,
    )?;
    progress.step(
        "chart",
        "render",
        "start",
        [("parts", payload_paths.len().to_string())],
    );
    run_chart_scripts(&payload_paths, progress)?;
    progress.step(
        "chart",
        "render",
        "done",
        [("dir", chart_dir.display().to_string())],
    );
    Ok(chart_dir)
}

fn write_chart_payloads(
    runtime_root: &Path,
    pick_date: NaiveDate,
    method: Method,
    charts: Vec<ChartItem>,
    chart_workers: usize,
) -> anyhow::Result<Vec<PathBuf>> {
    cleanup_chart_payloads(runtime_root, pick_date, method)?;
    let chunks = split_chart_items(charts, chart_workers);
    let chunk_count = chunks.len();
    let mut payload_paths = Vec::with_capacity(chunk_count);
    for (idx, chunk) in chunks.into_iter().enumerate() {
        let payload_path = if chunk_count == 1 {
            runtime_root.join("charts").join(format!(
                "{}.{}.payload.json",
                pick_date.format("%Y-%m-%d"),
                method.as_str()
            ))
        } else {
            runtime_root.join("charts").join(format!(
                "{}.{}.payload.part-{:02}-of-{:02}.json",
                pick_date.format("%Y-%m-%d"),
                method.as_str(),
                idx + 1,
                chunk_count
            ))
        };
        atomic_write_json(&payload_path, &ChartPayload { charts: chunk })?;
        payload_paths.push(payload_path);
    }
    Ok(payload_paths)
}

fn cleanup_chart_payloads(
    runtime_root: &Path,
    pick_date: NaiveDate,
    method: Method,
) -> anyhow::Result<()> {
    let charts_dir = runtime_root.join("charts");
    if !charts_dir.exists() {
        return Ok(());
    }
    let prefix = format!(
        "{}.{}.payload",
        pick_date.format("%Y-%m-%d"),
        method.as_str()
    );
    for entry in fs::read_dir(&charts_dir)? {
        let path = entry?.path();
        let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
            continue;
        };
        if name.starts_with(&prefix) && name.ends_with(".json") {
            fs::remove_file(path)?;
        }
    }
    Ok(())
}

fn split_chart_items(charts: Vec<ChartItem>, chart_workers: usize) -> Vec<Vec<ChartItem>> {
    if charts.is_empty() {
        return vec![Vec::new()];
    }
    let worker_count = chart_workers.max(1).min(charts.len());
    let mut chunks = vec![Vec::new(); worker_count];
    for (idx, chart) in charts.into_iter().enumerate() {
        chunks[idx % worker_count].push(chart);
    }
    chunks
        .into_iter()
        .filter(|chunk| !chunk.is_empty())
        .collect()
}

fn should_render_chart(code: &str, requested_codes: Option<&BTreeSet<String>>) -> bool {
    requested_codes.is_none_or(|codes| codes.contains(code))
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

fn run_chart_scripts(payload_paths: &[PathBuf], progress: ProgressReporter) -> anyhow::Result<()> {
    if payload_paths.len() <= 1 {
        if let Some(path) = payload_paths.first() {
            progress.step(
                "chart",
                "render-part",
                "start",
                [("part", "1/1".to_string())],
            );
            run_chart_script(path)?;
            progress.step(
                "chart",
                "render-part",
                "done",
                [("part", "1/1".to_string())],
            );
        }
        return Ok(());
    }
    let script_path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("scripts/render_charts.py");
    let script = script_path
        .to_str()
        .ok_or_else(|| anyhow::anyhow!("invalid chart script path"))?
        .to_string();
    let mut children = Vec::with_capacity(payload_paths.len());
    for (idx, payload_path) in payload_paths.iter().enumerate() {
        progress.step(
            "chart",
            "render-part",
            "start",
            [("part", format!("{}/{}", idx + 1, payload_paths.len()))],
        );
        let payload = payload_path
            .to_str()
            .ok_or_else(|| anyhow::anyhow!("invalid chart payload path"))?
            .to_string();
        let child = Command::new("uv")
            .args(["run", script.as_str(), "--input", payload.as_str()])
            .current_dir(env!("CARGO_MANIFEST_DIR"))
            .spawn()
            .with_context(|| {
                format!("spawn local chart renderer for {}", payload_path.display())
            })?;
        children.push((payload_path.clone(), child));
    }

    let mut failures = Vec::new();
    for (idx, (payload_path, mut child)) in children.into_iter().enumerate() {
        let status = child
            .wait()
            .with_context(|| format!("wait local chart renderer for {}", payload_path.display()))?;
        if !status.success() {
            failures.push(format!("{} status={status}", payload_path.display()));
        } else {
            progress.step(
                "chart",
                "render-part",
                "done",
                [("part", format!("{}/{}", idx + 1, payload_paths.len()))],
            );
        }
    }
    if !failures.is_empty() {
        anyhow::bail!("local chart renderer failed: {}", failures.join("; "));
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

    #[test]
    fn chart_subset_filter_keeps_only_requested_codes() {
        let requested = ["000002.SZ".to_string(), "000003.SZ".to_string()]
            .into_iter()
            .collect::<BTreeSet<_>>();
        assert!(!should_render_chart("000001.SZ", Some(&requested)));
        assert!(should_render_chart("000002.SZ", Some(&requested)));
        assert!(should_render_chart("000001.SZ", None));
    }

    #[test]
    fn chart_items_split_across_requested_workers_round_robin() {
        let charts = [
            "000001.SZ",
            "000002.SZ",
            "000003.SZ",
            "000004.SZ",
            "000005.SZ",
        ]
        .into_iter()
        .map(chart_item)
        .collect::<Vec<_>>();

        let chunks = split_chart_items(charts, 3);

        let codes = chunks
            .iter()
            .map(|chunk| {
                chunk
                    .iter()
                    .map(|item| item.code.as_str())
                    .collect::<Vec<_>>()
            })
            .collect::<Vec<_>>();
        assert_eq!(
            codes,
            vec![
                vec!["000001.SZ", "000004.SZ"],
                vec!["000002.SZ", "000005.SZ"],
                vec!["000003.SZ"],
            ]
        );
    }

    #[test]
    fn chart_items_split_caps_workers_to_item_count() {
        let charts = ["000001.SZ", "000002.SZ"]
            .into_iter()
            .map(chart_item)
            .collect::<Vec<_>>();

        let chunks = split_chart_items(charts, 8);

        assert_eq!(chunks.len(), 2);
        assert_eq!(chunks[0][0].code, "000001.SZ");
        assert_eq!(chunks[1][0].code, "000002.SZ");
    }

    #[test]
    fn cleanup_chart_payloads_removes_only_matching_payloads() {
        let temp = tempfile::tempdir().unwrap();
        let charts_dir = temp.path().join("charts");
        fs::create_dir_all(&charts_dir).unwrap();
        fs::write(charts_dir.join("2026-05-25.b2.payload.json"), "{}").unwrap();
        fs::write(
            charts_dir.join("2026-05-25.b2.payload.part-01-of-02.json"),
            "{}",
        )
        .unwrap();
        fs::write(charts_dir.join("2026-05-25.b1.payload.json"), "{}").unwrap();

        cleanup_chart_payloads(
            temp.path(),
            NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
            Method::B2,
        )
        .unwrap();

        assert!(!charts_dir.join("2026-05-25.b2.payload.json").exists());
        assert!(
            !charts_dir
                .join("2026-05-25.b2.payload.part-01-of-02.json")
                .exists()
        );
        assert!(charts_dir.join("2026-05-25.b1.payload.json").exists());
    }

    fn chart_item(code: &str) -> ChartItem {
        ChartItem {
            code: code.to_string(),
            out_path: format!("/tmp/{code}.png"),
            rows: Vec::new(),
        }
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
