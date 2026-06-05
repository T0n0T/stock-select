use crate::factors::series::{FactorList, mean_prefix_tail, pct_change, push_number, ratio};

pub fn push_abnormal_volume_event_factors(
    factors: &mut FactorList,
    open: &[f64],
    close: &[f64],
    volume: &[f64],
    latest_close: Option<f64>,
) {
    if volume.is_empty() {
        return;
    }

    let event_start = volume.len().saturating_sub(90);
    let Some((event_offset, event_volume)) = volume[event_start..]
        .iter()
        .copied()
        .enumerate()
        .max_by(|left, right| left.1.total_cmp(&right.1))
    else {
        return;
    };
    let event_idx = event_start + event_offset;
    let event_open = open.get(event_idx).copied();
    let event_close = close.get(event_idx).copied();
    let event_price = event_open
        .zip(event_close)
        .map(|(open, close)| open.max(close))
        .or(event_close);
    let event_volume_ma20 = mean_prefix_tail(volume, event_idx + 1, 20);
    let min_body_after = if event_idx + 1 < close.len() {
        (event_idx + 1..close.len())
            .map(|idx| open[idx].min(close[idx]))
            .reduce(f64::min)
    } else {
        event_open
            .zip(event_close)
            .map(|(open, close)| open.min(close))
    };
    let redundant_price = event_price.map(|price| price * 0.90);

    push_number(
        factors,
        "abnormal_volume_event_days_ago",
        Some((close.len() - 1 - event_idx) as f64),
    );
    push_number(
        factors,
        "abnormal_volume_to_ma20_ratio",
        ratio(Some(event_volume), event_volume_ma20),
    );
    push_number(
        factors,
        "abnormal_event_body_pct",
        event_open
            .zip(event_close)
            .and_then(|(open, close)| pct_change(Some(close), Some(open)))
            .map(f64::abs),
    );
    push_number(
        factors,
        "abnormal_event_price_to_current_pct",
        pct_change(event_price, latest_close),
    );
    push_number(
        factors,
        "post_abnormal_min_body_to_event_price_pct",
        pct_change(min_body_after, event_price),
    );
    push_number(
        factors,
        "post_abnormal_drawdown_pct",
        pct_change(min_body_after, event_price),
    );
    push_number(
        factors,
        "abnormal_redundant_position_pct",
        pct_change(min_body_after, redundant_price),
    );
}
