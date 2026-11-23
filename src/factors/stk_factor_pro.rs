//! Tushare stk_factor_pro 的单日扩展输入；价格量纲在同一 qfq 快照内归一化。
use std::collections::BTreeMap;

use crate::factors::series::{FactorList, push_number};

pub(crate) const SOURCE_COLUMNS: &[&str] = &[
    "close_qfq",
    "asi_qfq",
    "asit_qfq",
    "bias2_qfq",
    "bias3_qfq",
    "brar_ar_qfq",
    "brar_br_qfq",
    "cci_qfq",
    "cr_qfq",
    "emv_qfq",
    "maemv_qfq",
    "mass_qfq",
    "ma_mass_qfq",
    "mfi_qfq",
    "psyma_qfq",
    "maroc_qfq",
    "trma_qfq",
    "wr1_qfq",
    "updays",
    "downdays",
    "lowdays",
    "topdays",
    "dv_ttm",
    "turnover_rate",
    "volume_ratio",
    "float_share",
    "bbi_qfq",
    "ma_qfq_5",
    "ma_qfq_10",
    "ma_qfq_20",
    "ma_qfq_30",
    "ma_qfq_60",
    "ma_qfq_90",
    "ma_qfq_250",
    "ema_qfq_5",
    "ema_qfq_10",
    "ema_qfq_20",
    "ema_qfq_30",
    "ema_qfq_60",
    "ema_qfq_90",
    "ema_qfq_250",
    "expma_12_qfq",
    "expma_50_qfq",
    "boll_upper_qfq",
    "boll_mid_qfq",
    "boll_lower_qfq",
    "ktn_upper_qfq",
    "ktn_mid_qfq",
    "ktn_down_qfq",
    "taq_up_qfq",
    "taq_mid_qfq",
    "taq_down_qfq",
    "xsii_td1_qfq",
    "xsii_td2_qfq",
    "xsii_td3_qfq",
    "xsii_td4_qfq",
    "atr_qfq",
    "dfma_dif_qfq",
    "dfma_difma_qfq",
    "dpo_qfq",
    "madpo_qfq",
    "mtmma_qfq",
    "free_share",
];

const DIRECT_FACTORS: &[&str] = &[
    "asi_qfq",
    "asit_qfq",
    "bias2_qfq",
    "bias3_qfq",
    "brar_ar_qfq",
    "brar_br_qfq",
    "cci_qfq",
    "cr_qfq",
    "emv_qfq",
    "maemv_qfq",
    "mass_qfq",
    "ma_mass_qfq",
    "mfi_qfq",
    "psyma_qfq",
    "maroc_qfq",
    "trma_qfq",
    "wr1_qfq",
    "updays",
    "downdays",
    "lowdays",
    "topdays",
    "dv_ttm",
    "turnover_rate",
    "volume_ratio",
    "float_share",
];

const PRICE_LEVELS: &[&str] = &[
    "bbi_qfq",
    "ma_qfq_5",
    "ma_qfq_10",
    "ma_qfq_20",
    "ma_qfq_30",
    "ma_qfq_60",
    "ma_qfq_90",
    "ma_qfq_250",
    "ema_qfq_5",
    "ema_qfq_10",
    "ema_qfq_20",
    "ema_qfq_30",
    "ema_qfq_60",
    "ema_qfq_90",
    "ema_qfq_250",
    "expma_12_qfq",
    "expma_50_qfq",
    "boll_upper_qfq",
    "boll_mid_qfq",
    "boll_lower_qfq",
    "ktn_upper_qfq",
    "ktn_mid_qfq",
    "ktn_down_qfq",
    "taq_up_qfq",
    "taq_mid_qfq",
    "taq_down_qfq",
    "xsii_td1_qfq",
    "xsii_td2_qfq",
    "xsii_td3_qfq",
    "xsii_td4_qfq",
];

const PRICE_DIFFERENCES: &[&str] = &[
    "atr_qfq",
    "dfma_dif_qfq",
    "dfma_difma_qfq",
    "dpo_qfq",
    "madpo_qfq",
    "mtmma_qfq",
];

const CHANNELS: &[(&str, &str, &str)] = &[
    ("boll", "boll_upper_qfq", "boll_lower_qfq"),
    ("ktn", "ktn_upper_qfq", "ktn_down_qfq"),
    ("taq", "taq_up_qfq", "taq_down_qfq"),
    ("xsii_short", "xsii_td1_qfq", "xsii_td2_qfq"),
    ("xsii_long", "xsii_td3_qfq", "xsii_td4_qfq"),
];

pub(crate) fn push_stk_factor_pro_factors(
    factors: &mut FactorList,
    source: Option<&BTreeMap<String, f64>>,
) {
    let raw = |name: &str| {
        source
            .and_then(|values| values.get(&format!("_stk_{name}")))
            .copied()
            .filter(|value| value.is_finite())
    };
    // 不使用 prepared 的当前 close：它可能被重定基准或来自盘中行情。
    let close = raw("close_qfq").filter(|value| *value > 0.0);
    for name in DIRECT_FACTORS {
        push_finite(factors, name, raw(name));
    }
    for name in PRICE_LEVELS {
        let value = close
            .zip(raw(name).filter(|value| *value > 0.0))
            .map(|(close, line)| (close / line - 1.0) * 100.0);
        push_finite(factors, &format!("close_to_{name}_pct"), value);
    }
    for name in PRICE_DIFFERENCES {
        let indicator = raw(name).filter(|value| *name != "atr_qfq" || *value >= 0.0);
        let value = indicator
            .zip(close)
            .map(|(value, close)| value / close * 100.0);
        push_finite(factors, &format!("{name}_to_close_pct"), value);
    }
    for (name, upper, lower) in CHANNELS {
        let channel = close
            .zip(raw(upper))
            .zip(raw(lower))
            .filter(|((_, upper), lower)| *lower > 0.0 && upper > lower);
        let position =
            channel.map(|((close, upper), lower)| (close - lower) / (upper - lower) * 100.0);
        let width = channel.map(|((close, upper), lower)| (upper - lower) / close * 100.0);
        push_finite(factors, &format!("{name}_position_pct"), position);
        push_finite(factors, &format!("{name}_width_to_close_pct"), width);
    }
    let free_to_float = raw("free_share")
        .filter(|value| *value >= 0.0)
        .zip(raw("float_share").filter(|value| *value > 0.0))
        .map(|(free, float)| free / float * 100.0);
    push_finite(factors, "free_to_float_share_pct", free_to_float);
}

fn push_finite(factors: &mut FactorList, name: &str, value: Option<f64>) {
    push_number(
        factors,
        name,
        value.filter(|value| value.is_finite() && (value * 10_000.0).is_finite()),
    );
}
