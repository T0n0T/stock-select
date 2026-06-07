use crate::factors::series::{FactorList, push_number, ratio};

pub fn push_volume_turnover_factors(
    factors: &mut FactorList,
    latest_volume: Option<f64>,
    _previous_volume: Option<f64>,
    avg_volume5: Option<f64>,
    avg_volume20: Option<f64>,
    latest_turnover: Option<f64>,
    avg_turnover5: Option<f64>,
) {
    push_number(
        factors,
        "volume_to_ma5_ratio",
        ratio(latest_volume, avg_volume5),
    );
    push_number(
        factors,
        "volume_to_ma20_ratio",
        ratio(latest_volume, avg_volume20),
    );
    push_number(
        factors,
        "volume_ma5_to_ma20_ratio",
        ratio(avg_volume5, avg_volume20),
    );
    push_number(
        factors,
        "turnover_to_ma5_ratio",
        ratio(latest_turnover, avg_turnover5),
    );
}

pub fn push_latest_volume_shrink_factor(
    factors: &mut FactorList,
    latest_volume: Option<f64>,
    previous_volume: Option<f64>,
) {
    push_number(
        factors,
        "b3_volume_shrink_ratio",
        ratio(latest_volume, previous_volume),
    );
}
