use chrono::{Days, NaiveDate};

use crate::environment_profiles::get_method_environment_profile;
use crate::factors::macd::macd_lines;
use crate::factors::series::{FactorList, push_category, push_number, rolling_mean_series};
use crate::factors::types::{FactorInputRow, FactorValue};
use crate::factors::zx::zx_lines;
use crate::macd_trends::{
    classify_daily_macd_trend, classify_weekly_macd_trend, map_b2_macd_phase_score,
};
use crate::model::PreparedRow;
use crate::review_protocol::infer_signal_type;
use crate::reviewers::b2_scoring::{
    previous_abnormal_move_mode, price_position_mode, score_b2_previous_abnormal_move,
    score_b2_price_position, score_b2_trend_structure, score_b2_volume_behavior,
};

pub fn push_b2_semantic_factors(
    factors: &mut FactorList,
    history: &[FactorInputRow],
    signal: Option<&str>,
    environment_state: Option<&str>,
) {
    if history.is_empty() {
        return;
    }

    let prepared = prepared_rows(history);
    let profile_state = normalized_environment_state(environment_state);
    let profile = get_method_environment_profile("b2", profile_state)
        .expect("normalized b2 environment profile must resolve");
    let weekly_trend = classify_weekly_macd_trend(&prepared);
    let daily_trend = classify_daily_macd_trend(&prepared);

    let close = prepared.iter().map(|row| row.close).collect::<Vec<_>>();
    let high = prepared.iter().map(|row| row.high).collect::<Vec<_>>();
    let low = prepared.iter().map(|row| row.low).collect::<Vec<_>>();
    let open = prepared.iter().map(|row| row.open).collect::<Vec<_>>();
    let volume = prepared.iter().map(|row| row.volume).collect::<Vec<_>>();
    let ma25 = prepared.iter().map(|row| row.ma25).collect::<Vec<_>>();
    let zxdkx = prepared.iter().map(|row| row.zxdkx).collect::<Vec<_>>();

    let mut trend_structure = score_b2_trend_structure(
        &close,
        &low,
        &ma25,
        &zxdkx,
        Some(&weekly_trend),
        Some(&daily_trend),
        Some(&profile),
    );
    let mut price_position =
        score_b2_price_position(&close, &high, &low, price_position_mode(&profile));
    if profile.state == "neutral" {
        if (price_position - 3.0).abs() < f64::EPSILON
            && matches!(close.last().zip(ma25.last()), Some((close, Some(ma25))) if close >= ma25)
        {
            price_position = 4.0;
        }
        if price_position >= 5.0 {
            price_position = 4.0;
        }
    }
    if profile.state == "weak" && trend_structure > 4.0 {
        trend_structure = 4.0;
    }
    let volume_behavior = score_b2_volume_behavior(&close, &volume);
    let previous_abnormal_move = score_b2_previous_abnormal_move(
        &open,
        &close,
        &volume,
        previous_abnormal_move_mode(&profile),
    );
    let mut macd_phase = map_b2_macd_phase_score(
        prepared.len(),
        &weekly_trend,
        &daily_trend,
        signal,
        profile.state.as_str(),
    );
    macd_phase = adjust_b2_weak_macd_phase_boundary(
        macd_phase,
        profile.state.as_str(),
        signal,
        trend_structure,
        price_position,
        volume_behavior,
        previous_abnormal_move,
    );
    macd_phase = adjust_b2_bottom_repair_macd_phase(
        macd_phase,
        profile.state.as_str(),
        b2_refined_bottom_repair_profile(&prepared).as_ref(),
        signal,
        infer_signal_type(
            *close.last().unwrap_or(&f64::NAN),
            *open.last().unwrap_or(&f64::NAN),
            trend_structure,
            volume_behavior,
            price_position,
            true,
        ),
        trend_structure,
        price_position,
        previous_abnormal_move,
    );
    let signal_type = infer_signal_type(
        *close.last().unwrap_or(&f64::NAN),
        *open.last().unwrap_or(&f64::NAN),
        trend_structure,
        volume_behavior,
        price_position,
        true,
    );

    push_number(factors, "trend_structure", Some(trend_structure));
    push_number(factors, "price_position", Some(price_position));
    push_number(factors, "volume_behavior", Some(volume_behavior));
    push_number(
        factors,
        "previous_abnormal_move",
        Some(previous_abnormal_move),
    );
    push_number(factors, "macd_phase", Some(macd_phase));
    push_category(factors, "signal_type", signal_type);
    push_category(factors, "daily_macd_phase_type", daily_trend.phase.clone());
    push_number(
        factors,
        "daily_macd_wave_index",
        Some(daily_trend.metrics.state_machine_wave_index as f64),
    );
    push_category(
        factors,
        "daily_macd_wave_stage",
        daily_trend.wave_stage.clone(),
    );
    push_category(
        factors,
        "weekly_macd_phase_type",
        weekly_trend.phase.clone(),
    );
    push_number(
        factors,
        "weekly_macd_wave_index",
        Some(weekly_trend.metrics.state_machine_wave_index as f64),
    );
    push_category(
        factors,
        "weekly_macd_wave_stage",
        weekly_trend.wave_stage.clone(),
    );
    push_category(
        factors,
        "weekly_daily_combo_type",
        format!(
            "{}:{}|{}:{}",
            weekly_trend.phase,
            weekly_trend.metrics.state_machine_wave_index,
            daily_trend.phase,
            daily_trend.metrics.state_machine_wave_index
        ),
    );
    push_bool(
        factors,
        "daily_rising_initial_flag",
        daily_trend.is_rising_initial,
    );
    push_bool(
        factors,
        "macd_top_divergence_flag",
        weekly_trend.is_top_divergence || daily_trend.is_top_divergence,
    );

    let latest_close = close.last().copied();
    let latest_low = low.last().copied();
    let previous_close = close.iter().rev().nth(1).copied();
    let recent_high = max_tail(&high, 90);
    let recent_low = min_tail(&low, 90);
    let mid_90 = recent_high
        .zip(recent_low)
        .map(|(high, low)| (high + low) / 2.0);
    push_number(
        factors,
        "price_vs_90d_high",
        pct_change_option(latest_close, recent_high),
    );
    push_number(
        factors,
        "price_vs_90d_low",
        pct_change_option(latest_close, recent_low),
    );
    push_number(
        factors,
        "price_vs_90d_mid",
        pct_change_option(latest_close, mid_90),
    );
    push_category(
        factors,
        "midline_state",
        midline_state(
            latest_close,
            previous_close,
            latest_low,
            mid_90,
            volume_ratio_5d(&volume),
        ),
    );
}

fn prepared_rows(history: &[FactorInputRow]) -> Vec<PreparedRow> {
    let close = history.iter().map(|row| row.close).collect::<Vec<_>>();
    let (derived_dif, derived_dea, derived_hist) = macd_lines(&close);
    let (derived_zxdq, derived_zxdkx) = zx_lines(&close);
    let derived_ma25 = rolling_mean_series(&close, 25, 25);
    let derived_ma60 = rolling_mean_series(&close, 60, 60);
    let derived_ma144 = rolling_mean_series(&close, 144, 144);
    history
        .iter()
        .enumerate()
        .map(|(idx, row)| PreparedRow {
            ts_code: String::new(),
            trade_date: row.trade_date.unwrap_or_else(|| {
                NaiveDate::from_ymd_opt(1970, 1, 1)
                    .unwrap()
                    .checked_add_days(Days::new(idx as u64))
                    .unwrap()
            }),
            open: row.open,
            high: row.high,
            low: row.low,
            close: row.close,
            volume: row.volume,
            turnover_n: row.turnover_n,
            turnover_rate: row.turnover_rate,
            k: 0.0,
            d: 0.0,
            j: 0.0,
            zxdq: Some(row.zxdq.unwrap_or(derived_zxdq[idx])),
            zxdkx: row.zxdkx.or(derived_zxdkx[idx]),
            dif: row.dif.unwrap_or(derived_dif[idx]),
            dea: row.dea.unwrap_or(derived_dea[idx]),
            macd_hist: row.macd_hist.unwrap_or(derived_hist[idx]),
            ma25: row.ma25.or(derived_ma25[idx]),
            ma60: derived_ma60[idx],
            ma144: derived_ma144[idx],
            chg_d: None,
            weekly_ma_bull: false,
            max_vol_not_bearish: false,
            v_shrink: false,
            safe_mode: false,
            lt_filter: false,
            yellow_b1: false,
        })
        .collect()
}

fn normalized_environment_state(value: Option<&str>) -> &str {
    match value
        .unwrap_or("neutral")
        .trim()
        .to_ascii_lowercase()
        .as_str()
    {
        "weak" => "weak",
        "strong" => "strong",
        _ => "neutral",
    }
}

fn push_bool(factors: &mut FactorList, key: &str, value: bool) {
    factors.push((key.to_string(), FactorValue::Bool(value)));
}

fn max_tail(values: &[f64], len: usize) -> Option<f64> {
    values
        .iter()
        .rev()
        .take(len)
        .copied()
        .filter(|value| value.is_finite())
        .fold(None, |acc: Option<f64>, value| {
            Some(acc.map_or(value, |current| current.max(value)))
        })
}

fn min_tail(values: &[f64], len: usize) -> Option<f64> {
    values
        .iter()
        .rev()
        .take(len)
        .copied()
        .filter(|value| value.is_finite())
        .fold(None, |acc: Option<f64>, value| {
            Some(acc.map_or(value, |current| current.min(value)))
        })
}

fn mean_tail(values: &[f64], window: usize) -> Option<f64> {
    if values.len() < window || window == 0 {
        return None;
    }
    let tail = &values[values.len() - window..];
    Some(tail.iter().sum::<f64>() / window as f64)
}

fn volume_ratio_5d(volume: &[f64]) -> Option<f64> {
    if volume.len() < 2 {
        return None;
    }
    let latest = *volume.last()?;
    let average = mean_tail(&volume[..volume.len() - 1], 5)?;
    (average > 0.0).then_some(latest / average)
}

fn ratio_option(current: Option<f64>, base: Option<f64>) -> Option<f64> {
    match (current, base) {
        (Some(current), Some(base)) if base != 0.0 => Some(current / base),
        _ => None,
    }
}

fn pct_change_option(current: Option<f64>, base: Option<f64>) -> Option<f64> {
    ratio_option(current, base).map(|ratio| (ratio - 1.0) * 100.0)
}

fn midline_state(
    latest_close: Option<f64>,
    previous_close: Option<f64>,
    latest_low: Option<f64>,
    mid_90: Option<f64>,
    volume_ratio_5d: Option<f64>,
) -> &'static str {
    let (Some(latest_close), Some(mid_90)) = (latest_close, mid_90) else {
        return "unknown";
    };
    if previous_close.is_some_and(|close| close <= mid_90)
        && latest_close > mid_90
        && volume_ratio_5d.is_some_and(|ratio| ratio >= 1.30)
    {
        return "reclaim_volume";
    }
    if latest_close >= mid_90
        && latest_low.is_some_and(|low| low <= mid_90 * 1.02 && low >= mid_90 * 0.97)
    {
        return "pullback_confirm";
    }
    if latest_close >= mid_90 {
        "above_hold"
    } else {
        "below_midline"
    }
}

fn round2(value: f64) -> f64 {
    format!("{value:.2}")
        .parse::<f64>()
        .expect("formatted finite f64 should parse")
}

fn tail_slope_pct(values: &[Option<f64>], periods: usize) -> Option<f64> {
    let filtered = values.iter().copied().flatten().collect::<Vec<_>>();
    if filtered.len() <= periods {
        return None;
    }
    let previous = filtered[filtered.len() - periods - 1];
    let latest = filtered[filtered.len() - 1];
    if previous == 0.0 {
        None
    } else {
        Some((latest / previous - 1.0) * 100.0)
    }
}

#[derive(Debug, Clone, PartialEq)]
struct B2BottomRepairProfile {
    refined: bool,
    #[allow(dead_code)]
    price_profile: &'static str,
    #[allow(dead_code)]
    neutral_tight_repair: bool,
}

#[derive(Debug, Clone, Copy)]
struct B2MacdSegment {
    sign: i8,
    end: usize,
    high: f64,
    low: f64,
}

fn adjust_b2_weak_macd_phase_boundary(
    macd_phase: f64,
    environment_state: &str,
    signal: Option<&str>,
    trend_structure: f64,
    price_position: f64,
    volume_behavior: f64,
    previous_abnormal_move: f64,
) -> f64 {
    if environment_state == "weak"
        && signal_eq(signal, "B3")
        && (2.60..=2.62).contains(&macd_phase)
        && trend_structure >= 4.0
        && price_position <= 2.0
        && volume_behavior >= 5.0
        && previous_abnormal_move >= 5.0
    {
        2.75
    } else {
        macd_phase
    }
}

fn adjust_b2_bottom_repair_macd_phase(
    macd_phase: f64,
    environment_state: &str,
    profile: Option<&B2BottomRepairProfile>,
    signal: Option<&str>,
    signal_type: &str,
    trend_structure: f64,
    price_position: f64,
    previous_abnormal_move: f64,
) -> f64 {
    let Some(profile) = profile else {
        return macd_phase;
    };
    let adjustment = if profile.refined {
        match environment_state {
            "weak" => 0.20,
            "neutral" => 0.10,
            _ => 0.0,
        }
    } else if b2_bottom_repair_sensitive_slice(
        environment_state,
        signal,
        signal_type,
        trend_structure,
        price_position,
        previous_abnormal_move,
    ) {
        match environment_state {
            "weak" => -0.20,
            "neutral" => -0.10,
            _ => 0.0,
        }
    } else {
        0.0
    };
    round2((macd_phase + adjustment).clamp(1.0, 5.0))
}

fn b2_bottom_repair_sensitive_slice(
    environment_state: &str,
    signal: Option<&str>,
    signal_type: &str,
    trend_structure: f64,
    price_position: f64,
    previous_abnormal_move: f64,
) -> bool {
    matches!(environment_state, "weak" | "neutral")
        && signal == Some("B2")
        && signal_type == "rebound"
        && (trend_structure - 3.0).abs() < f64::EPSILON
        && (price_position - 4.0).abs() < f64::EPSILON
        && (previous_abnormal_move - 5.0).abs() < f64::EPSILON
}

fn b2_refined_bottom_repair_profile(history: &[PreparedRow]) -> Option<B2BottomRepairProfile> {
    const TOLERANCE: f64 = 0.05;
    const LEFT_BOTTOM_BUFFER: f64 = 0.15;
    const MAX_VOLUME_RATIO_5D: f64 = 2.0;

    let segments = b2_macd_hist_segments(history);
    let latest_idx = segments.len().checked_sub(1)?;
    let current_green_idx = if segments[latest_idx].sign < 0 {
        latest_idx
    } else {
        latest_idx.checked_sub(1)?
    };
    if current_green_idx < 3 || segments[current_green_idx].sign >= 0 {
        return None;
    }
    let previous_red = segments[current_green_idx - 3];
    let previous_green = segments[current_green_idx - 2];
    let current_red = segments[current_green_idx - 1];
    let current_green = segments[current_green_idx];
    if previous_red.sign <= 0
        || previous_green.sign >= 0
        || current_red.sign <= 0
        || current_green.sign >= 0
    {
        return None;
    }

    let latest_close = history.last()?.close;
    let current_top = current_red.high;
    let left_top = previous_red.high;
    let left_bottom = previous_green.low;
    let pullback_low = current_green.low;
    if !latest_close.is_finite()
        || !current_top.is_finite()
        || !left_top.is_finite()
        || !left_bottom.is_finite()
        || !pullback_low.is_finite()
        || left_top <= 0.0
        || left_bottom <= 0.0
    {
        return None;
    }

    let breaks_top = current_top >= left_top * (1.0 + TOLERANCE);
    let close_holds_top = latest_close >= left_top * (1.0 - TOLERANCE);
    let bottom_buffer = pullback_low >= left_bottom * (1.0 + LEFT_BOTTOM_BUFFER);
    let volume_ratio = latest_volume_ratio(history, 5)?;
    let refined =
        breaks_top && close_holds_top && bottom_buffer && volume_ratio <= MAX_VOLUME_RATIO_5D;
    let zxdq_slope_5d = tail_slope_pct(&history.iter().map(|row| row.zxdq).collect::<Vec<_>>(), 5);
    let neutral_tight_repair = current_top >= left_top * 1.02
        && latest_close >= left_top * 0.98
        && current_top <= left_top * 1.80
        && latest_close >= current_top * 0.65
        && volume_ratio <= 1.50
        && zxdq_slope_5d.is_none_or(|slope| slope >= -1.0);
    let price_profile = if breaks_top && close_holds_top {
        "breaks_top_close_holds_top"
    } else if breaks_top {
        "breaks_top_close_below_top"
    } else {
        "no_break_top"
    };

    Some(B2BottomRepairProfile {
        refined,
        price_profile,
        neutral_tight_repair,
    })
}

fn latest_volume_ratio(history: &[PreparedRow], window: usize) -> Option<f64> {
    if history.len() < 2 {
        return None;
    }
    let latest = history.last()?.volume;
    if !latest.is_finite() {
        return None;
    }
    let previous = history
        .iter()
        .rev()
        .skip(1)
        .take(window.saturating_sub(1))
        .map(|row| row.volume)
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if previous.is_empty() {
        return None;
    }
    let average = previous.iter().sum::<f64>() / previous.len() as f64;
    (average > 0.0).then_some(latest / average)
}

fn b2_macd_hist_segments(history: &[PreparedRow]) -> Vec<B2MacdSegment> {
    let mut segments = Vec::new();
    let mut current: Option<B2MacdSegment> = None;
    for (idx, row) in history.iter().enumerate() {
        let sign = if row.macd_hist >= 0.0 { 1 } else { -1 };
        match current.as_mut() {
            Some(segment) if segment.sign == sign => {
                segment.end = idx;
                segment.high = segment.high.max(row.high);
                segment.low = segment.low.min(row.low);
            }
            Some(segment) => {
                segments.push(*segment);
                current = Some(B2MacdSegment {
                    sign,
                    end: idx,
                    high: row.high,
                    low: row.low,
                });
            }
            None => {
                current = Some(B2MacdSegment {
                    sign,
                    end: idx,
                    high: row.high,
                    low: row.low,
                });
            }
        }
    }
    if let Some(segment) = current {
        segments.push(segment);
    }
    segments
}

fn signal_eq(signal: Option<&str>, expected: &str) -> bool {
    signal.unwrap_or("").trim().eq_ignore_ascii_case(expected)
}
