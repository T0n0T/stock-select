use chrono::Datelike;

use crate::factors::series::{FactorList, ema, pct_of, push_number};
use crate::factors::types::{FactorInputRow, FactorValue};

pub fn macd_lines(close: &[f64]) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    if close.is_empty() {
        return (Vec::new(), Vec::new(), Vec::new());
    }
    let ema12 = ema(close, 12);
    let ema26 = ema(close, 26);
    let dif = ema12
        .iter()
        .zip(ema26.iter())
        .map(|(fast, slow)| fast - slow)
        .collect::<Vec<_>>();
    let dea = ema(&dif, 9);
    let hist = dif
        .iter()
        .zip(dea.iter())
        .map(|(dif, dea)| dif - dea)
        .collect::<Vec<_>>();
    (dif, dea, hist)
}

pub fn push_macd_numeric_factors(
    factors: &mut FactorList,
    dif: &[Option<f64>],
    dea: &[Option<f64>],
    macd_hist: &[Option<f64>],
    derived_dif: &[f64],
    derived_dea: &[f64],
    derived_macd_hist: &[f64],
    latest_close: Option<f64>,
) {
    let latest_macd_hist = macd_hist
        .last()
        .copied()
        .flatten()
        .or_else(|| derived_macd_hist.last().copied());
    let previous_macd_hist = macd_hist
        .iter()
        .rev()
        .nth(1)
        .copied()
        .flatten()
        .or_else(|| derived_macd_hist.iter().rev().nth(1).copied());
    let macd_hist_delta = latest_macd_hist.zip(previous_macd_hist).map(|(a, b)| a - b);
    let macd_hist_slope_3d = if macd_hist.len() >= 4 {
        let previous = macd_hist[macd_hist.len() - 4]
            .or_else(|| derived_macd_hist.get(macd_hist.len() - 4).copied());
        latest_macd_hist
            .zip(previous)
            .map(|(latest, previous)| latest - previous)
    } else {
        None
    };

    push_number(
        factors,
        "macd_dif_to_close_pct",
        pct_of(
            dif.last()
                .copied()
                .flatten()
                .or_else(|| derived_dif.last().copied()),
            latest_close,
        ),
    );
    push_number(
        factors,
        "macd_dea_to_close_pct",
        pct_of(
            dea.last()
                .copied()
                .flatten()
                .or_else(|| derived_dea.last().copied()),
            latest_close,
        ),
    );
    push_number(
        factors,
        "macd_hist_to_close_pct",
        pct_of(latest_macd_hist, latest_close),
    );
    push_number(
        factors,
        "macd_hist_delta_to_close_pct",
        pct_of(macd_hist_delta, latest_close),
    );
    push_number(
        factors,
        "macd_hist_slope_3d_to_close_pct",
        pct_of(macd_hist_slope_3d, latest_close),
    );
    factors.push((
        "macd_hist_positive_flag".to_string(),
        latest_macd_hist
            .map(|value| FactorValue::Bool(value > 0.0))
            .unwrap_or(FactorValue::Missing),
    ));
}

pub fn push_b2_period_macd_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    let weekly = period_macd_snapshot(history, PeriodKind::Weekly);
    push_number(
        factors,
        "weekly_dea_pctile",
        weekly.as_ref().map(|value| value.dea_pctile),
    );
    push_number(
        factors,
        "weekly_macd_hist",
        weekly.as_ref().map(|value| value.hist),
    );

    let monthly = period_macd_snapshot(history, PeriodKind::Monthly);
    push_number(
        factors,
        "monthly_dea_pctile",
        monthly.as_ref().map(|value| value.dea_pctile),
    );
    push_number(
        factors,
        "monthly_macd_hist",
        monthly.as_ref().map(|value| value.hist),
    );
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct PeriodMacdSnapshot {
    dea_pctile: f64,
    hist: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PeriodKind {
    Weekly,
    Monthly,
}

fn period_macd_snapshot(
    history: &[FactorInputRow],
    kind: PeriodKind,
) -> Option<PeriodMacdSnapshot> {
    let closes = period_asof_closes(history, kind);
    if closes.is_empty() {
        return None;
    }
    let (dif, dea, _hist) = macd_lines(&closes);
    let latest_dif = *dif.last()?;
    let latest_dea = *dea.last()?;
    let prior_dea = if dea.len() > 1 {
        &dea[..dea.len() - 1]
    } else {
        &[]
    };
    let dea_pctile = (prior_dea
        .iter()
        .filter(|value| **value <= latest_dea)
        .count() as f64
        + 1.0)
        / (prior_dea.len() as f64 + 1.0);
    Some(PeriodMacdSnapshot {
        dea_pctile,
        hist: (latest_dif - latest_dea) * 2.0,
    })
}

fn period_asof_closes(history: &[FactorInputRow], kind: PeriodKind) -> Vec<f64> {
    let mut closes = Vec::new();
    let mut current_key: Option<i64> = None;
    for (idx, row) in history.iter().enumerate() {
        let key = period_key(row, idx, kind);
        if current_key.is_some_and(|current| current != key) {
            closes.push(history[idx - 1].close);
        }
        current_key = Some(key);
    }
    if let Some(latest) = history.last() {
        closes.push(latest.close);
    }
    closes
}

fn period_key(row: &FactorInputRow, idx: usize, kind: PeriodKind) -> i64 {
    if let Some(date) = row.trade_date {
        return match kind {
            PeriodKind::Weekly => {
                let week = date.iso_week();
                i64::from(week.year()) * 100 + i64::from(week.week())
            }
            PeriodKind::Monthly => i64::from(date.year()) * 100 + i64::from(date.month()),
        };
    }
    match kind {
        PeriodKind::Weekly => (idx / 5) as i64,
        PeriodKind::Monthly => (idx / 21) as i64,
    }
}
