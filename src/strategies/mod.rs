use std::collections::BTreeMap;

use chrono::Datelike;

use crate::indicators::macd;
use crate::model::{Candidate, PreparedRow};

pub mod b2;
pub mod b3;
pub mod lsh;

#[derive(Debug, Clone, PartialEq)]
pub struct StrategyOutput {
    pub candidates: Vec<Candidate>,
    pub stats: BTreeMap<String, usize>,
}

pub(crate) fn group_by_symbol(rows: &[PreparedRow]) -> BTreeMap<&str, Vec<&PreparedRow>> {
    let refs = rows.iter().collect::<Vec<_>>();
    group_refs_by_symbol(&refs)
}

pub(crate) fn group_refs_by_symbol<'a>(
    rows: &[&'a PreparedRow],
) -> BTreeMap<&'a str, Vec<&'a PreparedRow>> {
    let mut grouped = BTreeMap::<&str, Vec<&PreparedRow>>::new();
    for row in rows.iter().copied() {
        grouped.entry(row.ts_code.as_str()).or_default().push(row);
    }
    for history in grouped.values_mut() {
        history.sort_by_key(|row| row.trade_date);
    }
    grouped
}

pub(crate) fn sort_candidates(candidates: &mut [Candidate]) {
    candidates.sort_by(|left, right| left.code.cmp(&right.code));
}

pub(crate) fn latest_monthly_macd_dea_positive(history: &[&PreparedRow]) -> bool {
    if let Some(value) = latest_db_factor(history, "macd_monthly_dea") {
        return value > 0.0;
    }
    latest_macd_dea_positive(&monthly_asof_closes(history))
}

pub(crate) fn latest_period_macd_dif_and_dea_positive(
    history: &[&PreparedRow],
    dif_key: &str,
    dea_key: &str,
    fallback_closes: &[f64],
) -> bool {
    match (
        latest_db_factor(history, dif_key),
        latest_db_factor(history, dea_key),
    ) {
        (Some(dif), Some(dea)) => dif > 0.0 && dea > 0.0,
        _ => latest_macd_dif_and_dea_positive(fallback_closes),
    }
}

fn latest_db_factor(history: &[&PreparedRow], key: &str) -> Option<f64> {
    history
        .last()
        .and_then(|row| row.db_factors.get(key).copied())
        .filter(|value| value.is_finite())
}

pub(crate) fn latest_macd_dea_positive(closes: &[f64]) -> bool {
    if closes.is_empty() {
        return false;
    }
    let (_dif, dea, _hist) = macd(closes, 12, 26, 9);
    dea.last().is_some_and(|dea| dea.is_finite() && *dea > 0.0)
}

pub(crate) fn latest_macd_dif_and_dea_positive(closes: &[f64]) -> bool {
    if closes.is_empty() {
        return false;
    }
    let (dif, dea, _hist) = macd(closes, 12, 26, 9);
    dif.last()
        .zip(dea.last())
        .is_some_and(|(dif, dea)| dif.is_finite() && dea.is_finite() && *dif > 0.0 && *dea > 0.0)
}

pub(crate) fn weekly_asof_closes(history: &[&PreparedRow]) -> Vec<f64> {
    period_asof_closes(history, PeriodKind::Weekly)
}

pub(crate) fn monthly_asof_closes(history: &[&PreparedRow]) -> Vec<f64> {
    period_asof_closes(history, PeriodKind::Monthly)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PeriodKind {
    Weekly,
    Monthly,
}

fn period_asof_closes(history: &[&PreparedRow], kind: PeriodKind) -> Vec<f64> {
    let mut closes = Vec::new();
    let mut current_key: Option<i64> = None;
    for (idx, row) in history.iter().enumerate() {
        let key = period_key(row, kind);
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

fn period_key(row: &PreparedRow, kind: PeriodKind) -> i64 {
    match kind {
        PeriodKind::Weekly => {
            let week = row.trade_date.iso_week();
            i64::from(week.year()) * 100 + i64::from(week.week())
        }
        PeriodKind::Monthly => {
            i64::from(row.trade_date.year()) * 100 + i64::from(row.trade_date.month())
        }
    }
}
