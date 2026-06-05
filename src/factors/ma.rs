use crate::factors::series::{FactorList, pct_change, push_number, slope_pct_values};

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
