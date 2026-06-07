use std::collections::BTreeMap;

use crate::model::{Candidate, PreparedRow};

pub mod b2;
pub mod b3;

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
