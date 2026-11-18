use chrono::{Datelike, Duration, NaiveDate};

use crate::indicators::macd;
use crate::model::PreparedRow;

const RISING_INITIAL_BARS: usize = 3;
const MIN_TREND_PERIODS: usize = 4;

#[derive(Debug, Clone, PartialEq)]
pub struct MacdTrendState {
    pub phase: String,
    pub direction: String,
    pub is_rising_initial: bool,
    pub is_top_divergence: bool,
    pub bars_in_phase: usize,
    pub phase_index: i32,
    pub reason: String,
    pub metrics: Metrics,
    pub wave_label: String,
    pub wave_direction: String,
    pub wave_stage: String,
    pub transition_warnings: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct Metrics {
    pub periods: usize,
    pub dif: f64,
    pub dea: f64,
    pub spread: f64,
    pub previous_spread: f64,
    pub hist_change_rate: f64,
    pub dif_slope_5: f64,
    pub dif_zero_distance_ratio: f64,
    pub dif_max_20: f64,
    pub state_machine_state: String,
    pub state_machine_wave_index: i32,
    pub state_machine_valid_odd_wave_count: i32,
    pub even_repair_started: bool,
    pub golden_cross_imminent: bool,
    pub state_machine_reason: String,
    pub h: Option<f64>,
    pub l: Option<f64>,
    pub baseline_h: Option<f64>,
    pub pre_odd_macd_max: Option<f64>,
    pub current_wave_macd_max: Option<f64>,
    pub current_even_macd_min: Option<f64>,
    pub current_even_l: Option<f64>,
    pub prev_even_l: Option<f64>,
    pub bottom_divergence_valid: Option<bool>,
}

#[derive(Debug, Clone, PartialEq)]
struct StateMachineResult {
    current_state: String,
    current_wave_index: i32,
    valid_odd_wave_count: i32,
    h: Option<f64>,
    l: Option<f64>,
    baseline_h: Option<f64>,
    pre_odd_macd_max: Option<f64>,
    current_wave_macd_max: Option<f64>,
    current_even_macd_min: Option<f64>,
    current_even_l: Option<f64>,
    prev_even_l: Option<f64>,
    even_repair_started: bool,
    golden_cross_imminent: bool,
    bottom_divergence_valid: Option<bool>,
    events: Vec<String>,
    reason: String,
}

pub fn classify_daily_macd_trend(history: &[PreparedRow]) -> MacdTrendState {
    let dif = history.iter().map(|row| row.dif).collect::<Vec<_>>();
    let dea = history.iter().map(|row| row.dea).collect::<Vec<_>>();
    classify_macd_trend_with_state_machine_from_lines(&dif, &dea)
}

pub fn classify_weekly_macd_trend(history: &[PreparedRow]) -> MacdTrendState {
    let closes = weekly_close(history)
        .into_iter()
        .map(|(_date, close)| close)
        .collect::<Vec<_>>();
    let (dif, dea, _hist) = macd(&closes, 12, 26, 9);
    classify_macd_trend_with_state_machine_from_lines(&dif, &dea)
}

pub fn describe_macd_trend_state(label: &str, trend: &MacdTrendState) -> String {
    let phase_text = match trend.phase.as_str() {
        "rising" => "上升浪",
        "falling" => "下跌浪",
        "idle" => "等待启动",
        "ended" => "波段结束",
        _ => "状态无效",
    };
    let mut extras = Vec::new();
    let wave_label = if trend.wave_label.is_empty() {
        macd_wave_label(trend.phase_index)
    } else {
        trend.wave_label.clone()
    };
    if !wave_label.is_empty() || !trend.wave_stage.is_empty() {
        extras.push(format!("{wave_label}{}", trend.wave_stage));
    }
    if trend.is_rising_initial {
        extras.push("上升初期".to_string());
    }
    if trend.is_top_divergence {
        extras.push("顶背离风险".to_string());
    }
    let suffix = if extras.is_empty() {
        String::new()
    } else {
        format!("（{}）", extras.join("、"))
    };
    format!("{label}MACD{phase_text}{suffix}")
}

pub fn is_constructive_macd_trend_combo(weekly: &MacdTrendState, daily: &MacdTrendState) -> bool {
    if ["invalid", "ended"].contains(&weekly.phase.as_str())
        || ["invalid", "ended"].contains(&daily.phase.as_str())
    {
        return false;
    }
    if weekly.is_top_divergence || daily.is_top_divergence {
        return false;
    }
    if weekly.phase == "rising" && daily.phase == "rising" && daily.is_rising_initial {
        return true;
    }
    weekly.phase == "rising" && daily.phase == "falling"
}

pub fn map_b2_macd_phase_score(
    history_len: usize,
    weekly: &MacdTrendState,
    daily: &MacdTrendState,
    environment_state: &str,
) -> f64 {
    if history_len < 60 {
        return 3.0;
    }
    if environment_state == "weak" || environment_state == "neutral" {
        return score_b2_macd_state_machine_combo_with_fake_weekly(daily, environment_state);
    }
    score_b2_macd_state_machine_combo(weekly, daily, environment_state)
}

fn classify_macd_trend_with_state_machine_from_lines(dif: &[f64], dea: &[f64]) -> MacdTrendState {
    let baseline = classify_macd_trend_from_lines(dif, dea);
    let state = classify_macd_state_from_lines(dif, dea);
    if state.current_state == "invalid" {
        return baseline;
    }
    if state.events.is_empty() && state.current_wave_index <= 0 {
        return baseline;
    }
    let (phase, direction, phase_index, state_stage) = map_state_machine_trend_fields(&state);
    if phase == "invalid" {
        return baseline;
    }
    let wave_stage = resolve_state_machine_wave_stage(&state_stage, &baseline.wave_stage);
    let mut metrics = baseline.metrics.clone();
    apply_state_machine_metrics(&mut metrics, &state);
    MacdTrendState {
        phase,
        direction,
        is_rising_initial: is_state_machine_rising_initial(&state, phase_index),
        is_top_divergence: is_state_machine_top_divergence(&state, &baseline),
        bars_in_phase: baseline.bars_in_phase,
        phase_index,
        reason: state.reason.clone(),
        metrics,
        wave_label: wave_label(phase_index),
        wave_direction: if phase_index % 2 == 1 && phase_index > 0 {
            "rising".to_string()
        } else if phase_index > 0 {
            "falling".to_string()
        } else {
            "neutral".to_string()
        },
        wave_stage,
        transition_warnings: state_machine_transition_warnings(&state, &baseline),
    }
}

fn classify_macd_state_from_lines(dif_input: &[f64], dea_input: &[f64]) -> StateMachineResult {
    let mut dif = Vec::new();
    let mut dea = Vec::new();
    for (&d, &e) in dif_input.iter().zip(dea_input.iter()) {
        if d.is_finite() && e.is_finite() {
            dif.push(d);
            dea.push(e);
        }
    }
    if dif.len() < MIN_TREND_PERIODS {
        return invalid_state_machine_result("insufficient MACD history");
    }
    let hist2 = dif
        .iter()
        .zip(dea.iter())
        .map(|(d, e)| (d - e) * 2.0)
        .collect::<Vec<_>>();

    let mut state = "waiting_underwater".to_string();
    let mut current_wave_index = 0_i32;
    let mut valid_odd_wave_count = 0_i32;
    let mut h = None;
    let mut l = None;
    let mut baseline_h = None;
    let mut pre_odd_macd_max = None;
    let mut pre_odd_dead_crossed = false;
    let mut current_wave_macd_max = None;
    let mut current_even_macd_min = None;
    let mut current_even_l = None;
    let mut prev_even_l = None;
    let mut even_repair_started = false;
    let mut golden_cross_imminent = false;
    let mut bottom_divergence_valid = None;
    let mut events = Vec::new();
    let mut reason = "waiting for underwater golden cross".to_string();
    let mut has_prior_completed_red_segment = false;
    let mut positive_segment_active = false;

    for idx in 1..dif.len() {
        let prev_macd = hist2[idx - 1];
        let curr_macd = hist2[idx];
        let prev_dif = dif[idx - 1];
        let curr_dif = dif[idx];
        let curr_dea = dea[idx];
        let prev_dea = dea[idx - 1];

        if is_positive_macd_peak(&hist2, idx - 1) {
            h = Some(prev_macd);
        }
        if is_nonpositive_macd_valley(&hist2, idx - 1) {
            l = Some(prev_macd);
            if state == "even_wave_forming" || state == "pre_odd_adjusting" {
                current_even_l = Some(prev_macd);
            }
        }

        let underwater_golden_cross =
            prev_dif <= prev_dea && curr_dif > curr_dea && curr_dif < 0.0 && curr_dea < 0.0;
        let above_golden_cross =
            prev_dif <= prev_dea && curr_dif > curr_dea && curr_dea > 0.0 && curr_macd > 0.0;
        let dead_cross_event = prev_macd > 0.0 && curr_macd <= 0.0 && prev_dif > prev_dea;
        let dea_reentered_underwater = prev_dea > 0.0 && curr_dea <= 0.0;
        let dea_crossed_above_zero = prev_dea <= 0.0 && curr_dea > 0.0;

        if curr_macd > 0.0 {
            positive_segment_active = true;
        } else if positive_segment_active && curr_macd <= 0.0 {
            has_prior_completed_red_segment = true;
            positive_segment_active = false;
        }

        if dea_reentered_underwater && state != "waiting_underwater" && state != "pre_wave1_pushing"
        {
            end_cycle(
                "dea crossed below zero",
                &mut state,
                &mut current_wave_index,
                &mut h,
                &mut l,
                &mut baseline_h,
                &mut pre_odd_macd_max,
                &mut pre_odd_dead_crossed,
                &mut current_wave_macd_max,
                &mut current_even_macd_min,
                &mut current_even_l,
                &mut even_repair_started,
                &mut golden_cross_imminent,
                &mut bottom_divergence_valid,
                &mut events,
                &mut reason,
            );
            continue;
        }

        if state == "waiting_underwater" {
            if underwater_golden_cross {
                reason =
                    "underwater golden cross observed while waiting for dea above zero".to_string();
                events.push("underwater_gc_observed".to_string());
            }
            if dea_crossed_above_zero {
                if !has_prior_completed_red_segment {
                    state = "odd_wave_forming".to_string();
                    current_wave_index = 1;
                    valid_odd_wave_count += 1;
                    current_wave_macd_max = Some(curr_macd);
                    reason = "first dea-above-zero push without prior red peak counts as wave1"
                        .to_string();
                    events.push("odd_wave_confirmed".to_string());
                } else {
                    state = "pre_wave1_pushing".to_string();
                    baseline_h = h;
                    pre_odd_macd_max = Some(curr_macd);
                    reason = "dea crossed above zero and started pre wave1 push".to_string();
                    events.push("pre_wave1_started".to_string());
                }
            }
            continue;
        }

        if state == "pre_wave1_pushing" || state == "pre_odd_pushing" {
            pre_odd_macd_max = Some(pre_odd_macd_max.map_or(curr_macd, |v: f64| v.max(curr_macd)));
            if baseline_h.is_some_and(|base| pre_odd_macd_max.unwrap_or(curr_macd) > base) {
                confirm_odd_wave(
                    "pre odd wave confirmed by macd_max above baseline_H",
                    &mut state,
                    &mut current_wave_index,
                    &mut valid_odd_wave_count,
                    &mut current_wave_macd_max,
                    pre_odd_macd_max,
                    &mut reason,
                    &mut events,
                );
                continue;
            }
            if dead_cross_event {
                if baseline_h.is_none() && pre_odd_macd_max.is_some() {
                    confirm_odd_wave(
                        "pre odd wave confirmed because no prior baseline_H exists",
                        &mut state,
                        &mut current_wave_index,
                        &mut valid_odd_wave_count,
                        &mut current_wave_macd_max,
                        pre_odd_macd_max,
                        &mut reason,
                        &mut events,
                    );
                    start_even_wave(
                        "valid odd wave ended with above-water dead cross",
                        curr_macd,
                        &mut state,
                        &mut current_wave_index,
                        &mut current_even_macd_min,
                        &mut current_even_l,
                        &mut even_repair_started,
                        &mut golden_cross_imminent,
                        &mut bottom_divergence_valid,
                        &mut reason,
                        &mut events,
                    );
                    continue;
                }
                if state == "pre_wave1_pushing" && dea_reentered_underwater {
                    end_cycle(
                        "pre wave1 failed adjustment invalidated by dea below zero",
                        &mut state,
                        &mut current_wave_index,
                        &mut h,
                        &mut l,
                        &mut baseline_h,
                        &mut pre_odd_macd_max,
                        &mut pre_odd_dead_crossed,
                        &mut current_wave_macd_max,
                        &mut current_even_macd_min,
                        &mut current_even_l,
                        &mut even_repair_started,
                        &mut golden_cross_imminent,
                        &mut bottom_divergence_valid,
                        &mut events,
                        &mut reason,
                    );
                    continue;
                }
                if state == "pre_odd_pushing" {
                    start_pre_odd_adjustment(
                        "pre odd failed and entered above-zero adjustment",
                        curr_macd,
                        &mut state,
                        &mut h,
                        &mut baseline_h,
                        &mut pre_odd_dead_crossed,
                        &mut current_even_macd_min,
                        &mut current_even_l,
                        &mut even_repair_started,
                        &mut golden_cross_imminent,
                        &mut bottom_divergence_valid,
                        pre_odd_macd_max,
                        &mut events,
                        &mut reason,
                    );
                    continue;
                }
                pre_odd_dead_crossed = true;
                if state == "pre_wave1_pushing" {
                    reason = "pre wave1 failed to exceed baseline_H".to_string();
                }
                continue;
            }
            if state == "pre_wave1_pushing" && pre_odd_dead_crossed && dea_reentered_underwater {
                end_cycle(
                    "pre wave1 failed adjustment invalidated by dea below zero",
                    &mut state,
                    &mut current_wave_index,
                    &mut h,
                    &mut l,
                    &mut baseline_h,
                    &mut pre_odd_macd_max,
                    &mut pre_odd_dead_crossed,
                    &mut current_wave_macd_max,
                    &mut current_even_macd_min,
                    &mut current_even_l,
                    &mut even_repair_started,
                    &mut golden_cross_imminent,
                    &mut bottom_divergence_valid,
                    &mut events,
                    &mut reason,
                );
                continue;
            }
            if curr_macd <= 0.0 && curr_dea > 0.0 && prev_macd > curr_macd {
                start_pre_odd_adjustment(
                    "pre odd failed and entered above-zero adjustment",
                    curr_macd,
                    &mut state,
                    &mut h,
                    &mut baseline_h,
                    &mut pre_odd_dead_crossed,
                    &mut current_even_macd_min,
                    &mut current_even_l,
                    &mut even_repair_started,
                    &mut golden_cross_imminent,
                    &mut bottom_divergence_valid,
                    pre_odd_macd_max,
                    &mut events,
                    &mut reason,
                );
            }
            continue;
        }

        if state == "pre_odd_adjusting" {
            current_even_macd_min =
                Some(current_even_macd_min.map_or(curr_macd, |v: f64| v.min(curr_macd)));
            golden_cross_imminent = false;
            update_even_repair_flags(
                idx,
                &hist2,
                curr_macd,
                curr_dea,
                current_even_macd_min,
                prev_even_l,
                &mut even_repair_started,
                &mut bottom_divergence_valid,
                &mut events,
                &mut reason,
            );
            if above_golden_cross {
                if current_even_macd_min.is_some() {
                    prev_even_l = current_even_macd_min;
                }
                even_repair_started = false;
                golden_cross_imminent = false;
                bottom_divergence_valid = None;
                state = "pre_odd_pushing".to_string();
                baseline_h = h;
                pre_odd_macd_max = Some(curr_macd);
                pre_odd_dead_crossed = false;
                reason = "above-water golden cross starts next pre odd push".to_string();
                events.push("pre_odd_repush_started".to_string());
            }
            continue;
        }

        if state == "odd_wave_forming" {
            current_wave_macd_max =
                Some(current_wave_macd_max.map_or(curr_macd, |v: f64| v.max(curr_macd)));
            if dead_cross_event {
                start_even_wave(
                    "valid odd wave ended with above-water dead cross",
                    curr_macd,
                    &mut state,
                    &mut current_wave_index,
                    &mut current_even_macd_min,
                    &mut current_even_l,
                    &mut even_repair_started,
                    &mut golden_cross_imminent,
                    &mut bottom_divergence_valid,
                    &mut reason,
                    &mut events,
                );
            }
            continue;
        }

        if state == "even_wave_forming" {
            current_even_macd_min =
                Some(current_even_macd_min.map_or(curr_macd, |v: f64| v.min(curr_macd)));
            golden_cross_imminent = false;
            if current_even_macd_min.is_some() && curr_macd <= 0.0 && curr_dea > 0.0 {
                update_even_repair_flags(
                    idx,
                    &hist2,
                    curr_macd,
                    curr_dea,
                    current_even_macd_min,
                    prev_even_l,
                    &mut even_repair_started,
                    &mut bottom_divergence_valid,
                    &mut events,
                    &mut reason,
                );
            }
            if even_repair_started && curr_dea > 0.0 && curr_macd < 0.0 && curr_macd.abs() <= 0.02 {
                golden_cross_imminent = true;
                reason = "golden cross imminent after even-wave repair".to_string();
                if events.last().map(String::as_str) != Some("golden_cross_imminent") {
                    events.push("golden_cross_imminent".to_string());
                }
            }
            if above_golden_cross {
                if current_even_macd_min.is_some() {
                    prev_even_l = current_even_macd_min;
                }
                current_even_macd_min = None;
                current_even_l = None;
                even_repair_started = false;
                golden_cross_imminent = false;
                bottom_divergence_valid = None;
                state = "pre_odd_pushing".to_string();
                baseline_h = h;
                pre_odd_macd_max = Some(curr_macd);
                pre_odd_dead_crossed = false;
                reason = "even wave ended with above-water golden cross".to_string();
                events.push("pre_odd_started".to_string());
            }
        }
    }

    if is_positive_macd_peak(&hist2, hist2.len() - 1) {
        h = hist2.last().copied();
    }
    if is_nonpositive_macd_valley(&hist2, hist2.len() - 1) {
        l = hist2.last().copied();
        if state == "even_wave_forming" {
            current_even_l = hist2.last().copied();
        }
    }

    StateMachineResult {
        current_state: state,
        current_wave_index,
        valid_odd_wave_count,
        h: round_optional(h),
        l: round_optional(l),
        baseline_h: round_optional(baseline_h),
        pre_odd_macd_max: round_optional(pre_odd_macd_max),
        current_wave_macd_max: round_optional(current_wave_macd_max),
        current_even_macd_min: round_optional(current_even_macd_min),
        current_even_l: round_optional(current_even_l),
        prev_even_l: round_optional(prev_even_l),
        even_repair_started,
        golden_cross_imminent,
        bottom_divergence_valid,
        events,
        reason,
    }
}

fn classify_macd_trend_from_lines(dif_input: &[f64], dea_input: &[f64]) -> MacdTrendState {
    let mut dif = Vec::new();
    let mut dea = Vec::new();
    for (&d, &e) in dif_input.iter().zip(dea_input.iter()) {
        if d.is_finite() && e.is_finite() {
            dif.push(d);
            dea.push(e);
        }
    }
    if dif.len() < MIN_TREND_PERIODS {
        return invalid_trend_state("insufficient MACD history", dif.len());
    }
    let spread = dif
        .iter()
        .zip(dea.iter())
        .map(|(d, e)| d - e)
        .collect::<Vec<_>>();
    if dif.len() >= 10 && is_churn(&spread[spread.len() - 10..]) {
        let recent_above_zero_run = dif[dif.len() - 10..]
            .iter()
            .zip(dea[dea.len() - 10..].iter())
            .filter(|(d, e)| **d > 0.0 && **e > 0.0)
            .count()
            >= 5;
        if !recent_above_zero_run {
            return invalid_trend_state("MACD trend churn", dif.len());
        }
    }

    let mut machine = "waiting_underwater_cross".to_string();
    let mut phase = "idle".to_string();
    let mut reason = "waiting for underwater golden cross".to_string();
    let mut bars_in_phase = 0_usize;
    let mut phase_index = 0_i32;
    let mut last_completed_phase = "idle".to_string();
    let mut last_completed_reason = reason.clone();

    for idx in 1..dif.len() {
        let prev_dif = dif[idx - 1];
        let prev_dea = dea[idx - 1];
        let current_dif = dif[idx];
        let current_dea = dea[idx];
        let above_water = current_dif > 0.0 && current_dea > 0.0;
        let underwater_golden_cross = prev_dif <= prev_dea
            && current_dif > current_dea
            && current_dif < 0.0
            && current_dea < 0.0;
        let above_dead_cross = prev_dif >= prev_dea && current_dif < current_dea && above_water;
        let above_golden_cross = prev_dif <= prev_dea && current_dif > current_dea && above_water;

        if (phase == "rising" || phase == "falling") && current_dif < 0.0 {
            phase = "ended".to_string();
            last_completed_phase = "ended".to_string();
            last_completed_reason = "DIF crossed below zero".to_string();
            machine = "waiting_underwater_cross".to_string();
            bars_in_phase = 0;
            phase_index = 0;
            reason = "DIF crossed below zero".to_string();
            continue;
        }

        if machine == "waiting_underwater_cross" {
            if (phase == "ended" || phase == "idle") && above_water {
                machine = "running".to_string();
                if current_dif > current_dea {
                    phase = "rising".to_string();
                    reason = "above-zero recovery into MACD rising segment".to_string();
                    phase_index = 1;
                } else {
                    phase = "falling".to_string();
                    reason = "above-zero recovery into MACD falling segment".to_string();
                    phase_index = 2;
                }
                bars_in_phase = 1;
                continue;
            }
            if underwater_golden_cross {
                machine = "waiting_above_zero".to_string();
                phase = last_completed_phase.clone();
                reason = if last_completed_phase == "idle" {
                    "waiting for both MACD lines above zero".to_string()
                } else {
                    last_completed_reason.clone()
                };
            }
            continue;
        }

        if machine == "waiting_above_zero" {
            if current_dif < current_dea {
                machine = "waiting_underwater_cross".to_string();
                phase = last_completed_phase.clone();
                reason = last_completed_reason.clone();
                continue;
            }
            if above_water {
                machine = "running".to_string();
                phase = "rising".to_string();
                reason = "upward MACD segment after zero-axis confirmation".to_string();
                bars_in_phase = 1;
                phase_index = 1;
                continue;
            }
            reason = if last_completed_phase == "idle" {
                "waiting for both MACD lines above zero".to_string()
            } else {
                last_completed_reason.clone()
            };
            continue;
        }

        if machine == "running" {
            bars_in_phase += 1;
            if phase == "rising" && above_dead_cross {
                phase = "falling".to_string();
                reason = "above-water MACD dead cross".to_string();
                bars_in_phase = 1;
                phase_index += 1;
            } else if phase == "falling" && above_golden_cross {
                phase = "rising".to_string();
                reason = "above-water MACD golden cross".to_string();
                bars_in_phase = 1;
                phase_index += 1;
            }
        }
    }

    let latest_dif = *dif.last().unwrap();
    let latest_dea = *dea.last().unwrap();
    let latest_spread = latest_dif - latest_dea;
    let previous_spread = dif[dif.len() - 2] - dea[dea.len() - 2];
    let direction = if phase == "rising" || phase == "falling" {
        phase.clone()
    } else {
        "neutral".to_string()
    };
    let current_wave_label = if phase == "rising" || phase == "falling" {
        wave_label(phase_index)
    } else {
        String::new()
    };
    let wave_direction = if phase_index % 2 == 1 && phase_index > 0 {
        "rising"
    } else if phase_index > 0 {
        "falling"
    } else {
        "neutral"
    }
    .to_string();
    let (wave_stage, mut metrics) = judge_wave_stage(&dif, &dea, &phase, bars_in_phase);
    let transition_warnings = detect_stage_transition(&dif, &dea, &wave_stage, &phase);
    let is_top_divergence =
        phase == "rising" && (latest_spread < previous_spread || wave_stage == "背离");
    metrics.periods = dif.len();
    metrics.dif = latest_dif;
    metrics.dea = latest_dea;
    metrics.spread = round6(latest_spread);
    metrics.previous_spread = round6(previous_spread);
    MacdTrendState {
        phase: phase.clone(),
        direction,
        is_rising_initial: phase == "rising" && (1..=RISING_INITIAL_BARS).contains(&bars_in_phase),
        is_top_divergence,
        bars_in_phase,
        phase_index,
        reason,
        metrics,
        wave_label: current_wave_label,
        wave_direction,
        wave_stage,
        transition_warnings,
    }
}

fn judge_wave_stage(
    dif: &[f64],
    dea: &[f64],
    phase: &str,
    bars_in_phase: usize,
) -> (String, Metrics) {
    if phase != "rising" && phase != "falling" {
        return (String::new(), Metrics::default());
    }
    let hist_abs = dif
        .iter()
        .zip(dea.iter())
        .map(|(d, e)| ((d - e) * 2.0).abs())
        .collect::<Vec<_>>();
    if dif.len() < 10 {
        return (
            "分歧".to_string(),
            Metrics {
                hist_change_rate: 0.0,
                dif_slope_5: 0.0,
                dif_zero_distance_ratio: 0.0,
                ..Metrics::default()
            },
        );
    }
    let recent_avg = mean(&hist_abs[hist_abs.len() - 5..]);
    let prior_avg = mean(&hist_abs[hist_abs.len() - 10..hist_abs.len() - 5]);
    let latest_hist_abs = *hist_abs.last().unwrap();
    let previous_hist_abs = hist_abs[hist_abs.len() - 2];
    let hist_change_rate = if prior_avg.abs() <= 1e-12 {
        if recent_avg.abs() <= 1e-12 { 0.0 } else { 1.0 }
    } else {
        (recent_avg - prior_avg) / prior_avg.abs()
    };
    let latest_dif = *dif.last().unwrap();
    let dif_slope_5 = (latest_dif - dif[dif.len() - 6]) / 5.0;
    let max_abs_dif_20 = dif[dif.len().saturating_sub(20)..]
        .iter()
        .map(|value| value.abs())
        .fold(0.0, f64::max);
    let dif_zero_distance_ratio = if max_abs_dif_20 > 1e-12 {
        latest_dif.abs() / max_abs_dif_20
    } else {
        0.0
    };
    let stage = if phase == "rising" {
        let tail_start = hist_abs.len().saturating_sub(10);
        let is_new_hist_peak =
            latest_hist_abs >= hist_abs[tail_start..].iter().copied().fold(0.0, f64::max) * 0.98;
        if hist_change_rate > 0.05 && latest_hist_abs < previous_hist_abs && !is_new_hist_peak {
            "背离"
        } else if bars_in_phase > 5 && is_recent_hist_flattening(&hist_abs) {
            if hist_change_rate > 0.05 {
                "强势转分歧"
            } else {
                "分歧"
            }
        } else if hist_change_rate > 0.05 && dif_slope_5 > 0.001 && dif_zero_distance_ratio > 0.6 {
            "强势"
        } else if hist_change_rate < -0.05 {
            "背离"
        } else {
            "分歧"
        }
    } else if bars_in_phase > 5 && is_recent_hist_flattening(&hist_abs) {
        if hist_change_rate > 0.05 {
            "强势转分歧"
        } else {
            "分歧"
        }
    } else if hist_change_rate > 0.05 && dif_slope_5 < -0.001 {
        "强势"
    } else if hist_change_rate < -0.05 {
        "背离"
    } else {
        "分歧"
    };
    (
        stage.to_string(),
        Metrics {
            hist_change_rate: round6(hist_change_rate),
            dif_slope_5: round6(dif_slope_5),
            dif_zero_distance_ratio: round6(dif_zero_distance_ratio),
            dif_max_20: max_abs_dif_20,
            ..Metrics::default()
        },
    )
}

fn detect_stage_transition(
    dif: &[f64],
    dea: &[f64],
    current_stage: &str,
    phase: &str,
) -> Vec<String> {
    if phase != "rising" && phase != "falling" {
        return Vec::new();
    }
    let hist_abs = dif
        .iter()
        .zip(dea.iter())
        .map(|(d, e)| ((d - e) * 2.0).abs())
        .collect::<Vec<_>>();
    let mut warnings = Vec::new();
    if hist_abs.len() >= 4 {
        let last4 = &hist_abs[hist_abs.len() - 4..];
        let deltas = (1..last4.len())
            .map(|idx| last4[idx] - last4[idx - 1])
            .collect::<Vec<_>>();
        let max_hist = hist_abs[hist_abs.len().saturating_sub(10)..]
            .iter()
            .copied()
            .fold(0.0, f64::max)
            .max(1e-12);
        let flat_threshold = max_hist * 0.05;
        if current_stage == "强势"
            && (deltas.iter().all(|delta| *delta < 0.0)
                || deltas.iter().all(|delta| delta.abs() <= flat_threshold))
        {
            warnings.push("强势→分歧预警".to_string());
        }
        if current_stage == "背离" && deltas.iter().all(|delta| *delta > 0.0) {
            warnings.push("背离→分歧预警（反弹）".to_string());
        }
        if (current_stage == "分歧" || current_stage == "背离")
            && deltas.iter().all(|delta| *delta < 0.0)
        {
            warnings.push("强势→分歧预警".to_string());
        }
    }
    if hist_abs.len() >= 5 {
        let mean_hist = mean(&hist_abs[hist_abs.len() - 5..]);
        let latest_gap = (dif[dif.len() - 1] - dea[dea.len() - 1]).abs();
        if mean_hist > 1e-12 && latest_gap < 0.25 * mean_hist {
            warnings.push("金叉/死叉临近，浪型可能切换".to_string());
        }
    }
    warnings
}

fn map_state_machine_trend_fields(state: &StateMachineResult) -> (String, String, i32, String) {
    let mut wave_index = state.current_wave_index;
    match state.current_state.as_str() {
        "odd_wave_forming" => {
            if wave_index <= 0 {
                wave_index = 1;
            }
            (
                "rising".to_string(),
                "rising".to_string(),
                wave_index,
                "启动".to_string(),
            )
        }
        "even_wave_forming" => {
            if wave_index <= 0 {
                wave_index = 2;
            }
            let stage = if state.golden_cross_imminent {
                "金叉临近"
            } else if state.even_repair_started {
                "修复"
            } else {
                "调整"
            };
            (
                "falling".to_string(),
                "falling".to_string(),
                wave_index,
                stage.to_string(),
            )
        }
        "pre_odd_pushing" | "pre_wave1_pushing" => {
            let mut next_wave = if wave_index <= 0 { 1 } else { wave_index + 1 };
            if next_wave % 2 == 0 {
                next_wave += 1;
            }
            (
                "rising".to_string(),
                "rising".to_string(),
                next_wave,
                "预启动".to_string(),
            )
        }
        "pre_odd_adjusting" => {
            if wave_index <= 0 {
                wave_index = 2;
            }
            let stage = if state.even_repair_started {
                "修复"
            } else {
                "调整"
            };
            (
                "falling".to_string(),
                "falling".to_string(),
                wave_index,
                stage.to_string(),
            )
        }
        "waiting_underwater" => (
            "idle".to_string(),
            "neutral".to_string(),
            0,
            "等待启动".to_string(),
        ),
        _ => (
            "invalid".to_string(),
            "neutral".to_string(),
            0,
            String::new(),
        ),
    }
}

fn resolve_state_machine_wave_stage(state_stage: &str, baseline_stage: &str) -> String {
    if ["修复", "金叉临近", "等待启动"].contains(&state_stage) || baseline_stage.is_empty()
    {
        state_stage.to_string()
    } else {
        baseline_stage.to_string()
    }
}

fn apply_state_machine_metrics(metrics: &mut Metrics, state: &StateMachineResult) {
    metrics.state_machine_state = state.current_state.clone();
    metrics.state_machine_wave_index = state.current_wave_index;
    metrics.state_machine_valid_odd_wave_count = state.valid_odd_wave_count;
    metrics.even_repair_started = state.even_repair_started;
    metrics.golden_cross_imminent = state.golden_cross_imminent;
    metrics.state_machine_reason = state.reason.clone();
    metrics.h = state.h;
    metrics.l = state.l;
    metrics.baseline_h = state.baseline_h;
    metrics.pre_odd_macd_max = state.pre_odd_macd_max;
    metrics.current_wave_macd_max = state.current_wave_macd_max;
    metrics.current_even_macd_min = state.current_even_macd_min;
    metrics.current_even_l = state.current_even_l;
    metrics.prev_even_l = state.prev_even_l;
    metrics.bottom_divergence_valid = state.bottom_divergence_valid;
}

fn is_state_machine_rising_initial(state: &StateMachineResult, phase_index: i32) -> bool {
    if state.current_state == "pre_odd_pushing" || state.current_state == "pre_wave1_pushing" {
        return true;
    }
    state.current_state == "odd_wave_forming" && (phase_index == 1 || phase_index == 3)
}

fn is_state_machine_top_divergence(state: &StateMachineResult, baseline: &MacdTrendState) -> bool {
    if state.current_state != "odd_wave_forming" {
        return false;
    }
    baseline.is_top_divergence
}

fn state_machine_transition_warnings(
    state: &StateMachineResult,
    baseline: &MacdTrendState,
) -> Vec<String> {
    let mut warnings = baseline.transition_warnings.clone();
    if state.golden_cross_imminent {
        warnings.push("金叉临近，奇数浪可能启动".to_string());
    }
    if state.bottom_divergence_valid == Some(true) {
        warnings.push("偶数浪底背离有效".to_string());
    }
    if state.bottom_divergence_valid == Some(false) {
        warnings.push("偶数浪底背离无效".to_string());
    }
    let mut seen = std::collections::BTreeSet::new();
    warnings
        .into_iter()
        .filter(|item| seen.insert(item.clone()))
        .collect()
}

fn end_cycle(
    end_reason: &str,
    state: &mut String,
    current_wave_index: &mut i32,
    h: &mut Option<f64>,
    l: &mut Option<f64>,
    baseline_h: &mut Option<f64>,
    pre_odd_macd_max: &mut Option<f64>,
    pre_odd_dead_crossed: &mut bool,
    current_wave_macd_max: &mut Option<f64>,
    current_even_macd_min: &mut Option<f64>,
    current_even_l: &mut Option<f64>,
    even_repair_started: &mut bool,
    golden_cross_imminent: &mut bool,
    bottom_divergence_valid: &mut Option<bool>,
    events: &mut Vec<String>,
    reason: &mut String,
) {
    if state != "waiting_underwater" && events.last().map(String::as_str) != Some("cycle_ended") {
        events.push("cycle_ended".to_string());
    }
    *state = "waiting_underwater".to_string();
    *current_wave_index = 0;
    *h = None;
    *l = None;
    *baseline_h = None;
    *pre_odd_macd_max = None;
    *pre_odd_dead_crossed = false;
    *current_wave_macd_max = None;
    *current_even_macd_min = None;
    *current_even_l = None;
    *even_repair_started = false;
    *golden_cross_imminent = false;
    *bottom_divergence_valid = None;
    *reason = end_reason.to_string();
}

fn confirm_odd_wave(
    confirm_reason: &str,
    state: &mut String,
    current_wave_index: &mut i32,
    valid_odd_wave_count: &mut i32,
    current_wave_macd_max: &mut Option<f64>,
    pre_odd_macd_max: Option<f64>,
    reason: &mut String,
    events: &mut Vec<String>,
) {
    *state = "odd_wave_forming".to_string();
    *current_wave_index = if *current_wave_index == 0 {
        1
    } else {
        *current_wave_index + 1
    };
    if *current_wave_index % 2 == 0 {
        *current_wave_index += 1;
    }
    *valid_odd_wave_count += 1;
    *current_wave_macd_max = pre_odd_macd_max;
    *reason = confirm_reason.to_string();
    events.push("odd_wave_confirmed".to_string());
}

fn start_even_wave(
    start_reason: &str,
    curr_macd: f64,
    state: &mut String,
    current_wave_index: &mut i32,
    current_even_macd_min: &mut Option<f64>,
    current_even_l: &mut Option<f64>,
    even_repair_started: &mut bool,
    golden_cross_imminent: &mut bool,
    bottom_divergence_valid: &mut Option<bool>,
    reason: &mut String,
    events: &mut Vec<String>,
) {
    *state = "even_wave_forming".to_string();
    *current_wave_index += 1;
    *current_even_macd_min = Some(curr_macd);
    *current_even_l = None;
    *even_repair_started = false;
    *golden_cross_imminent = false;
    *bottom_divergence_valid = None;
    *reason = start_reason.to_string();
    events.push("even_wave_started".to_string());
}

fn start_pre_odd_adjustment(
    adjust_reason: &str,
    curr_macd: f64,
    state: &mut String,
    h: &mut Option<f64>,
    baseline_h: &mut Option<f64>,
    pre_odd_dead_crossed: &mut bool,
    current_even_macd_min: &mut Option<f64>,
    current_even_l: &mut Option<f64>,
    even_repair_started: &mut bool,
    golden_cross_imminent: &mut bool,
    bottom_divergence_valid: &mut Option<bool>,
    pre_odd_macd_max: Option<f64>,
    events: &mut Vec<String>,
    reason: &mut String,
) {
    *state = "pre_odd_adjusting".to_string();
    *current_even_macd_min = Some(curr_macd);
    *current_even_l = None;
    *even_repair_started = false;
    *golden_cross_imminent = false;
    *bottom_divergence_valid = None;
    if pre_odd_macd_max.is_some_and(|value| value > 0.0) {
        *h = pre_odd_macd_max;
        *baseline_h = pre_odd_macd_max;
        events.push("pre_odd_failed_rebase_H".to_string());
    }
    *pre_odd_dead_crossed = false;
    *reason = adjust_reason.to_string();
}

fn update_even_repair_flags(
    idx: usize,
    hist2: &[f64],
    curr_macd: f64,
    curr_dea: f64,
    current_even_macd_min: Option<f64>,
    prev_even_l: Option<f64>,
    even_repair_started: &mut bool,
    bottom_divergence_valid: &mut Option<bool>,
    events: &mut Vec<String>,
    reason: &mut String,
) {
    let recent_negative_contracting = idx >= 3
        && hist2[idx - 2] <= 0.0
        && hist2[idx - 1] <= 0.0
        && curr_macd <= 0.0
        && curr_macd.abs() < hist2[idx - 1].abs()
        && hist2[idx - 1].abs() < hist2[idx - 2].abs();
    let first_negative_rebound_after_even_low = idx >= 2
        && hist2[idx - 1] <= 0.0
        && curr_macd <= 0.0
        && curr_macd > hist2[idx - 1]
        && hist2[idx - 1] <= hist2[idx - 2];
    if current_even_macd_min.is_some()
        && (recent_negative_contracting || first_negative_rebound_after_even_low)
        && curr_macd <= 0.0
        && curr_dea > 0.0
    {
        *even_repair_started = true;
        if let Some(prev) = prev_even_l {
            *bottom_divergence_valid = current_even_macd_min.map(|current| current > prev);
        }
        *reason = "even wave repair started".to_string();
        events.push("even_repair_started".to_string());
    }
}

fn score_b2_macd_state_machine_combo(
    weekly: &MacdTrendState,
    daily: &MacdTrendState,
    environment_state: &str,
) -> f64 {
    let daily_stage = derive_score_stage(daily);
    let weekly_stage = derive_score_stage(weekly);
    let daily_score = score_daily_stage(&daily_stage);
    let weekly_score = round2(daily_score * weekly_coefficient(&weekly_stage, environment_state));
    let combo_score = score_combo(&weekly_stage, &daily_stage, environment_state);
    let risk_adjustment = score_risk_adjustment(&weekly_stage, &daily_stage);
    let method_bias = score_b2_method_bias(&daily_stage);
    let raw_score = (weekly_score + daily_score + combo_score + risk_adjustment + method_bias)
        .clamp(0.0, 100.0);
    round2(1.0 + ((raw_score + 8.0).min(100.0) / 25.0))
}

fn score_b2_macd_state_machine_combo_with_fake_weekly(
    daily: &MacdTrendState,
    environment_state: &str,
) -> f64 {
    let daily_stage = derive_score_stage(daily);
    let weekly_stage = waiting_score_stage();
    let daily_score = score_daily_stage(&daily_stage);
    let weekly_score = round2(daily_score * weekly_coefficient(&weekly_stage, environment_state));
    let combo_score = score_combo(&weekly_stage, &daily_stage, environment_state);
    let risk_adjustment = score_risk_adjustment(&weekly_stage, &daily_stage);
    let method_bias = score_b2_method_bias(&daily_stage);
    let raw_score = (weekly_score + daily_score + combo_score + risk_adjustment + method_bias)
        .clamp(0.0, 100.0);
    round2(1.0 + ((raw_score + 8.0).min(100.0) / 25.0))
}

#[derive(Debug, Clone, PartialEq)]
struct ScoreStage {
    wave_cycle_phase: String,
    current_wave_index: i32,
    current_opportunity_phase: String,
    odd_push_stage: String,
    waiting_strength_tier: String,
    supports_first_even_repair_window: bool,
    bottom_divergence_valid: Option<bool>,
    top_divergence_level: String,
    risk_flags: Vec<String>,
    reason: String,
}

fn waiting_score_stage() -> ScoreStage {
    ScoreStage {
        wave_cycle_phase: "waiting".to_string(),
        current_wave_index: 0,
        current_opportunity_phase: "not_applicable".to_string(),
        odd_push_stage: "not_applicable".to_string(),
        waiting_strength_tier: "waiting_flat".to_string(),
        supports_first_even_repair_window: false,
        bottom_divergence_valid: None,
        top_divergence_level: "none".to_string(),
        risk_flags: Vec::new(),
        reason: "insufficient MACD history".to_string(),
    }
}

fn derive_score_stage(trend: &MacdTrendState) -> ScoreStage {
    let current_state = trend.metrics.state_machine_state.as_str();
    let wave_cycle_phase = match current_state {
        "waiting_underwater" => "waiting",
        "pre_odd_pushing" | "pre_wave1_pushing" => "pre_odd_pushing",
        "pre_odd_adjusting" => "pre_odd_adjusting",
        "odd_wave_forming" => "odd_confirmed",
        "even_wave_forming" if trend.metrics.even_repair_started => "even_repairing",
        "even_wave_forming" => "even_adjusting",
        _ => "waiting",
    }
    .to_string();
    let current_wave_index = if ["pre_odd_pushing", "pre_odd_adjusting"]
        .contains(&wave_cycle_phase.as_str())
        || (current_state == "even_wave_forming" && trend.metrics.golden_cross_imminent)
    {
        next_odd_wave_index(trend.metrics.state_machine_wave_index)
    } else {
        trend.metrics.state_machine_wave_index
    };
    let current_opportunity_phase =
        if current_state == "even_wave_forming" && trend.metrics.golden_cross_imminent {
            "pre_odd_imminent"
        } else if wave_cycle_phase == "pre_odd_pushing" {
            "pre_odd_starting"
        } else {
            "not_applicable"
        }
        .to_string();
    let odd_push_stage =
        if ["pre_odd_pushing", "odd_confirmed"].contains(&wave_cycle_phase.as_str()) {
            classify_odd_push_stage(trend.metrics.dif, trend.metrics.dea, trend.metrics.spread)
        } else {
            "not_applicable".to_string()
        };
    let waiting_strength_tier = classify_waiting_strength_tier(
        trend.metrics.dif,
        trend.metrics.dea,
        trend.metrics.spread,
        &wave_cycle_phase,
    );
    let supports_first_even_repair_window = wave_cycle_phase == "even_repairing"
        && trend.metrics.state_machine_wave_index == 2
        && trend.metrics.state_machine_valid_odd_wave_count == 1;
    let mut risk_flags = Vec::new();
    if wave_cycle_phase == "pre_odd_pushing" && trend.metrics.baseline_h.is_some() {
        risk_flags.push("baseline_pending".to_string());
    }
    if trend.metrics.bottom_divergence_valid == Some(false) {
        risk_flags.push("bottom_divergence_invalid".to_string());
    }
    let top_divergence_level = "none".to_string();
    ScoreStage {
        wave_cycle_phase,
        current_wave_index,
        current_opportunity_phase,
        odd_push_stage,
        waiting_strength_tier,
        supports_first_even_repair_window,
        bottom_divergence_valid: trend.metrics.bottom_divergence_valid,
        top_divergence_level,
        risk_flags,
        reason: trend.metrics.state_machine_reason.clone(),
    }
}

fn next_odd_wave_index(current_wave_index: i32) -> i32 {
    if current_wave_index <= 0 {
        1
    } else if current_wave_index % 2 == 0 {
        current_wave_index + 1
    } else {
        current_wave_index
    }
}

fn classify_odd_push_stage(latest_dif: f64, latest_dea: f64, latest_hist: f64) -> String {
    if 0.0 < latest_dea && latest_dea < latest_hist && 0.0 < latest_dif && latest_dif < latest_hist
    {
        "stage1_hist_dominant".to_string()
    } else if 0.0 < latest_dea && latest_dea < latest_hist && latest_hist < latest_dif {
        "stage2_line_extending".to_string()
    } else if latest_hist < latest_dea && latest_hist < latest_dif {
        "stage3_hist_lagging".to_string()
    } else {
        "not_applicable".to_string()
    }
}

fn classify_waiting_strength_tier(
    latest_dif: f64,
    latest_dea: f64,
    latest_hist: f64,
    wave_cycle_phase: &str,
) -> String {
    if wave_cycle_phase != "waiting" {
        return "not_applicable".to_string();
    }
    if latest_dif > 0.0 && latest_dea < 0.0 && latest_hist > 0.0 {
        "underwater_ready".to_string()
    } else if latest_dif < 0.0 && latest_dea < 0.0 && latest_hist > 0.0 {
        "underwater_strengthening".to_string()
    } else {
        "waiting_flat".to_string()
    }
}

fn classify_weekly_grade(stage: &ScoreStage) -> &'static str {
    match stage.wave_cycle_phase.as_str() {
        "cycle_ended" => "很差",
        "waiting" if stage.waiting_strength_tier == "underwater_ready" => "差",
        "waiting" => "很差",
        "even_adjusting" | "even_repairing" => "中",
        "pre_odd_adjusting" => "差",
        "pre_odd_pushing" => "很好",
        "odd_confirmed" => match stage.odd_push_stage.as_str() {
            "stage1_hist_dominant" => "很好",
            "stage2_line_extending" => "好",
            "stage3_hist_lagging" => "中",
            _ => "中",
        },
        _ => "很差",
    }
}

fn classify_daily_grade(stage: &ScoreStage) -> &'static str {
    match stage.wave_cycle_phase.as_str() {
        "cycle_ended" => "很差",
        "waiting" => "很差",
        "even_adjusting" => "差",
        _ if stage.current_opportunity_phase == "pre_odd_imminent" => {
            if stage.current_wave_index == 3 {
                "很好"
            } else {
                "好"
            }
        }
        "even_repairing" if stage.bottom_divergence_valid == Some(true) => "很好",
        "even_repairing" if stage.supports_first_even_repair_window => "好",
        "even_repairing" => "中",
        "pre_odd_pushing" => "好",
        "pre_odd_adjusting" => "中",
        "odd_confirmed" => match stage.odd_push_stage.as_str() {
            "stage1_hist_dominant" => "很好",
            "stage2_line_extending" => "好",
            "stage3_hist_lagging" => "中",
            _ => "中",
        },
        _ => "很差",
    }
}

fn weekly_coefficient(stage: &ScoreStage, environment_state: &str) -> f64 {
    let grade = classify_weekly_grade(stage);
    let mut score = match environment_state {
        "weak" => match grade {
            "很差" => 0.35,
            "差" => 0.5,
            "中" => 0.65,
            "好" => 0.8,
            "很好" => 0.9,
            _ => 0.35,
        },
        "strong" => match grade {
            "很差" => 0.7,
            "差" => 1.16,
            "中" => 1.08,
            "好" => 1.15,
            "很好" => 1.2,
            _ => 0.7,
        },
        _ => match grade {
            "很差" => 0.55,
            "差" => 0.7,
            "中" => 0.9,
            "好" => 1.1,
            "很好" => 1.15,
            _ => 0.55,
        },
    };
    if stage.wave_cycle_phase == "waiting"
        && stage.waiting_strength_tier == "underwater_strengthening"
    {
        score += 0.03;
    }
    if stage.wave_cycle_phase == "pre_odd_pushing" && stage.current_wave_index >= 4 {
        score -= 0.20;
    }
    if stage.bottom_divergence_valid == Some(true) {
        score += 0.05;
    } else if stage.bottom_divergence_valid == Some(false) {
        score -= 0.05;
    }
    score
}

fn score_daily_stage(stage: &ScoreStage) -> f64 {
    let table = |grade: &str| match grade {
        "很差" => 5.0,
        "差" => 10.0,
        "中" => 18.0,
        "好" => 22.0,
        "很好" => 28.0,
        _ => 5.0,
    };
    if stage.current_opportunity_phase == "pre_odd_imminent" {
        return table("很好")
            + if stage.current_wave_index == 3 {
                4.0
            } else {
                1.0
            };
    }
    if stage.wave_cycle_phase == "even_repairing" {
        if stage.bottom_divergence_valid == Some(true) {
            if stage.supports_first_even_repair_window {
                return table("好") + 3.0;
            }
            return table("中") + 2.0;
        }
        if stage.supports_first_even_repair_window {
            return table("好");
        }
        return table("中");
    }
    table(classify_daily_grade(stage))
}

fn score_combo(
    weekly_stage: &ScoreStage,
    daily_stage: &ScoreStage,
    environment_state: &str,
) -> f64 {
    if weekly_stage.wave_cycle_phase == "cycle_ended"
        || daily_stage.wave_cycle_phase == "cycle_ended"
    {
        return 0.0;
    }
    if daily_stage.current_opportunity_phase == "pre_odd_imminent"
        && daily_stage.current_wave_index == 3
    {
        if weekly_stage.wave_cycle_phase == "odd_confirmed"
            && weekly_stage.odd_push_stage == "stage1_hist_dominant"
        {
            let score = 18.0;
            return match environment_state {
                "weak" => score - 15.0,
                "strong" => score - 12.0,
                _ => score,
            };
        }
        if weekly_stage.wave_cycle_phase == "odd_confirmed"
            && weekly_stage.odd_push_stage == "stage3_hist_lagging"
        {
            let score = 8.0;
            return if environment_state == "strong" {
                score - 2.0
            } else {
                score
            };
        }
        if ["pre_odd_pushing", "even_repairing", "odd_confirmed"]
            .contains(&weekly_stage.wave_cycle_phase.as_str())
        {
            let mut score = 16.0;
            if weekly_stage.wave_cycle_phase == "pre_odd_pushing"
                && weekly_stage.current_wave_index >= 4
            {
                score = 6.0;
            }
            return match environment_state {
                "weak" => score - 15.0,
                "strong" => score - 4.0,
                _ => score,
            };
        }
    }
    if daily_stage.current_opportunity_phase == "pre_odd_imminent" && environment_state == "weak" {
        return 2.0;
    }
    if daily_stage.wave_cycle_phase == "even_repairing"
        && weekly_stage.wave_cycle_phase == "even_repairing"
    {
        return 10.0;
    }
    if daily_stage.wave_cycle_phase == "odd_confirmed"
        && daily_stage.odd_push_stage == "stage3_hist_lagging"
    {
        return 8.0;
    }
    6.0
}

fn score_risk_adjustment(weekly_stage: &ScoreStage, daily_stage: &ScoreStage) -> f64 {
    let mut score = 0.0;
    if daily_stage.bottom_divergence_valid == Some(true) {
        if daily_stage.current_opportunity_phase == "pre_odd_imminent" {
            score += 6.0;
        } else if daily_stage.supports_first_even_repair_window {
            score += 5.0;
        } else if daily_stage.wave_cycle_phase == "even_repairing" {
            score += 1.0;
        }
    }
    if daily_stage.bottom_divergence_valid == Some(false) {
        score -= 6.0;
    }
    if weekly_stage.wave_cycle_phase == "cycle_ended"
        || daily_stage.wave_cycle_phase == "cycle_ended"
    {
        score -= 10.0;
    }
    if weekly_stage.top_divergence_level == "B" || daily_stage.top_divergence_level == "B" {
        score -= 8.0;
    }
    if weekly_stage.current_wave_index >= 7 || daily_stage.current_wave_index >= 7 {
        score -= 7.0;
    }
    score
}

fn score_b2_method_bias(daily_stage: &ScoreStage) -> f64 {
    if daily_stage.current_opportunity_phase == "pre_odd_imminent"
        && daily_stage.current_wave_index == 3
    {
        2.0
    } else if daily_stage.wave_cycle_phase == "even_repairing" {
        1.0
    } else {
        0.0
    }
}

fn weekly_close(history: &[PreparedRow]) -> Vec<(NaiveDate, f64)> {
    let mut out: Vec<(NaiveDate, f64)> = Vec::new();
    let mut current_week: Option<(i32, u32)> = None;
    let pick_date = history.iter().map(|row| row.trade_date).max();
    for row in history.iter().filter(|row| row.close.is_finite()) {
        let week_end = week_ending_friday(row.trade_date);
        if pick_date.is_some_and(|pick| week_end > pick) {
            continue;
        }
        let iso = row.trade_date.iso_week();
        let week = (iso.year(), iso.week());
        if current_week != Some(week) {
            out.push((row.trade_date, row.close));
            current_week = Some(week);
        } else if let Some(last) = out.last_mut() {
            *last = (row.trade_date, row.close);
        }
    }
    out
}

fn week_ending_friday(date: NaiveDate) -> NaiveDate {
    let weekday = date.weekday().num_days_from_monday() as i64;
    let days_to_friday = if weekday <= 4 {
        4 - weekday
    } else {
        11 - weekday
    };
    date + Duration::days(days_to_friday)
}

fn invalid_trend_state(reason: &str, periods: usize) -> MacdTrendState {
    MacdTrendState {
        phase: "invalid".to_string(),
        direction: "neutral".to_string(),
        is_rising_initial: false,
        is_top_divergence: false,
        bars_in_phase: 0,
        phase_index: 0,
        reason: reason.to_string(),
        metrics: Metrics {
            periods,
            ..Metrics::default()
        },
        wave_label: String::new(),
        wave_direction: "neutral".to_string(),
        wave_stage: String::new(),
        transition_warnings: Vec::new(),
    }
}

fn invalid_state_machine_result(reason: &str) -> StateMachineResult {
    StateMachineResult {
        current_state: "invalid".to_string(),
        current_wave_index: 0,
        valid_odd_wave_count: 0,
        h: None,
        l: None,
        baseline_h: None,
        pre_odd_macd_max: None,
        current_wave_macd_max: None,
        current_even_macd_min: None,
        current_even_l: None,
        prev_even_l: None,
        even_repair_started: false,
        golden_cross_imminent: false,
        bottom_divergence_valid: None,
        events: Vec::new(),
        reason: reason.to_string(),
    }
}

fn is_positive_macd_peak(values: &[f64], idx: usize) -> bool {
    if idx == 0 || idx >= values.len().saturating_sub(1) {
        return false;
    }
    values[idx] > 0.0 && values[idx] >= values[idx - 1] && values[idx] >= values[idx + 1]
}

fn is_nonpositive_macd_valley(values: &[f64], idx: usize) -> bool {
    if idx == 0 || idx >= values.len().saturating_sub(1) {
        return false;
    }
    values[idx] <= 0.0 && values[idx] <= values[idx - 1] && values[idx] <= values[idx + 1]
}

fn is_recent_hist_flattening(values: &[f64]) -> bool {
    if values.len() < 4 {
        return false;
    }
    let last4 = &values[values.len() - 4..];
    let latest = last4[3];
    let peak = last4.iter().copied().fold(0.0, f64::max);
    if peak <= 1e-12 {
        return false;
    }
    let last_delta = (last4[3] - last4[2]).abs() / peak;
    let prev_delta = (last4[2] - last4[1]).abs() / peak;
    let _ = latest;
    last_delta <= 0.08 || (last_delta <= 0.12 && prev_delta <= 0.12)
}

fn is_churn(hist: &[f64]) -> bool {
    let mut flips = 0;
    let mut previous: Option<i32> = None;
    for value in hist {
        let sign = if *value > 0.0 {
            1
        } else if *value < 0.0 {
            -1
        } else {
            0
        };
        if previous.is_some_and(|prev| prev != sign) {
            flips += 1;
        }
        previous = Some(sign);
    }
    flips >= 4
}

fn wave_label(phase_index: i32) -> String {
    match phase_index {
        1 => "一浪".to_string(),
        2 => "二浪".to_string(),
        3 => "三浪".to_string(),
        4 => "四浪".to_string(),
        5 => "五浪".to_string(),
        6 => "六浪".to_string(),
        7 => "七浪".to_string(),
        value if value > 0 => format!("第{value}浪"),
        _ => String::new(),
    }
}

fn macd_wave_label(phase_index: i32) -> String {
    wave_label(phase_index)
}

fn mean(values: &[f64]) -> f64 {
    if values.is_empty() {
        0.0
    } else {
        values.iter().sum::<f64>() / values.len() as f64
    }
}

fn round_optional(value: Option<f64>) -> Option<f64> {
    value.map(round6)
}

fn round2(value: f64) -> f64 {
    format!("{value:.2}")
        .parse::<f64>()
        .expect("formatted finite f64 should parse")
}

fn round6(value: f64) -> f64 {
    format!("{value:.6}")
        .parse::<f64>()
        .expect("formatted finite f64 should parse")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn weekly_close_keeps_last_trade_in_iso_week() {
        let rows = [
            row("000001.SZ", 2026, 5, 18, 10.0),
            row("000001.SZ", 2026, 5, 19, 11.0),
            row("000001.SZ", 2026, 5, 25, 12.0),
        ];
        assert_eq!(
            weekly_close(&rows),
            vec![(NaiveDate::from_ymd_opt(2026, 5, 19).unwrap(), 11.0)]
        );
    }

    fn row(code: &str, year: i32, month: u32, day: u32, close: f64) -> PreparedRow {
        PreparedRow {
            ts_code: code.to_string(),
            trade_date: NaiveDate::from_ymd_opt(year, month, day).unwrap(),
            open: close,
            high: close,
            low: close,
            close,
            volume: 1.0,
            turnover_n: 1.0,
            turnover_rate: Some(1.0),
            k: 50.0,
            d: 50.0,
            j: 50.0,
            zxdq: Some(close),
            zxdkx: Some(close),
            dif: 0.0,
            dea: 0.0,
            macd_hist: 0.0,
            ma25: Some(close),
            ma60: Some(close),
            ma144: Some(close),
            chg_d: Some(0.0),
            weekly_ma_bull: true,
            max_vol_not_bearish: true,
            v_shrink: true,
            safe_mode: true,
            lt_filter: true,
            db_factors: Default::default(),
        }
    }
}
