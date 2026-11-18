use std::collections::BTreeMap;

use chrono::{Datelike, NaiveDate};

use crate::indicators::macd;
use crate::model::{Candidate, PreparedRow};
use crate::strategies::{
    StrategyOutput, group_refs_by_symbol, monthly_asof_closes, sort_candidates, weekly_asof_closes,
};

const MA25_PATH_LOOKBACK: usize = 20;
const MA25_SCM_MIN_ABOVE: usize = 16;
const MA25_SCM_RECENT_LOOKBACK: usize = 10;
const MA25_SCM_MIN_RECENT_ABOVE: usize = 8;
const MA25_PBM_CROSS_LOOKBACK: usize = 5;
const WEEKLY_VOLUME_LOOKBACK: usize = 10;

#[derive(Clone, Copy)]
enum MethodKind {
    Scm,
    Pbm,
}

impl MethodKind {
    fn method_name(self) -> &'static str {
        match self {
            Self::Scm => "scm",
            Self::Pbm => "pbm",
        }
    }

    fn signal(self) -> &'static str {
        match self {
            Self::Scm => "SCM",
            Self::Pbm => "PBM",
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Ma25PathState {
    Sustained,
    RecentCross,
    Other,
}

#[derive(Clone, Copy)]
struct WeeklyCandle {
    key: i64,
    open: f64,
    close: f64,
    volume: f64,
}

pub fn run_scm_strategy(rows: &[PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let refs = rows.iter().collect::<Vec<_>>();
    run_scm_strategy_from_refs(&refs, pick_date)
}

pub fn run_scm_strategy_from_refs(rows: &[&PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    run_strategy(rows, pick_date, MethodKind::Scm)
}

pub fn run_pbm_strategy(rows: &[PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    let refs = rows.iter().collect::<Vec<_>>();
    run_pbm_strategy_from_refs(&refs, pick_date)
}

pub fn run_pbm_strategy_from_refs(rows: &[&PreparedRow], pick_date: NaiveDate) -> StrategyOutput {
    run_strategy(rows, pick_date, MethodKind::Pbm)
}

fn run_strategy(rows: &[&PreparedRow], pick_date: NaiveDate, method: MethodKind) -> StrategyOutput {
    let grouped = group_refs_by_symbol(rows);
    let method_name = method.method_name();
    let mut stats = BTreeMap::from([
        ("total_symbols".to_string(), grouped.len()),
        ("eligible".to_string(), 0),
        ("fail_no_pick_date".to_string(), 0),
        ("fail_insufficient_history".to_string(), 0),
        ("fail_daily_shape".to_string(), 0),
        ("fail_ma25_state".to_string(), 0),
        ("fail_macd".to_string(), 0),
        ("fail_weekly_volume_candle".to_string(), 0),
        ("selected".to_string(), 0),
        (format!("selected_{method_name}"), 0),
    ]);
    let mut candidates = Vec::new();

    for (code, history) in grouped {
        let Some((idx, row)) = history
            .iter()
            .enumerate()
            .find(|(_idx, row)| row.trade_date == pick_date)
        else {
            *stats.entry("fail_no_pick_date".to_string()).or_default() += 1;
            continue;
        };
        *stats.entry("eligible".to_string()).or_default() += 1;

        if idx < 25
            || row.ma25.is_none_or(|value| !value.is_finite())
            || history[idx - 1].ma25.is_none_or(|value| !value.is_finite())
        {
            *stats
                .entry("fail_insufficient_history".to_string())
                .or_default() += 1;
            continue;
        }

        let previous = history[idx - 1];
        let previous_ma25 = previous.ma25.unwrap();
        let ma25 = row.ma25.unwrap();
        if !(previous.low < previous_ma25
            && row.close > row.open
            && row.close > ma25
            && row.volume > previous.volume)
        {
            *stats.entry("fail_daily_shape".to_string()).or_default() += 1;
            continue;
        }

        let active_history = &history[..=idx];
        let Some(ma25_path) = recent_ma25_path(active_history) else {
            *stats
                .entry("fail_insufficient_history".to_string())
                .or_default() += 1;
            continue;
        };
        let expected_path = match method {
            MethodKind::Scm => Ma25PathState::Sustained,
            MethodKind::Pbm => Ma25PathState::RecentCross,
        };
        if ma25_path != expected_path {
            *stats.entry("fail_ma25_state".to_string()).or_default() += 1;
            continue;
        }

        if !monthly_macd_histogram_increasing(active_history)
            || !weekly_macd_histogram_positive(active_history)
        {
            *stats.entry("fail_macd".to_string()).or_default() += 1;
            continue;
        }

        let Some(current_price) = current_price_for_row(row) else {
            *stats
                .entry("fail_weekly_volume_candle".to_string())
                .or_default() += 1;
            continue;
        };
        if !recent_max_volume_week_is_bullish(active_history, current_price) {
            *stats
                .entry("fail_weekly_volume_candle".to_string())
                .or_default() += 1;
            continue;
        }

        candidates.push(Candidate {
            code: code.to_string(),
            pick_date,
            close: current_price,
            turnover_n: row.turnover_n,
            signal: Some(method.signal().to_string()),
        });
        *stats.entry("selected".to_string()).or_default() += 1;
        *stats.entry(format!("selected_{method_name}")).or_default() += 1;
    }

    sort_candidates(&mut candidates);
    StrategyOutput { candidates, stats }
}

fn current_price_for_row(row: &PreparedRow) -> Option<f64> {
    row.db_factors
        .get("intraday_price_live_qfq")
        .copied()
        .filter(|value| value.is_finite())
        .or_else(|| row.close.is_finite().then_some(row.close))
}

fn recent_ma25_path(history: &[&PreparedRow]) -> Option<Ma25PathState> {
    if history.len() < MA25_PATH_LOOKBACK {
        return None;
    }
    let path = &history[history.len() - MA25_PATH_LOOKBACK..];
    let above = path
        .iter()
        .map(|row| {
            row.ma25
                .filter(|value| value.is_finite())
                .zip(row.close.is_finite().then_some(row.close))
                .map(|(ma25, close)| close > ma25)
        })
        .collect::<Option<Vec<_>>>()?;
    if !above.last().copied().unwrap_or(false) {
        return Some(Ma25PathState::Other);
    }

    let above_days = above.iter().filter(|above| **above).count();
    let recent_above_days = above
        .iter()
        .rev()
        .take(MA25_SCM_RECENT_LOOKBACK)
        .filter(|above| **above)
        .count();
    if above_days >= MA25_SCM_MIN_ABOVE && recent_above_days >= MA25_SCM_MIN_RECENT_ABOVE {
        return Some(Ma25PathState::Sustained);
    }

    let cross_start = history.len().saturating_sub(MA25_PBM_CROSS_LOOKBACK);
    let recent_cross = (cross_start..history.len()).any(|idx| {
        idx > 0
            && history[idx - 1]
                .ma25
                .filter(|value| value.is_finite())
                .zip(
                    history[idx - 1]
                        .close
                        .is_finite()
                        .then_some(history[idx - 1].close),
                )
                .zip(
                    history[idx]
                        .ma25
                        .filter(|value| value.is_finite())
                        .zip(history[idx].close.is_finite().then_some(history[idx].close)),
                )
                .is_some_and(|((previous_ma25, previous_close), (ma25, close))| {
                    previous_close <= previous_ma25 && close > ma25
                })
    });
    Some(if recent_cross {
        Ma25PathState::RecentCross
    } else {
        Ma25PathState::Other
    })
}

fn monthly_macd_histogram_increasing(history: &[&PreparedRow]) -> bool {
    let database = period_db_histograms(history, "macd_monthly_hist", false);
    let Some([previous, current]) = database.last_chunk::<2>() else {
        return false;
    };
    match (previous, current) {
        (Some(previous), Some(current)) => return current > previous,
        (None, None) => {}
        // 两侧必须共用初始化历史，不能将数据库长预热值与窗口内重算值混用。
        _ => return false,
    }

    let closes = monthly_asof_closes(history);
    let (_, _, histogram) = macd(&closes, 12, 26, 9);
    histogram
        .get(histogram.len().saturating_sub(2))
        .zip(histogram.last())
        .is_some_and(|(previous, current)| {
            previous.is_finite() && current.is_finite() && current > previous
        })
}

fn weekly_macd_histogram_positive(history: &[&PreparedRow]) -> bool {
    let closes = weekly_asof_closes(history);
    let histogram = period_macd_histogram(history, "macd_weekly_hist", &closes, true);
    histogram
        .last()
        .is_some_and(|current| current.is_finite() && *current > 0.0)
}

fn period_macd_histogram(
    history: &[&PreparedRow],
    factor_key: &str,
    closes: &[f64],
    weekly: bool,
) -> Vec<f64> {
    let (_, _, fallback) = macd(closes, 12, 26, 9);
    period_db_histograms(history, factor_key, weekly)
        .into_iter()
        .zip(fallback)
        .map(|(database_value, fallback_value)| database_value.unwrap_or(fallback_value))
        .collect()
}

fn period_db_histograms(
    history: &[&PreparedRow],
    factor_key: &str,
    weekly: bool,
) -> Vec<Option<f64>> {
    let mut values = Vec::new();
    let mut current_key = None;
    for (idx, row) in history.iter().enumerate() {
        let key = period_key(row, weekly);
        if current_key.is_some_and(|current| current != key) {
            values.push(db_histogram(history[idx - 1], factor_key));
        }
        current_key = Some(key);
    }
    if let Some(latest) = history.last() {
        values.push(db_histogram(latest, factor_key));
    }
    values
}

fn db_histogram(row: &PreparedRow, factor_key: &str) -> Option<f64> {
    row.db_factors
        .get(factor_key)
        .copied()
        .filter(|value| value.is_finite())
}

fn period_key(row: &PreparedRow, weekly: bool) -> i64 {
    if weekly {
        let week = row.trade_date.iso_week();
        i64::from(week.year()) * 100 + i64::from(week.week())
    } else {
        i64::from(row.trade_date.year()) * 100 + i64::from(row.trade_date.month())
    }
}

fn recent_max_volume_week_is_bullish(history: &[&PreparedRow], current_price: f64) -> bool {
    if !current_price.is_finite() {
        return false;
    }
    let mut candles = Vec::<WeeklyCandle>::new();
    for row in history {
        if !row.open.is_finite() || !row.close.is_finite() || !row.volume.is_finite() {
            return false;
        }
        let week = row.trade_date.iso_week();
        let key = i64::from(week.year()) * 100 + i64::from(week.week());
        if let Some(candle) = candles.last_mut().filter(|candle| candle.key == key) {
            candle.close = row.close;
            candle.volume += row.volume;
        } else {
            candles.push(WeeklyCandle {
                key,
                open: row.open,
                close: row.close,
                volume: row.volume,
            });
        }
    }

    let recent = candles
        .iter()
        .rev()
        .take(WEEKLY_VOLUME_LOOKBACK)
        .collect::<Vec<_>>();
    let largest = recent
        .iter()
        .enumerate()
        .max_by(|(left_index, left), (right_index, right)| {
            left.volume
                .total_cmp(&right.volume)
                .then_with(|| right_index.cmp(left_index))
        })
        .map(|(_index, candle)| *candle);

    largest.is_some_and(|candle| candle.close > candle.open && current_price > candle.open)
}
