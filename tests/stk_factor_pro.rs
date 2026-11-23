use std::collections::BTreeMap;
use stock_select::factors::registry::history_factor_fields_for_method;
use stock_select::factors::types::{FactorInputRow, FactorValue};
use stock_select::model::Method;

fn input(values: &[(&str, f64)]) -> FactorInputRow {
    FactorInputRow {
        trade_date: None,
        open: 19.0,
        high: 21.0,
        low: 18.0,
        close: 20.0,
        volume: 100.0,
        turnover_n: 1.0,
        turnover_rate: Some(1.0),
        d: None,
        j: None,
        ma25: None,
        ma60: None,
        zxdkx: None,
        zxdq: None,
        dif: None,
        dea: None,
        macd_hist: None,
        db_factors: values
            .iter()
            .map(|(key, value)| (format!("_stk_{key}"), *value))
            .collect(),
    }
}

fn factors(history: &[FactorInputRow]) -> BTreeMap<String, FactorValue> {
    history_factor_fields_for_method(Method::Scm, history, None, None)
        .into_iter()
        .collect()
}

#[test]
fn stk_factor_pro_normalizes_prices_and_preserves_dimensionless_indicators() {
    let result = factors(&[input(&[
        ("close_qfq", 20.0),
        ("atr_qfq", 1.0),
        ("dfma_dif_qfq", -2.0),
        ("mtmma_qfq", 0.5),
        ("bbi_qfq", 16.0),
        ("ema_qfq_250", 25.0),
        ("mfi_qfq", 62.5),
        ("psyma_qfq", 50.0),
        ("maroc_qfq", -3.0),
        ("bias2_qfq", 2.0),
        ("bias3_qfq", 4.0),
        ("updays", 3.0),
        ("dv_ttm", 0.0),
        ("free_share", 40.0),
        ("float_share", 80.0),
    ])]);
    for (key, expected) in [
        ("atr_qfq_to_close_pct", 5.0),
        ("dfma_dif_qfq_to_close_pct", -10.0),
        ("mtmma_qfq_to_close_pct", 2.5),
        ("close_to_bbi_qfq_pct", 25.0),
        ("close_to_ema_qfq_250_pct", -20.0),
        ("mfi_qfq", 62.5),
        ("psyma_qfq", 50.0),
        ("maroc_qfq", -3.0),
        ("bias2_qfq", 2.0),
        ("bias3_qfq", 4.0),
        ("updays", 3.0),
        ("dv_ttm", 0.0),
        ("free_to_float_share_pct", 50.0),
    ] {
        assert_eq!(
            result.get(key),
            Some(&FactorValue::Number(expected)),
            "{key}"
        );
    }
    assert!(!result.keys().any(|key| key.starts_with("_stk_")));
    assert!(!result.contains_key("ema_qfq_250"));
}

#[test]
fn stk_factor_pro_channels_preserve_breakouts_and_ignore_nominal_price_scale() {
    let prices = [
        ("close_qfq", 24.0),
        ("atr_qfq", 1.2),
        ("xsii_td1_qfq", 22.0),
        ("xsii_td2_qfq", 18.0),
        ("xsii_td3_qfq", 21.0),
        ("xsii_td4_qfq", 15.0),
        ("ktn_upper_qfq", 22.0),
        ("ktn_down_qfq", 18.0),
    ];
    let original = factors(&[input(&prices)]);
    let scaled = factors(&[input(&prices.map(|(key, value)| (key, value * 7.0)))]);
    for (key, expected) in [
        ("xsii_short_position_pct", 150.0),
        ("xsii_long_position_pct", 150.0),
        ("ktn_position_pct", 150.0),
        ("xsii_short_width_to_close_pct", 16.6667),
        ("xsii_long_width_to_close_pct", 25.0),
        ("atr_qfq_to_close_pct", 5.0),
    ] {
        assert_eq!(
            original.get(key),
            Some(&FactorValue::Number(expected)),
            "{key}"
        );
        assert_eq!(original.get(key), scaled.get(key), "{key}");
    }
}

#[test]
fn stk_factor_pro_keeps_missing_invalid_values_and_zero_denominators_missing() {
    let result = factors(&[input(&[
        ("close_qfq", 0.0),
        ("atr_qfq", 1.0),
        ("bbi_qfq", 0.0),
        ("mfi_qfq", f64::NAN),
        ("cr_qfq", f64::INFINITY),
        ("xsii_td3_qfq", 10.0),
        ("xsii_td4_qfq", 10.0),
        ("free_share", 10.0),
        ("float_share", 0.0),
    ])]);
    for key in [
        "atr_qfq_to_close_pct",
        "close_to_bbi_qfq_pct",
        "mfi_qfq",
        "cr_qfq",
        "xsii_long_position_pct",
        "xsii_long_width_to_close_pct",
        "free_to_float_share_pct",
        "psyma_qfq",
        "dv_ttm",
    ] {
        assert_eq!(result.get(key), Some(&FactorValue::Missing), "{key}");
    }
}

#[test]
fn stk_factor_pro_does_not_backfill_current_inputs_from_previous_eod() {
    let result = factors(&[
        input(&[("close_qfq", 20.0), ("mfi_qfq", 99.0), ("atr_qfq", 1.0)]),
        input(&[]),
    ]);
    assert_eq!(result.get("mfi_qfq"), Some(&FactorValue::Missing));
    assert_eq!(
        result.get("atr_qfq_to_close_pct"),
        Some(&FactorValue::Missing)
    );
}
