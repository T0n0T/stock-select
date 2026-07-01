use chrono::{Days, NaiveDate};

use crate::environment_profiles::get_method_environment_profile;
use crate::factors::ma::push_b2_long_trend_factors;
use crate::factors::macd::{macd_lines, push_b2_period_macd_factors};
use crate::factors::price_position::{
    latest_bar_position_ratio, push_b2_hl90_position_factors, push_latest_upper_shadow_factor,
};
use crate::factors::series::{
    pct_change, push_category, push_number, rolling_mean_series, FactorList,
};
use crate::factors::types::{FactorInputRow, FactorValue};
use crate::factors::zx::zx_lines;
use crate::macd_trends::{
    classify_daily_macd_trend, classify_weekly_macd_trend, is_constructive_macd_trend_combo,
    map_b2_macd_phase_score,
};
use crate::model::PreparedRow;
use crate::review_protocol::infer_signal_type;
use crate::reviewers::b2_scoring::{
    previous_abnormal_move_mode, price_position_mode, score_b2_previous_abnormal_move,
    score_b2_price_position, score_b2_trend_structure, score_b2_volume_behavior,
};
use crate::strategies::b2::build_b2_signal_series;

pub fn push_b2_semantic_factors(
    factors: &mut FactorList,
    history: &[FactorInputRow],
    signal: Option<&str>,
    environment_state: Option<&str>,
    latest_ma60: Option<f64>,
) {
    push_b2_rdagent_rank_factors(factors, history, latest_ma60);
    push_b2_family_semantic_factors(factors, history, signal, environment_state);
}

pub fn push_b3_semantic_factors(
    factors: &mut FactorList,
    history: &[FactorInputRow],
    signal: Option<&str>,
    environment_state: Option<&str>,
) {
    push_b2_family_semantic_factors(factors, history, signal, environment_state);
    push_b3_signal_context_factors(factors, history, signal);
}

pub fn push_lsh_semantic_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    if history.is_empty() {
        return;
    }

    push_rank_runtime_common_factors(factors, history);

    let prepared = prepared_rows(history);
    let daily_trend = classify_daily_macd_trend(&prepared);
    let weekly_trend = classify_weekly_macd_trend(&prepared);

    push_number(
        factors,
        "lsh_daily_macd_wave_index",
        Some(daily_trend.metrics.state_machine_wave_index as f64),
    );
    push_number(
        factors,
        "lsh_weekly_macd_wave_index",
        Some(weekly_trend.metrics.state_machine_wave_index as f64),
    );
    push_bool(
        factors,
        "lsh_daily_macd_rising_initial_flag",
        daily_trend.is_rising_initial,
    );
    push_bool(
        factors,
        "lsh_weekly_macd_rising_initial_flag",
        weekly_trend.is_rising_initial,
    );
    push_bool(
        factors,
        "lsh_daily_macd_top_divergence_flag",
        daily_trend.is_top_divergence,
    );
    push_bool(
        factors,
        "lsh_weekly_macd_top_divergence_flag",
        weekly_trend.is_top_divergence,
    );
    push_bool(
        factors,
        "lsh_weekly_daily_constructive_combo_flag",
        is_constructive_macd_trend_combo(&weekly_trend, &daily_trend),
    );
    push_lsh_bullish_engulfing_factors(factors, history);
}

pub fn push_rank_runtime_common_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    if history.is_empty() {
        return;
    }

    let prepared = prepared_rows(history);
    let daily_trend = classify_daily_macd_trend(&prepared);
    let weekly_trend = classify_weekly_macd_trend(&prepared);

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

    let close = prepared.iter().map(|row| row.close).collect::<Vec<_>>();
    let high = prepared.iter().map(|row| row.high).collect::<Vec<_>>();
    let low = prepared.iter().map(|row| row.low).collect::<Vec<_>>();
    let volume = prepared.iter().map(|row| row.volume).collect::<Vec<_>>();
    let ma25 = prepared.iter().map(|row| row.ma25).collect::<Vec<_>>();
    let zxdkx = prepared.iter().map(|row| row.zxdkx).collect::<Vec<_>>();

    let latest_close = close.last().copied();
    let latest_low = low.last().copied();
    let latest_ma25 = ma25.last().copied().flatten();
    let latest_zxdkx = zxdkx.last().copied().flatten();
    let previous_close = close.iter().rev().nth(1).copied();
    let previous_volume = volume.iter().rev().nth(1).copied();
    let previous_ma25 = ma25.iter().rev().nth(1).copied().flatten();
    let previous_zxdkx = zxdkx.iter().rev().nth(1).copied().flatten();
    let latest_zxdkx_for_model = latest_zxdkx.or(latest_ma25).or(latest_close);
    let previous_zxdkx_for_model = previous_zxdkx.or(previous_ma25).or(previous_close);
    let recent_high_90 = max_tail(&high, 90);
    let recent_low_90 = min_tail(&low, 90);
    let mid_90 = recent_high_90
        .zip(recent_low_90)
        .map(|(high, low)| (high + low) / 2.0);
    let recent_high_120 = max_tail(&high, 120);
    let recent_low_120 = min_tail(&low, 120);

    push_number(
        factors,
        "price_vs_90d_high",
        pct_change_option(latest_close, recent_high_90),
    );
    push_number(
        factors,
        "price_vs_90d_low",
        pct_change_option(latest_close, recent_low_90),
    );
    push_number(
        factors,
        "price_vs_90d_mid",
        pct_change_option(latest_close, mid_90),
    );
    push_number(
        factors,
        "close_to_zxdkx_pct",
        pct_change_option(latest_close, latest_zxdkx_for_model).or(Some(0.0)),
    );
    push_number(
        factors,
        "ma25_to_zxdkx_pct",
        pct_change_option(latest_ma25.or(latest_close), latest_zxdkx_for_model).or(Some(0.0)),
    );
    push_number(
        factors,
        "zxdkx_slope_5d_pct",
        tail_slope_pct(&zxdkx, 5)
            .or_else(|| tail_slope_pct(&ma25, 5))
            .or(Some(0.0)),
    );
    push_optional_bool(
        factors,
        "near_ma25_support_flag",
        latest_low
            .zip(latest_ma25)
            .map(|(low, ma25)| low <= ma25 * 1.03),
    );
    push_optional_bool(
        factors,
        "ma_aligned_flag",
        latest_close
            .zip(latest_ma25.zip(latest_zxdkx_for_model))
            .map(|(close, (ma25, zxdkx))| close >= ma25 && ma25 >= zxdkx),
    );
    push_optional_bool(
        factors,
        "zxdkx_up_1d_flag",
        latest_zxdkx_for_model
            .zip(previous_zxdkx_for_model)
            .map(|(latest, previous)| latest >= previous),
    );
    push_number(
        factors,
        "breakout_distance_120d_pct",
        pct_change_option(latest_close, recent_high_120),
    );
    push_number(
        factors,
        "range_floor_distance_120d_pct",
        pct_change_option(latest_close, recent_low_120),
    );
    push_number(
        factors,
        "range_compression_40d",
        range_compression_pct(&high, &low, latest_close, 40).or(Some(0.0)),
    );
    push_number(
        factors,
        "abnormal_volume_to_ma20_ratio",
        abnormal_volume_to_ma20_ratio(&volume).or(Some(0.0)),
    );
    push_optional_bool(
        factors,
        "price_up_1d_flag",
        latest_close
            .zip(previous_close)
            .map(|(latest, previous)| latest > previous),
    );
    push_optional_bool(
        factors,
        "volume_up_1d_flag",
        volume
            .last()
            .copied()
            .zip(previous_volume)
            .map(|(latest, previous)| latest > previous),
    );
}

fn push_lsh_bullish_engulfing_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    let latest = history.last();
    let previous = history.iter().rev().nth(1);
    let bullish_engulf = latest.zip(previous).is_some_and(|(latest, previous)| {
        previous.close < previous.open
            && latest.close > latest.open
            && latest.open <= previous.close
            && latest.close >= previous.open
    });
    let volume_ratio = latest.zip(previous).and_then(|(latest, previous)| {
        (previous.volume > 0.0).then_some(latest.volume / previous.volume)
    });
    let volume_bullish_engulf = bullish_engulf && volume_ratio.is_some_and(|ratio| ratio > 1.0);

    push_bool(
        factors,
        "lsh_bullish_engulf_prev_bearish_flag",
        bullish_engulf,
    );
    push_bool(
        factors,
        "lsh_volume_bullish_engulf_prev_bearish_flag",
        volume_bullish_engulf,
    );
    push_number(factors, "lsh_bullish_engulf_volume_ratio", volume_ratio);
}

fn push_b2_rdagent_rank_factors(
    factors: &mut FactorList,
    history: &[FactorInputRow],
    latest_ma60: Option<f64>,
) {
    if history.is_empty() {
        return;
    }
    let close = history.iter().map(|row| row.close).collect::<Vec<_>>();
    let high = history.iter().map(|row| row.high).collect::<Vec<_>>();
    let low = history.iter().map(|row| row.low).collect::<Vec<_>>();
    let latest = history.last();
    let latest_close = latest.map(|row| row.close);
    let latest_high = latest.map(|row| row.high);
    let latest_low = latest.map(|row| row.low);

    push_number(factors, "D", latest.and_then(|row| row.d));
    push_number(
        factors,
        "bar_close_position",
        latest_bar_position_ratio(latest_close, latest_low, latest_high),
    );
    push_b2_long_trend_factors(factors, &close, latest_close, latest_ma60);
    push_b2_hl90_position_factors(factors, &high, &low, latest_close);
    push_latest_upper_shadow_factor(factors, latest_high, latest_close);
    push_b2_period_macd_factors(factors, history);
    push_b2_bullish_engulfing_factors(factors, history);
}

fn push_b2_bullish_engulfing_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    let latest = history.last();
    let previous = history.iter().rev().nth(1);
    let bullish_engulf = latest.zip(previous).is_some_and(|(latest, previous)| {
        previous.close < previous.open
            && latest.close > latest.open
            && latest.open <= previous.close
            && latest.close >= previous.open
    });
    let volume_ratio = latest.zip(previous).and_then(|(latest, previous)| {
        (previous.volume > 0.0).then_some(latest.volume / previous.volume)
    });
    let volume_bullish_engulf = bullish_engulf && volume_ratio.is_some_and(|ratio| ratio > 1.0);
    let latest_ma25 = latest.and_then(|row| row.ma25).or_else(|| {
        let close = history.iter().map(|row| row.close).collect::<Vec<_>>();
        rolling_mean_series(&close, 25, 25)
            .last()
            .copied()
            .flatten()
    });
    let above_ma25 = latest
        .zip(latest_ma25)
        .is_some_and(|(latest, ma25)| latest.close > ma25);
    let ma25_volume_bullish_engulf = volume_bullish_engulf && above_ma25;
    let body_pct = latest.and_then(|latest| pct_change(Some(latest.close), Some(latest.open)));
    let strength = match (ma25_volume_bullish_engulf, body_pct, volume_ratio) {
        (true, Some(body_pct), Some(volume_ratio)) => {
            Some(body_pct.max(0.0) * volume_ratio.max(0.0).ln_1p())
        }
        _ => Some(0.0),
    };

    push_bool(
        factors,
        "b2_bullish_engulf_prev_bearish_flag",
        bullish_engulf,
    );
    push_bool(
        factors,
        "b2_volume_bullish_engulf_prev_bearish_flag",
        volume_bullish_engulf,
    );
    push_number(factors, "b2_bullish_engulf_volume_ratio", volume_ratio);
    push_bool(factors, "b2_yang_engulf_ma25", ma25_volume_bullish_engulf);
    push_number(
        factors,
        "b2_yang_engulf_ma25_vol_ratio",
        ma25_volume_bullish_engulf
            .then_some(volume_ratio)
            .flatten()
            .or(Some(0.0)),
    );
    push_number(factors, "b2_yang_engulf_ma25_strength", strength);
}

pub fn push_b3_signal_context_factors(
    factors: &mut FactorList,
    history: &[FactorInputRow],
    signal: Option<&str>,
) {
    push_b3_schema_structure_factors(factors, history);

    let latest_j = history.last().and_then(|row| row.j);
    let previous_j = history.iter().rev().nth(1).and_then(|row| row.j);
    push_number(
        factors,
        "b3_j_delta",
        latest_j
            .zip(previous_j)
            .map(|(latest, previous)| latest - previous),
    );

    let prepared = prepared_rows(history);
    let previous_b2 = if prepared.len() >= 2 {
        let refs = prepared.iter().collect::<Vec<_>>();
        let signals = build_b2_signal_series(&refs);
        signals.cur_b2[prepared.len() - 2]
    } else {
        false
    };
    push_bool(factors, "b3_prev_b2_flag", previous_b2);
    push_bool(factors, "b3_plus_flag", matches!(signal, Some("B3+")));
}

fn push_b3_schema_structure_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    let setup_end = history.len().saturating_sub(1).max(1).min(history.len());
    let setup_history = &history[..setup_end];
    let close = setup_history
        .iter()
        .map(|row| row.close)
        .collect::<Vec<_>>();
    let high = setup_history.iter().map(|row| row.high).collect::<Vec<_>>();
    let low = setup_history.iter().map(|row| row.low).collect::<Vec<_>>();
    let latest = setup_history.last();
    let previous = setup_history.iter().rev().nth(1);
    let latest_close = close.last().copied();

    let high_90 = max_tail(&high, 90).or_else(|| high.iter().copied().reduce(f64::max));
    let low_90 = min_tail(&low, 90).or_else(|| low.iter().copied().reduce(f64::min));
    let range_90 = high_90.zip(low_90).map(|(high, low)| high - low);
    let mid_90 = high_90.zip(low_90).map(|(high, low)| (high + low) / 2.0);
    push_number(
        factors,
        "structure_hl90_position",
        match (latest_close, low_90, range_90) {
            (Some(close), Some(low), Some(width)) if width != 0.0 => Some((close - low) / width),
            _ => None,
        },
    );
    push_number(
        factors,
        "structure_hl90_range_pct",
        match (range_90, mid_90) {
            (Some(width), Some(mid)) if mid != 0.0 => Some(width / mid * 100.0),
            _ => None,
        },
    );
    push_number(
        factors,
        "bar_upper_shadow_pct",
        latest.and_then(|row| {
            (row.close != 0.0).then_some((row.high - row.close) / row.close * 100.0)
        }),
    );

    let bullish_engulf = latest.zip(previous).is_some_and(|(latest, previous)| {
        previous.close < previous.open
            && latest.close > latest.open
            && latest.open <= previous.close
            && latest.close >= previous.open
    });
    let volume_ratio = latest.zip(previous).and_then(|(latest, previous)| {
        (previous.volume > 0.0).then_some(latest.volume / previous.volume)
    });
    let volume_bullish_engulf = bullish_engulf && volume_ratio.is_some_and(|ratio| ratio > 1.0);
    let latest_ma25 = latest.and_then(|row| row.ma25).or_else(|| {
        rolling_mean_series(&close, 25, 25)
            .last()
            .copied()
            .flatten()
    });
    let above_ma25 = latest
        .zip(latest_ma25)
        .is_some_and(|(latest, ma25)| latest.close > ma25);

    push_bool(
        factors,
        "signal_bullish_engulf_prev_bearish_flag",
        bullish_engulf,
    );
    push_number(factors, "signal_bullish_engulf_volume_ratio", volume_ratio);
    push_bool(
        factors,
        "signal_yang_engulf_ma25_flag",
        volume_bullish_engulf && above_ma25,
    );
}

fn push_b2_family_semantic_factors(
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
            j: row.j.unwrap_or(0.0),
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
            db_factors: row.db_factors.clone(),
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

fn push_optional_bool(factors: &mut FactorList, key: &str, value: Option<bool>) {
    factors.push((
        key.to_string(),
        value.map_or(FactorValue::Missing, FactorValue::Bool),
    ));
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

fn range_compression_pct(
    high: &[f64],
    low: &[f64],
    latest_close: Option<f64>,
    window: usize,
) -> Option<f64> {
    if high.len() < window || low.len() < window {
        return None;
    }
    let max_high = high[high.len() - window..]
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    let min_low = low[low.len() - window..]
        .iter()
        .copied()
        .fold(f64::INFINITY, f64::min);
    latest_close.and_then(|close| (close != 0.0).then_some((max_high - min_low) / close * 100.0))
}

fn mean_tail(values: &[f64], window: usize) -> Option<f64> {
    if values.len() < window || window == 0 {
        return None;
    }
    let tail = &values[values.len() - window..];
    Some(tail.iter().sum::<f64>() / window as f64)
}

fn abnormal_volume_to_ma20_ratio(volume: &[f64]) -> Option<f64> {
    if volume.is_empty() {
        return None;
    }
    let event_start = volume.len().saturating_sub(90);
    let (event_offset, event_volume) = volume[event_start..]
        .iter()
        .copied()
        .enumerate()
        .max_by(|left, right| left.1.total_cmp(&right.1))?;
    let event_idx = event_start + event_offset;
    if event_idx + 1 < 20 {
        return None;
    }
    let ma20 = mean_tail(&volume[event_idx + 1 - 20..=event_idx], 20)?;
    ratio_option(Some(event_volume), Some(ma20))
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
