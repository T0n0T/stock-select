use chrono::{Duration, NaiveDate};

use crate::factors::series::{FactorList, pct_change, push_bool, push_category, push_number};
use crate::factors::types::FactorInputRow;

const EPOCH_YEAR: i32 = 1970;
const BREAKOUT_MIN_PCT: f64 = 1.0;
const LINE_TOLERANCE_RATIO: f64 = 0.01;
const SHRINK_TO_BREAKOUT_MAX: f64 = 0.80;
const SHRINK_TO_PREV5_MAX: f64 = 1.00;

pub fn push_czsc_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    let latest = history.last();
    let intraday = latest
        .and_then(|row| raw(row, "intraday_structure_source_previous_eod"))
        .is_some_and(|value| value == 1.0);
    let official_history = if intraday && !history.is_empty() {
        &history[..history.len() - 1]
    } else {
        history
    };
    for (raw_prefix, factor_prefix) in [
        ("_czsc_", "czsc_"),
        ("_czsc_weekly_", "czsc_weekly_"),
        ("_czsc_monthly_", "czsc_monthly_"),
    ] {
        push_snapshot_factors(factors, official_history, latest, raw_prefix, factor_prefix);
    }
    let value = |field: &str| latest.and_then(|row| raw(row, &format!("_czsc_{field}")));
    push_intraday_distance_factors(
        factors,
        intraday.then(|| latest.map(|row| row.close)).flatten(),
        value("last_bi_high"),
        value("last_bi_low"),
        value("last_bi_mid"),
        value("latest_zs_zg"),
        value("latest_zs_zd"),
        value("latest_zs_zz"),
        value("recent_peak_high"),
        value("post_peak_first_bear_open"),
        value("post_peak_first_bear_high"),
        value("post_peak_first_bear_low"),
        value("post_peak_first_bear_close"),
    );
    push_pricing_lifecycle_factors(factors, official_history);
    push_zs_lifecycle_factors(factors, official_history);
}

fn push_snapshot_factors(
    factors: &mut FactorList,
    official_history: &[FactorInputRow],
    latest: Option<&FactorInputRow>,
    raw_prefix: &str,
    factor_prefix: &str,
) {
    let value = |field: &str| latest.and_then(|row| raw(row, &format!("{raw_prefix}{field}")));
    let day = |field: &str| latest.and_then(|row| raw_day(row, &format!("{raw_prefix}{field}")));
    let snapshot_available = value("snapshot_available").is_some_and(|value| value == 1.0);
    push_bool(
        factors,
        &format!("{factor_prefix}snapshot_available"),
        Some(snapshot_available),
    );
    push_bool(
        factors,
        &format!("{factor_prefix}period_complete"),
        value("period_complete").map(|v| v == 1.0),
    );
    push_category(
        factors,
        &format!("{factor_prefix}status"),
        value("status_code")
            .and_then(status_name)
            .unwrap_or("missing_snapshot"),
    );
    push_bool(
        factors,
        &format!("{factor_prefix}source_bar_valid"),
        value("source_bar_valid").map(|value| value == 1.0),
    );
    push_number(
        factors,
        &format!("{factor_prefix}available_finished_bi_count"),
        value("available_finished_bi_count"),
    );
    push_number(
        factors,
        &format!("{factor_prefix}recent_bi_count"),
        value("recent_bi_count"),
    );

    let close = official_history.last().map(|row| row.close);
    let bi_high = value("last_bi_high");
    let bi_low = value("last_bi_low");
    let bi_mid = value("last_bi_mid");
    let bi_available = bi_high.zip(bi_low).zip(bi_mid).is_some();
    push_bool(
        factors,
        &format!("{factor_prefix}bi_available"),
        Some(bi_available),
    );
    push_category(
        factors,
        &format!("{factor_prefix}last_bi_direction"),
        value("last_bi_direction_code")
            .and_then(direction_name)
            .unwrap_or("missing"),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_last_bi_high_pct"),
        pct_change(close, bi_high),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_last_bi_low_pct"),
        pct_change(close, bi_low),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_last_bi_mid_pct"),
        pct_change(close, bi_mid),
    );
    push_number(
        factors,
        &format!("{factor_prefix}last_bi_range_width_pct"),
        pct_change(bi_high, bi_low),
    );
    push_number(
        factors,
        &format!("{factor_prefix}last_bi_move_pct"),
        value("last_bi_direction_code").and_then(|direction| {
            let magnitude = pct_change(bi_high, bi_low)?;
            Some(if direction < 0.0 {
                -magnitude
            } else {
                magnitude
            })
        }),
    );
    push_number(
        factors,
        &format!("{factor_prefix}last_bi_duration_trade_days"),
        trading_day_span(
            official_history,
            day("last_bi_start_day"),
            day("last_bi_end_day"),
        ),
    );

    let zs_zg = value("latest_zs_zg");
    let zs_zd = value("latest_zs_zd");
    let zs_zz = value("latest_zs_zz");
    let zs_available = zs_zg.zip(zs_zd).zip(zs_zz).is_some();
    push_bool(
        factors,
        &format!("{factor_prefix}zs_available"),
        Some(zs_available),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_zs_zg_pct"),
        pct_change(close, zs_zg),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_zs_zd_pct"),
        pct_change(close, zs_zd),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_zs_zz_pct"),
        pct_change(close, zs_zz),
    );
    push_number(
        factors,
        &format!("{factor_prefix}zs_width_pct"),
        pct_change(zs_zg, zs_zd),
    );
    push_number(
        factors,
        &format!("{factor_prefix}zs_bi_count"),
        value("latest_zs_bi_count"),
    );
    push_number(
        factors,
        &format!("{factor_prefix}zs_duration_trade_days"),
        trading_day_span(
            official_history,
            day("latest_zs_start_day"),
            day("latest_zs_end_day"),
        ),
    );
    push_category(
        factors,
        &format!("{factor_prefix}zs_region"),
        zs_region(close, zs_zg, zs_zd, zs_zz),
    );

    let peak = value("recent_peak_high");
    let peak_day = day("recent_peak_day");
    push_bool(
        factors,
        &format!("{factor_prefix}recent_peak_available"),
        Some(peak.zip(peak_day).is_some()),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_recent_peak_pct"),
        pct_change(close, peak),
    );
    push_number(
        factors,
        &format!("{factor_prefix}recent_peak_age_trade_days"),
        trading_days_since(official_history, peak_day),
    );

    let pricing_open = value("post_peak_first_bear_open");
    let pricing_day = day("post_peak_first_bear_day");
    let pricing_available = pricing_open.zip(pricing_day).is_some();
    push_bool(
        factors,
        &format!("{factor_prefix}pricing_line_available"),
        Some(pricing_available),
    );
    push_bool(
        factors,
        &format!("{factor_prefix}pricing_line_missing_after_peak"),
        value("post_peak_first_bear_missing").map(|value| value == 1.0),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_pricing_line_pct"),
        pct_change(close, pricing_open),
    );
    push_number(
        factors,
        &format!("{factor_prefix}pricing_line_age_trade_days"),
        trading_days_since(official_history, pricing_day),
    );
    let bear_high = value("post_peak_first_bear_high");
    let bear_low = value("post_peak_first_bear_low");
    let bear_close = value("post_peak_first_bear_close");
    push_number(
        factors,
        &format!("{factor_prefix}pricing_bear_body_pct"),
        pct_change(bear_close, pricing_open),
    );
    push_number(
        factors,
        &format!("{factor_prefix}pricing_bear_amplitude_pct"),
        pct_change(bear_high, bear_low),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_pricing_bear_high_pct"),
        pct_change(close, bear_high),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_pricing_bear_low_pct"),
        pct_change(close, bear_low),
    );
    push_number(
        factors,
        &format!("{factor_prefix}close_to_pricing_bear_close_pct"),
        pct_change(close, bear_close),
    );
    let asof = official_history.last().and_then(|row| row.trade_date);
    for (output, input) in [
        ("last_bi_start", "last_bi_start_day"),
        ("last_bi_end", "last_bi_end_day"),
        ("zs_start", "latest_zs_start_day"),
        ("zs_end", "latest_zs_end_day"),
        ("recent_peak", "recent_peak_day"),
        ("pricing_line", "post_peak_first_bear_day"),
    ] {
        push_number(
            factors,
            &format!("{factor_prefix}{output}_age_calendar_days"),
            asof.zip(day(input))
                .filter(|(asof, event)| event <= asof)
                .map(|(asof, event)| (asof - event).num_days() as f64),
        );
    }
    for (output, start, end) in [
        ("last_bi", "last_bi_start_day", "last_bi_end_day"),
        ("zs", "latest_zs_start_day", "latest_zs_end_day"),
    ] {
        push_number(
            factors,
            &format!("{factor_prefix}{output}_duration_calendar_days"),
            day(start)
                .zip(day(end))
                .filter(|(start, end)| start <= end && Some(*end) <= asof)
                .map(|(start, end)| (end - start).num_days() as f64),
        );
    }
}

#[allow(clippy::too_many_arguments)]
fn push_intraday_distance_factors(
    factors: &mut FactorList,
    close: Option<f64>,
    bi_high: Option<f64>,
    bi_low: Option<f64>,
    bi_mid: Option<f64>,
    zs_zg: Option<f64>,
    zs_zd: Option<f64>,
    zs_zz: Option<f64>,
    peak: Option<f64>,
    pricing_open: Option<f64>,
    bear_high: Option<f64>,
    bear_low: Option<f64>,
    bear_close: Option<f64>,
) {
    for (key, base) in [
        ("intraday_czsc_close_to_last_bi_high_pct", bi_high),
        ("intraday_czsc_close_to_last_bi_low_pct", bi_low),
        ("intraday_czsc_close_to_last_bi_mid_pct", bi_mid),
        ("intraday_czsc_close_to_zs_zg_pct", zs_zg),
        ("intraday_czsc_close_to_zs_zd_pct", zs_zd),
        ("intraday_czsc_close_to_zs_zz_pct", zs_zz),
        ("intraday_czsc_close_to_recent_peak_pct", peak),
        ("intraday_czsc_close_to_pricing_line_pct", pricing_open),
        ("intraday_czsc_close_to_pricing_bear_high_pct", bear_high),
        ("intraday_czsc_close_to_pricing_bear_low_pct", bear_low),
        ("intraday_czsc_close_to_pricing_bear_close_pct", bear_close),
    ] {
        push_number(factors, key, pct_change(close, base));
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct LifecycleIdentity {
    first_day: NaiveDate,
    first_price: f64,
    second_day: NaiveDate,
    second_price: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum LifecycleState {
    Unknown,
    WaitingBreakout,
    Active,
    WaitingRebreak,
}

impl LifecycleState {
    fn as_str(self) -> &'static str {
        match self {
            Self::Unknown => "unknown",
            Self::WaitingBreakout => "waiting_breakout",
            Self::Active => "active",
            Self::WaitingRebreak => "waiting_rebreak",
        }
    }
}

#[derive(Debug, Clone)]
struct LifecycleResult {
    state: LifecycleState,
    cycle_count: usize,
    failed_cycle_count: usize,
    breakout_index: Option<usize>,
    breakout_volume: Option<f64>,
    pullback_count: usize,
    first_pullback_index: Option<usize>,
    latest_pullback_index: Option<usize>,
    latest_pullback_distance_pct: Option<f64>,
    latest_pullback_volume_to_breakout: Option<f64>,
    latest_pullback_volume_to_prev5: Option<f64>,
    latest_pullback_shrink: Option<bool>,
}

impl Default for LifecycleResult {
    fn default() -> Self {
        Self {
            state: LifecycleState::Unknown,
            cycle_count: 0,
            failed_cycle_count: 0,
            breakout_index: None,
            breakout_volume: None,
            pullback_count: 0,
            first_pullback_index: None,
            latest_pullback_index: None,
            latest_pullback_distance_pct: None,
            latest_pullback_volume_to_breakout: None,
            latest_pullback_volume_to_prev5: None,
            latest_pullback_shrink: None,
        }
    }
}

fn push_pricing_lifecycle_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    push_lifecycle_factors(
        factors,
        history,
        "czsc_pricing",
        "czsc_pricing_line_active_flag",
        pricing_lifecycle_input,
    );
}

fn push_zs_lifecycle_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    push_lifecycle_factors(
        factors,
        history,
        "czsc_zs",
        "czsc_zs_upper_active_flag",
        zs_lifecycle_input,
    );
}

fn push_lifecycle_factors(
    factors: &mut FactorList,
    history: &[FactorInputRow],
    prefix: &str,
    active_key: &str,
    input: fn(&FactorInputRow) -> Option<(LifecycleIdentity, f64, f64)>,
) {
    let lifecycle = derive_lifecycle(history, input);
    let state = lifecycle
        .as_ref()
        .map(|value| value.state.as_str())
        .unwrap_or("missing");
    push_category(factors, &format!("{prefix}_lifecycle_state"), state);
    push_bool(
        factors,
        active_key,
        lifecycle
            .as_ref()
            .map(|value| value.state == LifecycleState::Active),
    );
    push_number(
        factors,
        &format!("{prefix}_cycle_count"),
        lifecycle.as_ref().map(|value| value.cycle_count as f64),
    );
    push_number(
        factors,
        &format!("{prefix}_failed_cycle_count"),
        lifecycle
            .as_ref()
            .map(|value| value.failed_cycle_count as f64),
    );
    push_number(
        factors,
        &format!("{prefix}_pullback_count"),
        lifecycle.as_ref().map(|value| value.pullback_count as f64),
    );
    let latest_index = history.len().checked_sub(1);
    push_number(
        factors,
        &format!("{prefix}_days_since_breakout"),
        lifecycle
            .as_ref()
            .and_then(|value| index_age(latest_index, value.breakout_index)),
    );
    push_number(
        factors,
        &format!("{prefix}_days_since_first_pullback"),
        lifecycle
            .as_ref()
            .and_then(|value| index_age(latest_index, value.first_pullback_index)),
    );
    push_number(
        factors,
        &format!("{prefix}_days_since_latest_pullback"),
        lifecycle
            .as_ref()
            .and_then(|value| index_age(latest_index, value.latest_pullback_index)),
    );
    push_number(
        factors,
        &format!("{prefix}_latest_pullback_distance_pct"),
        lifecycle
            .as_ref()
            .and_then(|value| value.latest_pullback_distance_pct),
    );
    push_number(
        factors,
        &format!("{prefix}_latest_pullback_volume_to_breakout"),
        lifecycle
            .as_ref()
            .and_then(|value| value.latest_pullback_volume_to_breakout),
    );
    push_number(
        factors,
        &format!("{prefix}_latest_pullback_volume_to_prev5"),
        lifecycle
            .as_ref()
            .and_then(|value| value.latest_pullback_volume_to_prev5),
    );
    push_bool(
        factors,
        &format!("{prefix}_latest_pullback_shrink_flag"),
        lifecycle
            .as_ref()
            .and_then(|value| value.latest_pullback_shrink),
    );
    push_bool(
        factors,
        &format!("{prefix}_pullback_today_flag"),
        lifecycle.as_ref().and_then(|value| {
            latest_index.map(|latest| value.latest_pullback_index == Some(latest))
        }),
    );
}

fn derive_lifecycle(
    history: &[FactorInputRow],
    input: fn(&FactorInputRow) -> Option<(LifecycleIdentity, f64, f64)>,
) -> Option<LifecycleResult> {
    let mut current_identity = None;
    let mut result = LifecycleResult::default();
    let mut saw_identity = false;

    for (index, row) in history.iter().enumerate() {
        let Some((identity, trigger_line, support_line)) = input(row) else {
            current_identity = None;
            result = LifecycleResult::default();
            continue;
        };
        saw_identity = true;
        if current_identity != Some(identity) {
            current_identity = Some(identity);
            result = LifecycleResult::default();
            if index > 0 {
                result.state = LifecycleState::WaitingBreakout;
            }
            continue;
        }
        let previous_close = index.checked_sub(1).map(|previous| history[previous].close);

        if result.state != LifecycleState::Active {
            let breakout = pct_change(previous_close, Some(trigger_line))
                .is_some_and(|value| value < BREAKOUT_MIN_PCT)
                && pct_change(Some(row.close), Some(trigger_line))
                    .is_some_and(|value| value >= BREAKOUT_MIN_PCT);
            if breakout {
                result.state = LifecycleState::Active;
                result.cycle_count += 1;
                result.breakout_index = Some(index);
                result.breakout_volume = row.volume.is_finite().then_some(row.volume);
                result.pullback_count = 0;
                result.first_pullback_index = None;
                result.latest_pullback_index = None;
                result.latest_pullback_distance_pct = None;
                result.latest_pullback_volume_to_breakout = None;
                result.latest_pullback_volume_to_prev5 = None;
                result.latest_pullback_shrink = None;
            }
            continue;
        }

        if row.close < support_line * (1.0 - LINE_TOLERANCE_RATIO) {
            result.state = LifecycleState::WaitingRebreak;
            result.failed_cycle_count += 1;
            result.breakout_index = None;
            result.breakout_volume = None;
            continue;
        }

        let after_breakout = result
            .breakout_index
            .is_some_and(|breakout| index > breakout);
        let touched = row.low >= support_line * (1.0 - LINE_TOLERANCE_RATIO)
            && row.low <= support_line * (1.0 + LINE_TOLERANCE_RATIO);
        if after_breakout && touched {
            result.pullback_count += 1;
            result.first_pullback_index.get_or_insert(index);
            result.latest_pullback_index = Some(index);
            result.latest_pullback_distance_pct = pct_change(Some(row.low), Some(support_line));
            result.latest_pullback_volume_to_breakout = ratio(row.volume, result.breakout_volume);
            result.latest_pullback_volume_to_prev5 = previous_volume_mean(history, index, 5)
                .and_then(|average| ratio(row.volume, Some(average)));
            result.latest_pullback_shrink = result
                .latest_pullback_volume_to_breakout
                .zip(result.latest_pullback_volume_to_prev5)
                .map(|(to_breakout, to_prev5)| {
                    to_breakout <= SHRINK_TO_BREAKOUT_MAX && to_prev5 <= SHRINK_TO_PREV5_MAX
                });
        }
    }

    saw_identity.then_some(result)
}

fn pricing_lifecycle_input(row: &FactorInputRow) -> Option<(LifecycleIdentity, f64, f64)> {
    let peak_day = raw_day(row, "_czsc_recent_peak_day")?;
    let peak_high = raw(row, "_czsc_recent_peak_high")?;
    let bear_day = raw_day(row, "_czsc_post_peak_first_bear_day")?;
    let pricing_open = raw(row, "_czsc_post_peak_first_bear_open")?;
    Some((
        LifecycleIdentity {
            first_day: peak_day,
            first_price: peak_high,
            second_day: bear_day,
            second_price: pricing_open,
        },
        peak_high,
        pricing_open,
    ))
}

fn zs_lifecycle_input(row: &FactorInputRow) -> Option<(LifecycleIdentity, f64, f64)> {
    let start_day = raw_day(row, "_czsc_latest_zs_start_day")?;
    let end_day = raw_day(row, "_czsc_latest_zs_end_day")?;
    let zg = raw(row, "_czsc_latest_zs_zg")?;
    let zd = raw(row, "_czsc_latest_zs_zd")?;
    Some((
        LifecycleIdentity {
            first_day: start_day,
            first_price: zg,
            second_day: end_day,
            second_price: zd,
        },
        zg,
        zg,
    ))
}

fn ratio(current: f64, base: Option<f64>) -> Option<f64> {
    base.filter(|value| *value != 0.0)
        .map(|value| current / value)
}

fn previous_volume_mean(
    history: &[FactorInputRow],
    current_index: usize,
    window: usize,
) -> Option<f64> {
    if current_index < window || window == 0 {
        return None;
    }
    let values = &history[current_index - window..current_index];
    values
        .iter()
        .all(|row| row.volume.is_finite())
        .then(|| values.iter().map(|row| row.volume).sum::<f64>() / window as f64)
}

fn index_age(latest: Option<usize>, event: Option<usize>) -> Option<f64> {
    Some(latest?.checked_sub(event?)? as f64)
}

fn raw(row: &FactorInputRow, key: &str) -> Option<f64> {
    row.db_factors
        .get(key)
        .copied()
        .filter(|value| value.is_finite())
}

fn raw_day(row: &FactorInputRow, key: &str) -> Option<NaiveDate> {
    let days = raw(row, key)? as i64;
    NaiveDate::from_ymd_opt(EPOCH_YEAR, 1, 1)?.checked_add_signed(Duration::days(days))
}

fn status_name(code: f64) -> Option<&'static str> {
    match code as i32 {
        0 => Some("invalid_source_bar"),
        1 => Some("no_finished_bi"),
        2 => Some("insufficient_bis_for_zs"),
        3 => Some("no_valid_zs"),
        4 => Some("ok"),
        _ => None,
    }
}

fn direction_name(code: f64) -> Option<&'static str> {
    if code > 0.0 {
        Some("up")
    } else if code < 0.0 {
        Some("down")
    } else {
        None
    }
}

fn zs_region(
    close: Option<f64>,
    zg: Option<f64>,
    zd: Option<f64>,
    zz: Option<f64>,
) -> &'static str {
    let (Some(close), Some(zg), Some(zd), Some(zz)) = (close, zg, zd, zz) else {
        return "missing";
    };
    if close > zg {
        "above_zg"
    } else if close < zd {
        "below_zd"
    } else if close >= zz {
        "inside_upper"
    } else {
        "inside_lower"
    }
}

fn trading_day_span(
    history: &[FactorInputRow],
    start: Option<NaiveDate>,
    end: Option<NaiveDate>,
) -> Option<f64> {
    let (Some(start), Some(end)) = (start, end) else {
        return None;
    };
    let first = history.first()?.trade_date?;
    let latest = history.last()?.trade_date?;
    if start < first || end > latest || start > end {
        return None;
    }
    Some(
        history
            .iter()
            .filter_map(|row| row.trade_date)
            .filter(|date| *date >= start && *date <= end)
            .count() as f64,
    )
}

fn trading_days_since(history: &[FactorInputRow], event: Option<NaiveDate>) -> Option<f64> {
    let event = event?;
    let first = history.first()?.trade_date?;
    let latest = history.last()?.trade_date?;
    if event < first || event > latest {
        return None;
    }
    Some(
        history
            .iter()
            .filter_map(|row| row.trade_date)
            .filter(|date| *date > event && *date <= latest)
            .count() as f64,
    )
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use chrono::{Duration, NaiveDate};

    use super::*;
    use crate::factors::types::FactorValue;

    fn epoch_day(date: NaiveDate) -> f64 {
        (date - NaiveDate::from_ymd_opt(1970, 1, 1).unwrap()).num_days() as f64
    }

    fn pricing_row(
        first_date: NaiveDate,
        index: usize,
        close: f64,
        low: f64,
        volume: f64,
    ) -> FactorInputRow {
        let mut db_factors = BTreeMap::new();
        if index >= 1 {
            db_factors.extend([
                ("_czsc_snapshot_available".to_string(), 1.0),
                ("_czsc_source_bar_valid".to_string(), 1.0),
                ("_czsc_status_code".to_string(), 4.0),
                (
                    "_czsc_recent_peak_day".to_string(),
                    epoch_day(first_date + Duration::days(1)),
                ),
                ("_czsc_recent_peak_high".to_string(), 10.0),
                (
                    "_czsc_post_peak_first_bear_day".to_string(),
                    epoch_day(first_date + Duration::days(2)),
                ),
                ("_czsc_post_peak_first_bear_open".to_string(), 9.0),
            ]);
        }
        FactorInputRow {
            trade_date: Some(first_date + Duration::days(index as i64)),
            open: close,
            high: close.max(low),
            low,
            close,
            volume,
            turnover_n: 1.0,
            turnover_rate: None,
            d: None,
            j: None,
            ma25: None,
            ma60: None,
            zxdkx: None,
            zxdq: None,
            dif: None,
            dea: None,
            macd_hist: None,
            db_factors,
        }
    }

    fn factor<'a>(factors: &'a FactorList, key: &str) -> &'a FactorValue {
        factors
            .iter()
            .rev()
            .find_map(|(candidate, value)| (candidate == key).then_some(value))
            .unwrap_or_else(|| panic!("missing factor {key}"))
    }

    #[test]
    fn structural_trade_day_counts_do_not_silently_clip_to_the_loaded_window() {
        let date = NaiveDate::from_ymd_opt(2026, 11, 20).unwrap();
        let history = [pricing_row(date, 0, 10.0, 9.0, 1000.0)];
        assert_eq!(
            trading_day_span(&history, Some(date - Duration::days(400)), Some(date)),
            None
        );
        assert_eq!(
            trading_days_since(&history, Some(date - Duration::days(400))),
            None
        );
        assert_eq!(
            trading_days_since(&history, Some(date + Duration::days(1))),
            None
        );
        assert_eq!(
            trading_day_span(&history, Some(date), Some(date)),
            Some(1.0)
        );
    }

    #[test]
    fn lifecycle_thresholds_are_inclusive_and_latest_pullback_replaces_details() {
        let first_date = NaiveDate::from_ymd_opt(2026, 6, 1).unwrap();
        let closes = [9.5, 9.8, 10.1, 8.91, 9.2, 9.2, 9.2, 9.2, 9.0];
        let lows = [9.4, 9.7, 10.0, 8.91, 9.2, 9.2, 9.2, 9.2, 8.91];
        let volumes = [
            800.0, 800.0, 1_000.0, 800.0, 800.0, 800.0, 800.0, 800.0, 800.0,
        ];
        let rows = closes
            .into_iter()
            .zip(lows)
            .zip(volumes)
            .enumerate()
            .map(|(index, ((close, low), volume))| {
                pricing_row(first_date, index, close, low, volume)
            })
            .collect::<Vec<_>>();

        let mut first_pullback_factors = FactorList::new();
        push_czsc_factors(&mut first_pullback_factors, &rows[..4]);
        assert_eq!(
            factor(
                &first_pullback_factors,
                "czsc_pricing_latest_pullback_shrink_flag"
            ),
            &FactorValue::Missing
        );
        assert_eq!(
            factor(&first_pullback_factors, "czsc_pricing_lifecycle_state"),
            &FactorValue::Category("active".to_string())
        );

        let mut factors = FactorList::new();
        push_czsc_factors(&mut factors, &rows);
        assert_eq!(
            factor(&factors, "czsc_pricing_lifecycle_state"),
            &FactorValue::Category("active".to_string())
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_cycle_count"),
            &FactorValue::Number(1.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_failed_cycle_count"),
            &FactorValue::Number(0.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_pullback_count"),
            &FactorValue::Number(2.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_days_since_breakout"),
            &FactorValue::Number(6.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_days_since_first_pullback"),
            &FactorValue::Number(5.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_days_since_latest_pullback"),
            &FactorValue::Number(0.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_latest_pullback_distance_pct"),
            &FactorValue::Number(-1.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_latest_pullback_volume_to_breakout"),
            &FactorValue::Number(0.8)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_latest_pullback_volume_to_prev5"),
            &FactorValue::Number(1.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_latest_pullback_shrink_flag"),
            &FactorValue::Bool(true)
        );
    }

    #[test]
    fn lifecycle_does_not_count_support_touch_before_breakout() {
        let first_date = NaiveDate::from_ymd_opt(2026, 6, 1).unwrap();
        let closes = [9.5, 9.4, 9.2, 9.3];
        let lows = [9.4, 9.0, 8.91, 9.0];
        let rows = closes
            .into_iter()
            .zip(lows)
            .enumerate()
            .map(|(index, (close, low))| pricing_row(first_date, index, close, low, 800.0))
            .collect::<Vec<_>>();

        let mut factors = FactorList::new();
        push_czsc_factors(&mut factors, &rows);

        assert_eq!(
            factor(&factors, "czsc_pricing_lifecycle_state"),
            &FactorValue::Category("waiting_breakout".to_string())
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_cycle_count"),
            &FactorValue::Number(0.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_pullback_count"),
            &FactorValue::Number(0.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_latest_pullback_distance_pct"),
            &FactorValue::Missing
        );
    }

    #[test]
    fn lifecycle_does_not_count_breakout_day_as_pullback() {
        let first_date = NaiveDate::from_ymd_opt(2026, 6, 1).unwrap();
        let closes = [9.5, 9.8, 10.1];
        let lows = [9.4, 9.7, 8.91];
        let rows = closes
            .into_iter()
            .zip(lows)
            .enumerate()
            .map(|(index, (close, low))| pricing_row(first_date, index, close, low, 800.0))
            .collect::<Vec<_>>();

        let mut factors = FactorList::new();
        push_czsc_factors(&mut factors, &rows);

        assert_eq!(
            factor(&factors, "czsc_pricing_lifecycle_state"),
            &FactorValue::Category("active".to_string())
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_cycle_count"),
            &FactorValue::Number(1.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_pullback_count"),
            &FactorValue::Number(0.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_pullback_today_flag"),
            &FactorValue::Bool(false)
        );
    }

    #[test]
    fn lifecycle_detects_delayed_crossing_of_breakout_threshold() {
        let first_date = NaiveDate::from_ymd_opt(2026, 6, 1).unwrap();
        let rows = [9.8, 10.05, 10.12]
            .into_iter()
            .enumerate()
            .map(|(index, close)| pricing_row(first_date, index, close, close, 800.0))
            .collect::<Vec<_>>();

        let mut factors = FactorList::new();
        push_czsc_factors(&mut factors, &rows);

        assert_eq!(
            factor(&factors, "czsc_pricing_lifecycle_state"),
            &FactorValue::Category("active".to_string())
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_cycle_count"),
            &FactorValue::Number(1.0)
        );
        assert_eq!(
            factor(&factors, "czsc_pricing_days_since_breakout"),
            &FactorValue::Number(0.0)
        );
    }

    #[test]
    fn lifecycle_structure_switch_resets_old_cycle_and_pullback_details() {
        let first_date = NaiveDate::from_ymd_opt(2026, 6, 1).unwrap();
        let closes = [9.5, 9.8, 10.2, 10.0, 10.4, 11.11];
        let lows = [9.4, 9.7, 10.1, 9.95, 10.3, 11.0];
        let mut rows = closes
            .into_iter()
            .zip(lows)
            .enumerate()
            .map(|(index, (close, low))| FactorInputRow {
                trade_date: Some(first_date + Duration::days(index as i64)),
                open: close,
                high: close + 0.1,
                low,
                close,
                volume: if index == 2 { 2_000.0 } else { 800.0 },
                turnover_n: 1.0,
                turnover_rate: None,
                d: None,
                j: None,
                ma25: None,
                ma60: None,
                zxdkx: None,
                zxdq: None,
                dif: None,
                dea: None,
                macd_hist: None,
                db_factors: BTreeMap::new(),
            })
            .collect::<Vec<_>>();

        for (index, row) in rows.iter_mut().enumerate().skip(1) {
            let (start_offset, end_offset, zg, zd, zz) = if index < 5 {
                (1, 2, 10.0, 8.0, 9.0)
            } else {
                (4, 5, 11.0, 9.0, 10.0)
            };
            row.db_factors.extend([
                ("_czsc_snapshot_available".to_string(), 1.0),
                ("_czsc_source_bar_valid".to_string(), 1.0),
                ("_czsc_status_code".to_string(), 4.0),
                (
                    "_czsc_latest_zs_start_day".to_string(),
                    epoch_day(first_date + Duration::days(start_offset)),
                ),
                (
                    "_czsc_latest_zs_end_day".to_string(),
                    epoch_day(first_date + Duration::days(end_offset)),
                ),
                ("_czsc_latest_zs_zg".to_string(), zg),
                ("_czsc_latest_zs_zd".to_string(), zd),
                ("_czsc_latest_zs_zz".to_string(), zz),
            ]);
        }

        let mut factors = FactorList::new();
        push_czsc_factors(&mut factors, &rows);

        assert_eq!(
            factor(&factors, "czsc_zs_lifecycle_state"),
            &FactorValue::Category("waiting_breakout".to_string())
        );
        assert_eq!(
            factor(&factors, "czsc_zs_cycle_count"),
            &FactorValue::Number(0.0)
        );
        assert_eq!(
            factor(&factors, "czsc_zs_failed_cycle_count"),
            &FactorValue::Number(0.0)
        );
        assert_eq!(
            factor(&factors, "czsc_zs_pullback_count"),
            &FactorValue::Number(0.0)
        );
        assert_eq!(
            factor(&factors, "czsc_zs_days_since_breakout"),
            &FactorValue::Missing
        );
        assert_eq!(
            factor(&factors, "czsc_zs_latest_pullback_distance_pct"),
            &FactorValue::Missing
        );
    }
}
