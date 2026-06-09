use chip_age_factor::{Bar, ChipConfig, ChipState, LAYERS, OUT_BINS};

use crate::factors::series::{FactorList, push_number};
use crate::factors::types::FactorInputRow;

const CHIP_VWAP_KEY: &str = "chip_vwap";
const CHIP_TURNOVER_KEY: &str = "chip_turnover";

pub fn push_chip_age_summary_factors(factors: &mut FactorList, history: &[FactorInputRow]) {
    let bars = history
        .iter()
        .filter_map(chip_bar_from_history_row)
        .collect::<Vec<_>>();
    if bars.is_empty() {
        return;
    }

    let Ok(config) = ChipConfig::from_bar(&bars[0]) else {
        return;
    };
    let mut state = ChipState::new(config);
    let mut latest = None;
    for bar in &bars {
        let Ok(features) = state.update(bar) else {
            return;
        };
        latest = Some(features);
    }
    let Some(features) = latest else {
        return;
    };

    push_number(factors, "total_mass", Some(features.total_mass));
    push_number(
        factors,
        "chip_age_layer_sum",
        Some(features.layer_ratios.iter().sum()),
    );
    push_number(
        factors,
        "chip_age_ultrashort_ratio",
        Some(features.layer_ratios[0]),
    );
    push_number(
        factors,
        "chip_age_short_ratio",
        Some(features.layer_ratios[1]),
    );
    push_number(
        factors,
        "chip_age_mid_ratio",
        Some(features.layer_ratios[2]),
    );
    push_number(
        factors,
        "chip_age_long_ratio",
        Some(features.layer_ratios[3]),
    );
    push_number(factors, "profit_ratio", Some(features.profit_ratio));
    push_number(
        factors,
        "avg_cost_close_ratio",
        Some(features.avg_cost_close_ratio),
    );
    push_number(
        factors,
        "peak_price_close_ratio",
        Some(features.peak_price_close_ratio),
    );
    push_number(factors, "chip_entropy", Some(features.chip_entropy));
    push_number(
        factors,
        "chip_concentration",
        Some(features.chip_concentration),
    );

    for layer in 0..LAYERS {
        for bin in 0..OUT_BINS {
            push_number(
                factors,
                &format!("chip_age_l{layer}_b{bin:02}"),
                Some(features.layers[layer][bin]),
            );
        }
    }
}

fn chip_bar_from_history_row(row: &FactorInputRow) -> Option<Bar> {
    let date = row.trade_date?.format("%Y-%m-%d").to_string();
    let vwap = row.db_factors.get(CHIP_VWAP_KEY).copied()?;
    let turnover = row.db_factors.get(CHIP_TURNOVER_KEY).copied()?;
    [row.low, row.high, row.close, vwap, turnover]
        .into_iter()
        .all(f64::is_finite)
        .then_some(Bar {
            date,
            symbol: String::new(),
            low: row.low,
            high: row.high,
            close: row.close,
            vwap,
            turnover,
        })
}
