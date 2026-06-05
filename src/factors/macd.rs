use crate::factors::series::{FactorList, ema, pct_of, push_number};
use crate::factors::types::FactorValue;

pub fn macd_lines(close: &[f64]) -> (Vec<f64>, Vec<f64>, Vec<f64>) {
    if close.is_empty() {
        return (Vec::new(), Vec::new(), Vec::new());
    }
    let ema12 = ema(close, 12);
    let ema26 = ema(close, 26);
    let dif = ema12
        .iter()
        .zip(ema26.iter())
        .map(|(fast, slow)| fast - slow)
        .collect::<Vec<_>>();
    let dea = ema(&dif, 9);
    let hist = dif
        .iter()
        .zip(dea.iter())
        .map(|(dif, dea)| dif - dea)
        .collect::<Vec<_>>();
    (dif, dea, hist)
}

pub fn push_macd_numeric_factors(
    factors: &mut FactorList,
    dif: &[Option<f64>],
    dea: &[Option<f64>],
    macd_hist: &[Option<f64>],
    derived_dif: &[f64],
    derived_dea: &[f64],
    derived_macd_hist: &[f64],
    latest_close: Option<f64>,
) {
    let latest_macd_hist = macd_hist
        .last()
        .copied()
        .flatten()
        .or_else(|| derived_macd_hist.last().copied());
    let previous_macd_hist = macd_hist
        .iter()
        .rev()
        .nth(1)
        .copied()
        .flatten()
        .or_else(|| derived_macd_hist.iter().rev().nth(1).copied());
    let macd_hist_delta = latest_macd_hist.zip(previous_macd_hist).map(|(a, b)| a - b);
    let macd_hist_slope_3d = if macd_hist.len() >= 4 {
        let previous = macd_hist[macd_hist.len() - 4]
            .or_else(|| derived_macd_hist.get(macd_hist.len() - 4).copied());
        latest_macd_hist
            .zip(previous)
            .map(|(latest, previous)| latest - previous)
    } else {
        None
    };

    push_number(
        factors,
        "macd_dif_to_close_pct",
        pct_of(
            dif.last()
                .copied()
                .flatten()
                .or_else(|| derived_dif.last().copied()),
            latest_close,
        ),
    );
    push_number(
        factors,
        "macd_dea_to_close_pct",
        pct_of(
            dea.last()
                .copied()
                .flatten()
                .or_else(|| derived_dea.last().copied()),
            latest_close,
        ),
    );
    push_number(
        factors,
        "macd_hist_to_close_pct",
        pct_of(latest_macd_hist, latest_close),
    );
    push_number(
        factors,
        "macd_hist_delta_to_close_pct",
        pct_of(macd_hist_delta, latest_close),
    );
    push_number(
        factors,
        "macd_hist_slope_3d_to_close_pct",
        pct_of(macd_hist_slope_3d, latest_close),
    );
    factors.push((
        "macd_hist_positive_flag".to_string(),
        latest_macd_hist
            .map(|value| FactorValue::Bool(value > 0.0))
            .unwrap_or(FactorValue::Missing),
    ));
}
