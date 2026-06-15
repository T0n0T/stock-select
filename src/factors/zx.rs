use crate::factors::series::{
    FactorList, ema, pct_change, push_bool, push_number, rolling_mean_series, slope_pct_values,
};

pub fn zx_lines(close: &[f64]) -> (Vec<f64>, Vec<Option<f64>>) {
    let first = ema(close, 10);
    let zxdq = ema(&first, 10);
    let ma14 = rolling_mean_series(close, 14, 14);
    let ma28 = rolling_mean_series(close, 28, 28);
    let ma57 = rolling_mean_series(close, 57, 57);
    let ma114 = rolling_mean_series(close, 114, 114);
    let zxdkx = (0..close.len())
        .map(|idx| match (ma14[idx], ma28[idx], ma57[idx], ma114[idx]) {
            (Some(a), Some(b), Some(c), Some(d)) => Some((a + b + c + d) / 4.0),
            _ => None,
        })
        .collect();
    (zxdq, zxdkx)
}

pub fn push_zx_pullback_factors(
    factors: &mut FactorList,
    latest_close: Option<f64>,
    latest_ma25: Option<f64>,
    latest_zxdkx: Option<f64>,
    previous_zxdkx: Option<f64>,
    zxdkx_values: &[f64],
    zxdq_values: &[f64],
) {
    push_number(
        factors,
        "close_to_zxdkx_pct",
        pct_change(latest_close, latest_zxdkx),
    );
    push_number(
        factors,
        "ma25_to_zxdkx_pct",
        pct_change(latest_ma25, latest_zxdkx),
    );
    push_number(
        factors,
        "zxdkx_slope_5d_pct",
        slope_pct_values(zxdkx_values, 5),
    );
    push_number(
        factors,
        "zxdq_slope_5d_pct",
        slope_pct_values(zxdq_values, 5),
    );
    push_bool(
        factors,
        "zxdkx_up_1d_flag",
        latest_zxdkx
            .zip(previous_zxdkx)
            .map(|(latest, previous)| latest >= previous),
    );
}
