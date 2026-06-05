use crate::factors::series::{FactorList, pct_change, push_number};

pub fn latest_bar_position(
    latest_close: Option<f64>,
    latest_low: Option<f64>,
    latest_high: Option<f64>,
) -> Option<f64> {
    match (latest_close, latest_low, latest_high) {
        (Some(close), Some(low), Some(high)) if high != low => {
            Some((close - low) / (high - low) * 100.0)
        }
        _ => None,
    }
}

pub fn push_price_position_factors(
    factors: &mut FactorList,
    close: &[f64],
    high: &[f64],
    low: &[f64],
    latest_close: Option<f64>,
    latest_low: Option<f64>,
    latest_high: Option<f64>,
    previous_close: Option<f64>,
    avg_close5: Option<f64>,
) {
    let high_20_close = if close.len() >= 20 {
        Some(
            close[close.len() - 20..]
                .iter()
                .copied()
                .fold(f64::NEG_INFINITY, f64::max),
        )
    } else {
        None
    };
    let tail_high_120 = if high.len() >= 120 {
        &high[high.len() - 120..]
    } else {
        high
    };
    let tail_low_120 = if low.len() >= 120 {
        &low[low.len() - 120..]
    } else {
        low
    };
    let high_120 = tail_high_120.iter().copied().reduce(f64::max);
    let low_120 = tail_low_120.iter().copied().reduce(f64::min);
    let range_center_120 = high_120.zip(low_120).map(|(high, low)| (high + low) / 2.0);
    let range_width_120 = high_120.zip(low_120).map(|(high, low)| high - low);
    let box_position_120 = match (latest_close, low_120, range_width_120) {
        (Some(close), Some(low), Some(width)) if width != 0.0 => {
            Some((close - low) / width * 100.0)
        }
        _ => None,
    };

    push_number(
        factors,
        "latest_bar_position_pct",
        latest_bar_position(latest_close, latest_low, latest_high),
    );
    push_number(
        factors,
        "close_to_close_ma5_pct",
        pct_change(latest_close, avg_close5),
    );
    push_number(factors, "box_position_120d_pct", box_position_120);
    push_number(
        factors,
        "close_to_120d_max_pct",
        pct_change(latest_close, high_120),
    );
    push_number(
        factors,
        "close_to_120d_min_pct",
        pct_change(latest_close, low_120),
    );
    push_number(
        factors,
        "close_to_120d_range_center_pct",
        pct_change(latest_close, range_center_120),
    );
    push_number(
        factors,
        "range_width_120d_pct",
        match (range_width_120, latest_close) {
            (Some(width), Some(close)) if close != 0.0 => Some(width / close * 100.0),
            _ => None,
        },
    );
    push_number(
        factors,
        "close_to_20d_max_close_pct",
        pct_change(latest_close, high_20_close),
    );
    push_number(
        factors,
        "pct_chg_1d",
        pct_change(latest_close, previous_close),
    );
}

pub fn push_range_compression(
    factors: &mut FactorList,
    high: &[f64],
    low: &[f64],
    latest_close: Option<f64>,
    window: usize,
) {
    let value = if high.len() >= window && low.len() >= window {
        let max_high = high[high.len() - window..]
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max);
        let min_low = low[low.len() - window..]
            .iter()
            .copied()
            .fold(f64::INFINITY, f64::min);
        latest_close.and_then(|close| {
            if close != 0.0 {
                Some((max_high - min_low) / close * 100.0)
            } else {
                None
            }
        })
    } else {
        None
    };
    push_number(factors, &format!("range_compression_{window}d"), value);
}
