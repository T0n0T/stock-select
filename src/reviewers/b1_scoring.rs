use crate::indicators::rolling_mean;
use crate::review_protocol::compute_b1_weighted_total;

const APPROX_TOLERANCE: f64 = 0.05;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PricePositionMode {
    Default,
    LeftSideFavored,
    LessLeftBias,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PreviousAbnormalMoveMode {
    Default,
    Strict,
    Lenient,
}

#[derive(Debug, Clone, PartialEq)]
pub struct B1EnvironmentGate {
    pub cooldown_active: bool,
    pub below_ma25: bool,
    pub runup_pct: Option<f64>,
    pub sideways_amplitude_pct: Option<f64>,
    pub weekly_slope_26w: Option<f64>,
    pub weekly_macd_cooldown_active: bool,
    pub triggered_flags: Vec<String>,
    pub score_penalty: f64,
}

pub fn compute_bbi(close: &[f64]) -> Vec<Option<f64>> {
    let ma3 = rolling_mean(close, 3, 3);
    let ma6 = rolling_mean(close, 6, 6);
    let ma12 = rolling_mean(close, 12, 12);
    let ma24 = rolling_mean(close, 24, 24);
    (0..close.len())
        .map(|idx| match (ma3[idx], ma6[idx], ma12[idx], ma24[idx]) {
            (Some(a), Some(b), Some(c), Some(d)) => Some((a + b + c + d) / 4.0),
            _ => None,
        })
        .collect()
}

pub fn score_b1_trend_structure(
    open: &[f64],
    close: &[f64],
    ma25: &[Option<f64>],
    zxdkx: &[Option<f64>],
    bbi: &[Option<f64>],
) -> f64 {
    assert_same_len(open, close, "open", "close");
    assert_same_len(close, ma25, "close", "ma25");
    assert_same_len(close, zxdkx, "close", "zxdkx");
    assert_same_len(close, bbi, "close", "bbi");
    if close.len() < 5 {
        return 3.0;
    }
    let latest_ma25 = match ma25.last().copied().flatten() {
        Some(value) => value,
        None => return 3.0,
    };
    let latest_zxdkx = match zxdkx.last().copied().flatten() {
        Some(value) => value,
        None => return 3.0,
    };
    if latest_ma25 <= 0.0 || latest_zxdkx <= 0.0 {
        return 3.0;
    }

    if !(recent_slope_non_negative(ma25) && recent_slope_non_negative(zxdkx)) {
        return 1.0;
    }

    let latest = close.len() - 1;
    let p_value = (open[latest] + close[latest]) / 2.0;
    let p_below_ma25 = p_value < latest_ma25;
    let p_above_zxdkx = p_value > latest_zxdkx;
    let p_near_or_above_zxdkx = p_value >= latest_zxdkx * (1.0 - APPROX_TOLERANCE);
    let p_near_or_above_ma25 = p_value >= latest_ma25 * (1.0 - APPROX_TOLERANCE);
    let bbi_above_ma25 = tail_all_greater(bbi, ma25, 30);
    let ma25_above_zxdkx = tail_all_greater(ma25, zxdkx, 30);

    if p_below_ma25 && p_near_or_above_zxdkx && bbi_above_ma25 {
        5.0
    } else if p_below_ma25 && p_above_zxdkx {
        4.0
    } else if p_near_or_above_ma25 && ma25_above_zxdkx {
        3.0
    } else if p_value > latest_ma25 {
        2.0
    } else {
        1.0
    }
}

pub fn score_b1_price_position(
    close: &[f64],
    high: &[f64],
    low: &[f64],
    ma25: &[Option<f64>],
    zxdq: &[Option<f64>],
    mode: PricePositionMode,
) -> f64 {
    assert_same_len(high, low, "high", "low");
    let latest_close = match close.last().copied() {
        Some(value) if value.is_finite() => value,
        _ => return 3.0,
    };
    let recent_high = high
        .iter()
        .rev()
        .take(120)
        .copied()
        .filter(|value| value.is_finite())
        .fold(None, |acc: Option<f64>, value| {
            Some(acc.map_or(value, |current| current.max(value)))
        });
    let recent_low = low
        .iter()
        .rev()
        .take(120)
        .copied()
        .filter(|value| value.is_finite())
        .fold(None, |acc: Option<f64>, value| {
            Some(acc.map_or(value, |current| current.min(value)))
        });
    let (box_high, box_low) = match (recent_high, recent_low) {
        (Some(high), Some(low)) if high > low => (high, low),
        _ => return 3.0,
    };
    let position = (latest_close - box_low) / (box_high - box_low);
    let ma25_holds_zxdq = match (
        ma25.last().copied().flatten(),
        zxdq.last().copied().flatten(),
    ) {
        (Some(ma25), Some(zxdq)) => zxdq > 0.0 && ma25 >= zxdq * (1.0 - APPROX_TOLERANCE),
        _ => false,
    };

    match mode {
        PricePositionMode::LeftSideFavored => {
            if position <= 0.45 {
                return 5.0;
            }
            if position <= 0.60 {
                return 4.0;
            }
        }
        PricePositionMode::LessLeftBias => {
            if position <= 0.30 {
                return 5.0;
            }
            if position <= 0.50 {
                return 4.0;
            }
        }
        PricePositionMode::Default => {}
    }

    if position <= 0.45 {
        5.0
    } else if position <= 0.55 {
        4.0
    } else if position <= 0.65 || (position > 0.75 && ma25_holds_zxdq) {
        3.0
    } else if position <= 0.75 {
        2.0
    } else {
        1.0
    }
}

pub fn score_b1_volume_behavior(open: &[f64], close: &[f64], volume: &[f64]) -> f64 {
    assert_same_len(open, close, "open", "close");
    assert_same_len(close, volume, "close", "volume");
    if volume.len() < 2 {
        return 3.0;
    }
    let latest_volume = *volume.last().expect("volume len checked");
    if latest_volume <= 0.0 {
        return 1.0;
    }

    let max_volume_index = volume
        .iter()
        .enumerate()
        .max_by(|left, right| {
            left.1
                .partial_cmp(right.1)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|(idx, _value)| idx)
        .expect("volume len checked");
    let volume_ratio = volume[max_volume_index] / latest_volume;
    let max_volume_bullish = close[max_volume_index] >= open[max_volume_index];
    let pullback_volume_expanding = latest_pullback_volume_expanding(close, volume);

    if volume_ratio >= 2.0 && max_volume_bullish && pullback_volume_expanding {
        5.0
    } else if (volume_ratio >= 2.0 && max_volume_bullish)
        || (volume_ratio >= 3.0 && !max_volume_bullish && pullback_volume_expanding)
        || (1.5..2.0).contains(&volume_ratio) && max_volume_bullish && pullback_volume_expanding
    {
        4.0
    } else if (1.5..2.0).contains(&volume_ratio) && max_volume_bullish {
        3.0
    } else if max_volume_bullish || pullback_volume_expanding {
        2.0
    } else {
        1.0
    }
}

pub fn score_b1_previous_abnormal_move(
    open: &[f64],
    close: &[f64],
    low: &[f64],
    volume: &[f64],
    mode: PreviousAbnormalMoveMode,
) -> f64 {
    assert_same_len(open, close, "open", "close");
    assert_same_len(close, low, "close", "low");
    assert_same_len(close, volume, "close", "volume");
    if close.len() < 2 {
        return 3.0;
    }

    let start = volume.len().saturating_sub(90);
    let event_idx = match volume[start..]
        .iter()
        .enumerate()
        .filter(|(_idx, value)| value.is_finite())
        .max_by(|left, right| {
            left.1
                .partial_cmp(right.1)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
        .map(|(idx, _value)| start + idx)
    {
        Some(idx) => idx,
        None => return 3.0,
    };

    let event_open = open[event_idx];
    let event_close = close[event_idx];
    let abnormal_price = if event_close >= event_open {
        event_close
    } else {
        event_open
    };
    if abnormal_price <= 0.0 {
        return 1.0;
    }

    let mut min_low_after_event: Option<f64> = None;
    for idx in event_idx + 1..close.len() {
        let body_low = open[idx].min(close[idx]);
        if body_low.is_finite() {
            min_low_after_event = Some(match min_low_after_event {
                Some(current) => current.min(body_low),
                None => body_low,
            });
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
        PreviousAbnormalMoveMode::Strict => {
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
        PreviousAbnormalMoveMode::Lenient => {
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
        PreviousAbnormalMoveMode::Default => {
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

pub fn b1_raw_total_score(
    trend_structure: f64,
    price_position: f64,
    volume_behavior: f64,
    previous_abnormal_move: f64,
    macd_phase: f64,
) -> f64 {
    compute_b1_weighted_total(&[
        ("trend_structure", trend_structure),
        ("price_position", price_position),
        ("volume_behavior", volume_behavior),
        ("previous_abnormal_move", previous_abnormal_move),
        ("macd_phase", macd_phase),
    ])
}

pub fn compute_b1_environment_gate(
    close: &[f64],
    ma25: &[Option<f64>],
    dif: &[f64],
    dea: &[f64],
    environment_state: &str,
) -> B1EnvironmentGate {
    assert_same_len(close, ma25, "close", "ma25");
    assert_same_len(dif, dea, "dif", "dea");
    let state = environment_state.trim().to_ascii_lowercase();
    let cooldown_days = if state == "weak" { 4 } else { 2 };
    let cooldown_active = compute_daily_macd_cooldown_active(dif, dea, cooldown_days);
    let below_ma25 = match (close.last().copied(), ma25.last().copied().flatten()) {
        (Some(close), Some(ma25)) => close < ma25,
        _ => false,
    };
    let runup_pct = compute_b1_30d_runup_pct(close);
    let sideways_amplitude_pct = compute_b1_sideways_amplitude_pct(close);
    let runup_limit = resolve_b1_runup_limit(&state);
    let sideways_limit = 20.0;
    let weekly_slope_26w = None;
    let weekly_macd_cooldown_active = false;

    let mut triggered_flags = Vec::new();
    if cooldown_active {
        triggered_flags.push("cooldown_active".to_string());
    }
    if weekly_macd_cooldown_active {
        triggered_flags.push("weekly_macd_cooldown_active".to_string());
    }
    if below_ma25 {
        triggered_flags.push("below_ma25".to_string());
    }
    if runup_pct.is_some_and(|value| value >= runup_limit) {
        triggered_flags.push("runup_over_limit".to_string());
    }
    if sideways_amplitude_pct.is_some_and(|value| value <= sideways_limit) {
        triggered_flags.push("sideways_tight_range".to_string());
    }
    let score_penalty = round2(
        (if below_ma25 { 0.15 } else { 0.0 })
            + (if runup_pct.is_some_and(|value| value >= runup_limit) {
                0.2
            } else {
                0.0
            })
            + (if sideways_amplitude_pct.is_some_and(|value| value <= sideways_limit) {
                0.15
            } else {
                0.0
            }),
    );

    B1EnvironmentGate {
        cooldown_active,
        below_ma25,
        runup_pct,
        sideways_amplitude_pct,
        weekly_slope_26w,
        weekly_macd_cooldown_active,
        triggered_flags,
        score_penalty,
    }
}

fn recent_slope_non_negative(series: &[Option<f64>]) -> bool {
    if series.len() < 5 {
        return false;
    }
    match (series.last().copied().flatten(), series[series.len() - 5]) {
        (Some(last), Some(previous)) => last - previous >= 0.0,
        _ => false,
    }
}

fn compute_daily_macd_cooldown_active(dif: &[f64], dea: &[f64], cooldown_days: usize) -> bool {
    if dif.len() < 2 || dea.len() < 2 {
        return false;
    }
    let mut latest_death_index: Option<usize> = None;
    let mut latest_golden_index: Option<usize> = None;
    for idx in 1..dif.len() {
        if dif[idx - 1] >= dea[idx - 1] && dif[idx] < dea[idx] {
            latest_death_index = Some(idx);
        }
        if dif[idx - 1] <= dea[idx - 1] && dif[idx] > dea[idx] {
            latest_golden_index = Some(idx);
        }
    }
    let Some(death_idx) = latest_death_index else {
        return false;
    };
    if latest_golden_index.is_some_and(|golden_idx| golden_idx >= death_idx) {
        return false;
    }
    let bars_since_death_cross = dif.len() - 1 - death_idx;
    bars_since_death_cross < cooldown_days
}

fn compute_b1_30d_runup_pct(close: &[f64]) -> Option<f64> {
    let values = close
        .iter()
        .rev()
        .take(30)
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if values.is_empty() {
        return None;
    }
    let trailing_high = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let trailing_low = values.iter().copied().fold(f64::INFINITY, f64::min);
    if trailing_low <= 0.0 {
        return None;
    }
    Some(round2((trailing_high / trailing_low - 1.0) * 100.0))
}

fn compute_b1_sideways_amplitude_pct(close: &[f64]) -> Option<f64> {
    let values = close
        .iter()
        .rev()
        .take(10)
        .copied()
        .filter(|value| value.is_finite())
        .collect::<Vec<_>>();
    if values.len() < 5 {
        return None;
    }
    let latest_high = values.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let latest_low = values.iter().copied().fold(f64::INFINITY, f64::min);
    if latest_low <= 0.0 {
        return None;
    }
    Some(round2((latest_high / latest_low - 1.0) * 100.0))
}

fn resolve_b1_runup_limit(environment_state: &str) -> f64 {
    match environment_state {
        "strong" => 60.0,
        "weak" => 80.0,
        _ => 70.0,
    }
}

fn round2(value: f64) -> f64 {
    format!("{value:.2}")
        .parse::<f64>()
        .expect("formatted finite f64 should parse")
}

fn tail_all_greater(left: &[Option<f64>], right: &[Option<f64>], periods: usize) -> bool {
    if left.len() < periods || right.len() < periods {
        return false;
    }
    let left_tail = &left[left.len() - periods..];
    let right_tail = &right[right.len() - periods..];
    left_tail
        .iter()
        .zip(right_tail.iter())
        .all(|(left, right)| match (left, right) {
            (Some(left), Some(right)) => left > right,
            _ => false,
        })
}

fn latest_pullback_volume_expanding(close: &[f64], volume: &[f64]) -> bool {
    if close.len() < 3 {
        return false;
    }
    let mut start = close.len() - 1;
    while start > 0 && close[start] < close[start - 1] {
        start -= 1;
    }
    if start >= close.len() - 2 {
        return false;
    }
    volume[start..]
        .windows(2)
        .any(|pair| pair[1] - pair[0] > 0.0)
}

fn assert_same_len<L, R>(left: &[L], right: &[R], left_name: &str, right_name: &str) {
    assert_eq!(
        left.len(),
        right.len(),
        "{left_name} and {right_name} length mismatch"
    );
}
