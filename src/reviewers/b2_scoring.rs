use crate::environment_profiles::MethodEnvironmentProfile;
use crate::macd_trends::MacdTrendState;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum B2PricePositionMode {
    Default,
    LowRiskRequired,
    BreakoutTolerant,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum B2PreviousAbnormalMoveMode {
    Default,
    Strict,
    Lenient,
}

#[derive(Debug, Clone, PartialEq)]
pub struct B2VerdictInput<'a> {
    pub total_score: f64,
    pub trend_structure: f64,
    pub price_position: f64,
    pub volume_behavior: f64,
    pub previous_abnormal_move: f64,
    pub macd_phase: f64,
    pub signal: Option<&'a str>,
    pub signal_type: &'a str,
    pub close_above_ma25_pct: Option<f64>,
    pub ma25_above_zxdkx_pct: Option<f64>,
    pub zxdq_5d_slope_pct: Option<f64>,
    pub profile: Option<&'a MethodEnvironmentProfile>,
    pub strong_negative_macd_guard: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub struct B2WatchInput<'a> {
    pub verdict: &'a str,
    pub total_score: f64,
    pub trend_structure: f64,
    pub price_position: f64,
    pub volume_behavior: f64,
    pub previous_abnormal_move: f64,
    pub macd_phase: f64,
    pub elastic_watch_reason: Option<&'a str>,
    pub signal: Option<&'a str>,
    pub signal_type: &'a str,
}

pub fn score_b2_trend_structure(
    close: &[f64],
    low: &[f64],
    ma25: &[Option<f64>],
    zxdkx: &[Option<f64>],
    weekly_trend: Option<&MacdTrendState>,
    daily_trend: Option<&MacdTrendState>,
    profile: Option<&MethodEnvironmentProfile>,
) -> f64 {
    if close.len() < 60
        || low.len() != close.len()
        || ma25.len() != close.len()
        || zxdkx.len() != close.len()
    {
        return 3.0;
    }
    let latest = close.len() - 1;
    let Some(latest_ma25) = ma25[latest] else {
        return 3.0;
    };
    let Some(latest_zxdkx) = zxdkx[latest] else {
        return 3.0;
    };
    let Some(previous_zxdkx) = zxdkx[latest - 1] else {
        return 3.0;
    };
    let latest_ma25_prev = ma25[latest - 1].unwrap_or(latest_ma25);
    let latest_close = close[latest];
    let latest_low = low[latest];
    let near_ma25_support = latest_low <= latest_ma25 * 1.03;
    let ma_aligned = latest_close >= latest_ma25 && latest_ma25 >= latest_zxdkx;
    let weekly_phase = weekly_trend.map(|trend| trend.phase.as_str()).unwrap_or("");
    let daily_phase = daily_trend.map(|trend| trend.phase.as_str()).unwrap_or("");
    let daily_initial = daily_trend.is_some_and(|trend| trend.is_rising_initial);
    let has_divergence = weekly_trend.is_some_and(|trend| trend.is_top_divergence)
        || daily_trend.is_some_and(|trend| trend.is_top_divergence);
    let trend_window =
        weekly_phase == "rising" && daily_phase == "rising" && daily_initial && !has_divergence;
    let constructive_pullback =
        weekly_phase == "rising" && daily_phase == "falling" && !has_divergence;
    let mode = profile_mode(profile, "trend_structure");

    if trend_window && ma_aligned && latest_zxdkx >= previous_zxdkx && near_ma25_support {
        if mode == "pullback_only" {
            return 4.0;
        }
        return 5.0;
    }
    if mode == "aggressive" && trend_window && ma_aligned && latest_zxdkx >= previous_zxdkx {
        return 5.0;
    }
    if (trend_window || constructive_pullback || weekly_phase == "rising") && ma_aligned {
        return 4.0;
    }
    if ma_aligned && latest_zxdkx >= previous_zxdkx && latest_ma25 >= latest_ma25_prev {
        return 4.0;
    }
    if latest_close >= latest_zxdkx {
        return 3.0;
    }
    if latest_close >= latest_zxdkx * 0.97 {
        return 2.0;
    }
    1.0
}

pub fn score_b2_price_position(
    close: &[f64],
    high: &[f64],
    low: &[f64],
    mode: B2PricePositionMode,
) -> f64 {
    if close.is_empty() || high.is_empty() || low.is_empty() {
        return 3.0;
    }
    let recent_high = max_tail(high, 120);
    let recent_low = min_tail(low, 120);
    let latest_high = high.last().copied().filter(|value| value.is_finite());
    let latest_low = low.last().copied().filter(|value| value.is_finite());
    let (Some(box_high), Some(box_low), Some(latest_high), Some(latest_low)) =
        (recent_high, recent_low, latest_high, latest_low)
    else {
        return 3.0;
    };
    if box_high <= box_low {
        return 3.0;
    }
    let current_mid_price = (latest_high + latest_low) / 2.0;
    let box_position = (current_mid_price - box_low) / (box_high - box_low);

    match mode {
        B2PricePositionMode::LowRiskRequired => {
            if (0.60..0.80).contains(&box_position) {
                return 4.0;
            }
            if (0.80..0.92).contains(&box_position) {
                return 2.0;
            }
        }
        B2PricePositionMode::BreakoutTolerant => {
            if (0.70..0.92).contains(&box_position) {
                return 5.0;
            }
            if (0.92..1.00).contains(&box_position) {
                return 4.0;
            }
        }
        B2PricePositionMode::Default => {}
    }

    if (0.70..0.85).contains(&box_position) {
        5.0
    } else if (0.60..0.70).contains(&box_position) || (0.85..0.92).contains(&box_position) {
        4.0
    } else if (0.50..0.60).contains(&box_position) || (0.92..1.00).contains(&box_position) {
        3.0
    } else if (0.40..0.50).contains(&box_position) || (1.00..1.08).contains(&box_position) {
        2.0
    } else {
        1.0
    }
}

pub fn score_b2_volume_behavior(close: &[f64], volume: &[f64]) -> f64 {
    if close.len() < 20 || volume.len() < 20 {
        return 3.0;
    }
    let latest = close.len() - 1;
    let recent_close = &close[close.len() - 20..];
    let recent_volume = &volume[volume.len() - 20..];
    let latest_close = close[latest];
    let previous_close = close[latest - 1];
    let latest_volume = volume[volume.len() - 1];
    let average_close_5 = mean_tail(recent_close, 5);
    let average_volume_5 = mean_tail(recent_volume, 5);
    let average_volume_20 = mean(recent_volume);
    let high_close_20 = recent_close
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);

    if latest_close < average_close_5 && latest_volume >= average_volume_5 {
        return 1.0;
    }
    if latest_close < average_close_5 {
        return 2.0;
    }
    if latest_close >= high_close_20 * 0.98
        && latest_close >= previous_close
        && latest_volume >= average_volume_5 * 0.80
    {
        return 5.0;
    }
    if latest_close >= high_close_20 * 0.95 && latest_volume <= average_volume_20 * 1.80 {
        return 4.0;
    }
    3.0
}

pub fn score_b2_previous_abnormal_move(
    open: &[f64],
    close: &[f64],
    volume: &[f64],
    mode: B2PreviousAbnormalMoveMode,
) -> f64 {
    if close.len() < 2 || open.len() != close.len() || volume.len() != close.len() {
        return 3.0;
    }
    let start = volume.len().saturating_sub(90);
    let Some(event_idx) = volume[start..]
        .iter()
        .enumerate()
        .filter(|(_idx, value)| value.is_finite())
        .max_by(|left, right| {
            left.1
                .partial_cmp(right.1)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|(idx, _value)| start + idx)
    else {
        return 3.0;
    };
    let abnormal_price = if close[event_idx] >= open[event_idx] {
        close[event_idx]
    } else {
        open[event_idx]
    };
    if abnormal_price <= 0.0 {
        return 1.0;
    }
    let mut min_low_after_event: Option<f64> = None;
    for idx in event_idx + 1..close.len() {
        let body_low = open[idx].min(close[idx]);
        if body_low.is_finite() {
            min_low_after_event =
                Some(min_low_after_event.map_or(body_low, |current| current.min(body_low)));
        }
    }
    let min_low_after_event =
        min_low_after_event.unwrap_or_else(|| open[event_idx].min(close[event_idx]));
    let redundant_price = abnormal_price * 0.90;
    if redundant_price <= 0.0 {
        return 1.0;
    }
    let position_pct = (min_low_after_event / redundant_price - 1.0) * 100.0;

    if position_pct > 10.0 {
        return 3.0;
    }
    match mode {
        B2PreviousAbnormalMoveMode::Strict => {
            if position_pct > -10.0 {
                3.0
            } else if position_pct > -30.0 {
                5.0
            } else if position_pct > -45.0 {
                3.0
            } else if position_pct > -55.0 {
                2.0
            } else {
                1.0
            }
        }
        B2PreviousAbnormalMoveMode::Lenient => {
            if position_pct > -15.0 {
                5.0
            } else if position_pct > -35.0 {
                3.0
            } else if position_pct > -55.0 {
                2.0
            } else {
                1.0
            }
        }
        B2PreviousAbnormalMoveMode::Default => {
            if position_pct > -25.0 {
                5.0
            } else if position_pct > -40.0 {
                3.0
            } else if position_pct > -55.0 {
                2.0
            } else {
                1.0
            }
        }
    }
}

pub fn infer_b2_verdict(input: B2VerdictInput<'_>) -> &'static str {
    let profile_state = input.profile.map(|profile| profile.state.as_str());
    let strong_negative_macd_guard_required = input.profile.is_some_and(|profile| {
        profile.state == "strong"
            && input.price_position >= 4.0
            && input.trend_structure == 4.0
            && input.volume_behavior >= 5.0
    });

    if input.signal_type == "distribution_risk" {
        if input.macd_phase >= 4.5
            && input.previous_abnormal_move >= 5.0
            && input.trend_structure >= 3.0
            && input.price_position >= 3.0
            && input.total_score >= 3.6
        {
            return "WATCH";
        }
        return "FAIL";
    }

    let is_weak_profile = profile_state == Some("weak");
    let strong_macd_setup = input.macd_phase >= 4.5
        && input.previous_abnormal_move >= 5.0
        && input.trend_structure >= 3.0
        && input.price_position >= 2.0
        && input.volume_behavior >= 2.0
        && input.total_score >= 3.6
        && (profile_state.is_none() || profile_state == Some("strong"));
    if strong_macd_setup {
        if strong_negative_macd_guard_required && !input.strong_negative_macd_guard {
            return "WATCH";
        }
        return "PASS";
    }

    let overheat_extension = input
        .close_above_ma25_pct
        .is_some_and(|value| value >= 10.0)
        || input
            .ma25_above_zxdkx_pct
            .is_some_and(|value| value >= 15.0);
    let pass_threshold = input
        .profile
        .map(|profile| profile.pass_threshold)
        .unwrap_or(4.0);

    let mut strong_trend_start_mid_macd_setup = input.signal_type == "trend_start"
        && input.previous_abnormal_move >= 5.0
        && input.trend_structure >= 4.0
        && input.price_position >= 3.0
        && input.volume_behavior >= 3.0
        && input.total_score >= pass_threshold
        && !overheat_extension
        && !is_weak_profile
        && (input.macd_phase >= 4.2
            || (input.macd_phase >= 3.5
                && input.price_position >= 5.0
                && (profile_state.is_none() || profile_state == Some("strong"))
                && input.total_score >= pass_threshold.max(4.2)));
    if profile_state == Some("neutral")
        && input.signal_type == "trend_start"
        && input.price_position >= 4.0
        && input.macd_phase >= 4.2
    {
        strong_trend_start_mid_macd_setup = false;
    }
    if strong_trend_start_mid_macd_setup {
        if strong_negative_macd_guard_required && !input.strong_negative_macd_guard {
            return "WATCH";
        }
        return "PASS";
    }

    if profile_state == Some("neutral")
        && input.signal_type == "trend_start"
        && input.trend_structure >= 3.0
        && input.price_position == 4.0
        && input.volume_behavior >= 3.0
        && input.previous_abnormal_move >= 5.0
        && (3.8..4.2).contains(&input.macd_phase)
        && input.total_score >= 4.0
        && input.zxdq_5d_slope_pct.is_none_or(|value| value >= 0.0)
        && !overheat_extension
    {
        return "PASS";
    }

    if profile_state == Some("neutral")
        && matches!(input.signal_type, "rebound" | "trend_start")
        && input.trend_structure == 3.0
        && input.price_position >= 3.0
        && [2.0, 3.0].contains(&input.volume_behavior)
        && input.previous_abnormal_move >= 5.0
        && input.macd_phase < 4.5
        && input.total_score >= 3.45
        && (input.price_position >= 4.0 || signal_in(input.signal, &["B3", "B3+"]))
        && input.zxdq_5d_slope_pct.is_none_or(|value| value >= 0.0)
        && !overheat_extension
    {
        return "PASS";
    }

    if profile_state == Some("neutral")
        && signal_eq(input.signal, "B3")
        && input.signal_type == "trend_start"
        && input.trend_structure == 4.0
        && input.price_position == 4.0
        && input.volume_behavior == 3.0
        && input.previous_abnormal_move >= 5.0
        && input.total_score <= 4.28
        && (4.2..=4.42).contains(&input.macd_phase)
        && !overheat_extension
    {
        return "PASS";
    }

    if profile_state == Some("strong")
        && signal_in(input.signal, &["B3", "B3+"])
        && matches!(input.signal_type, "rebound" | "trend_start")
        && input.trend_structure == 4.0
        && input.price_position >= 4.0
        && input.volume_behavior >= 4.0
        && input.previous_abnormal_move >= 3.0
        && (3.0..3.8).contains(&input.macd_phase)
        && input.total_score >= 4.0
        && !overheat_extension
    {
        return "PASS";
    }

    let b3_upgrade_setup = signal_in(input.signal, &["B3", "B3+"])
        && matches!(input.signal_type, "rebound" | "trend_start")
        && input.trend_structure >= 4.0
        && input.price_position >= 5.0
        && input.previous_abnormal_move >= 5.0
        && input.total_score >= 4.15
        && !is_weak_profile
        && (input.macd_phase >= 4.2
            || (input.signal_type == "trend_start" && input.macd_phase >= 3.8));
    if b3_upgrade_setup {
        if strong_negative_macd_guard_required && !input.strong_negative_macd_guard {
            return "WATCH";
        }
        return "PASS";
    }

    if input.total_score >= 3.3 {
        "WATCH"
    } else {
        "FAIL"
    }
}

pub fn infer_b2_elastic_watch(input: &B2WatchInput<'_>) -> (bool, Option<&'static str>) {
    if input.verdict != "WATCH" {
        return (false, None);
    }
    if (4.2..4.5).contains(&input.macd_phase)
        && input.price_position >= 4.0
        && input.previous_abnormal_move >= 5.0
        && input.total_score >= 4.0
    {
        return (true, Some("mid_macd_elastic_watch"));
    }
    if input.volume_behavior < 2.0
        && input.trend_structure >= 4.0
        && input.price_position >= 4.0
        && input.previous_abnormal_move >= 5.0
        && input.total_score >= 4.0
    {
        return (true, Some("low_volume_elastic_watch"));
    }
    (false, None)
}

pub fn score_b2_watch(input: B2WatchInput<'_>) -> Option<f64> {
    if input.verdict != "WATCH" {
        return None;
    }
    let mut score = 0.0;
    score += (input.total_score - 3.3).max(0.0) * 28.0;
    score += (input.trend_structure - 3.0).max(0.0) * 8.0;
    score += (input.price_position - 3.0).max(0.0) * 7.0;
    score += (input.volume_behavior - 2.0).max(0.0) * 7.0;
    score += (input.previous_abnormal_move - 3.0).max(0.0) * 6.0;

    if (4.2..4.5).contains(&input.macd_phase) {
        score += 16.0;
    } else if (3.8..4.2).contains(&input.macd_phase) {
        score += 9.0;
    } else if input.macd_phase >= 4.5 {
        score += 6.0;
    }

    match input.elastic_watch_reason {
        Some("mid_macd_elastic_watch") => score += 12.0,
        Some("low_volume_elastic_watch") => score += 5.0,
        _ => {}
    }
    if signal_in(input.signal, &["B3", "B3+"]) {
        score += 8.0;
    } else if signal_eq(input.signal, "B5") {
        score -= 30.0;
    }
    if input.signal_type == "trend_start" {
        score += 8.0;
    } else if input.signal_type == "distribution_risk" {
        score -= 25.0;
    }
    Some(round2(score))
}

pub fn infer_b2_watch_tier(
    verdict: &str,
    watch_score: Option<f64>,
    elastic_watch_reason: Option<&str>,
    signal: Option<&str>,
) -> Option<&'static str> {
    if verdict != "WATCH" {
        return None;
    }
    if signal_eq(signal, "B5") {
        return Some("WATCH-C");
    }
    let score = watch_score.unwrap_or(0.0);
    if matches!(
        elastic_watch_reason,
        Some("mid_macd_elastic_watch" | "low_volume_elastic_watch")
    ) && score >= 65.0
    {
        Some("WATCH-A")
    } else if score >= 50.0 {
        Some("WATCH-B")
    } else {
        Some("WATCH-C")
    }
}

pub fn price_position_mode(profile: &MethodEnvironmentProfile) -> B2PricePositionMode {
    match profile_mode(Some(profile), "price_position") {
        "low_risk_required" => B2PricePositionMode::LowRiskRequired,
        "breakout_tolerant" => B2PricePositionMode::BreakoutTolerant,
        _ => B2PricePositionMode::Default,
    }
}

pub fn previous_abnormal_move_mode(
    profile: &MethodEnvironmentProfile,
) -> B2PreviousAbnormalMoveMode {
    match profile_mode(Some(profile), "previous_abnormal_move") {
        "strict" => B2PreviousAbnormalMoveMode::Strict,
        "lenient" => B2PreviousAbnormalMoveMode::Lenient,
        _ => B2PreviousAbnormalMoveMode::Default,
    }
}

fn profile_mode<'a>(profile: Option<&'a MethodEnvironmentProfile>, field: &str) -> &'a str {
    profile
        .and_then(|profile| profile.subscore_mode.get(field).map(String::as_str))
        .unwrap_or("default")
}

fn signal_eq(signal: Option<&str>, expected: &str) -> bool {
    signal.unwrap_or("").trim().eq_ignore_ascii_case(expected)
}

fn signal_in(signal: Option<&str>, expected: &[&str]) -> bool {
    expected.iter().any(|item| signal_eq(signal, item))
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

fn mean_tail(values: &[f64], len: usize) -> f64 {
    let start = values.len().saturating_sub(len);
    mean(&values[start..])
}

fn mean(values: &[f64]) -> f64 {
    let mut total = 0.0;
    let mut count = 0.0;
    for value in values.iter().copied().filter(|value| value.is_finite()) {
        total += value;
        count += 1.0;
    }
    if count == 0.0 {
        f64::NAN
    } else {
        total / count
    }
}

fn round2(value: f64) -> f64 {
    (value * 100.0).round() / 100.0
}
