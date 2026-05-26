use std::collections::BTreeMap;

use chrono::NaiveDate;

use crate::model::{Candidate, Method, PreparedRow};

pub mod b1;
pub mod b2;
pub mod dribull;

#[derive(Debug, Clone, PartialEq)]
pub struct StrategyOutput {
    pub candidates: Vec<Candidate>,
    pub stats: BTreeMap<String, usize>,
}

pub fn run_strategy(method: Method, rows: &[PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    match method {
        Method::B1 => b1::run(rows, pick_date),
        Method::B2 => b2::run(rows, pick_date),
        Method::Dribull => dribull::run(rows, pick_date),
    }
}

pub(crate) fn group_by_symbol(rows: &[PreparedRow]) -> BTreeMap<&str, Vec<&PreparedRow>> {
    let mut grouped: BTreeMap<&str, Vec<&PreparedRow>> = BTreeMap::new();
    for row in rows {
        grouped.entry(row.ts_code.as_str()).or_default().push(row);
    }
    for group in grouped.values_mut() {
        group.sort_by_key(|row| row.trade_date);
    }
    grouped
}

pub(crate) fn sort_candidates(candidates: &mut [Candidate]) {
    candidates.sort_by(|left, right| {
        right
            .turnover_n
            .partial_cmp(&left.turnover_n)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(left.code.cmp(&right.code))
    });
}
