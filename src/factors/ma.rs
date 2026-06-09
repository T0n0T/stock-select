use crate::factors::series::{
    FactorList, pct_change, push_number, rolling_mean_series, slope_pct_values,
};

pub fn push_ma_support_factors(
    factors: &mut FactorList,
    latest_close: Option<f64>,
    latest_low: Option<f64>,
    latest_ma25: Option<f64>,
    _latest_zxdkx: Option<f64>,
    ma25_values: &[f64],
) {
    push_number(
        factors,
        "close_to_ma25_pct",
        pct_change(latest_close, latest_ma25),
    );
    push_number(
        factors,
        "ma25_slope_5d_pct",
        slope_pct_values(ma25_values, 5),
    );
    push_number(
        factors,
        "low_to_ma25_pct",
        pct_change(latest_low, latest_ma25),
    );
}

pub fn push_b2_long_trend_factors(
    factors: &mut FactorList,
    close: &[f64],
    latest_close: Option<f64>,
    latest_ma60: Option<f64>,
) {
    let lt_r = b2_lt_r_series(close).last().copied().flatten();
    push_number(factors, "close_to_lt_r_pct", pct_change(latest_close, lt_r));
    push_number(factors, "lt_r_to_ma60_pct", pct_change(lt_r, latest_ma60));
}

fn b2_lt_r_series(close: &[f64]) -> Vec<Option<f64>> {
    let ma14 = rolling_mean_series(close, 14, 14);
    let ma28 = rolling_mean_series(close, 28, 28);
    let ma57 = rolling_mean_series(close, 57, 57);
    let ma114 = rolling_mean_series(close, 114, 114);
    (0..close.len())
        .map(|idx| match (ma14[idx], ma28[idx], ma57[idx], ma114[idx]) {
            (Some(a), Some(b), Some(c), Some(d)) if idx + 1 > 114 => Some((a + b + c + d) / 4.0),
            _ => None,
        })
        .collect()
}
