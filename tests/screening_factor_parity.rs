use chrono::{Duration, NaiveDate};
use stock_select::cache::load_prepared_cache;
use stock_select::factors::registry::{build_candidate_factor_rows, factor_profile_for_method};
use stock_select::factors::types::FactorValue;
use stock_select::model::{Candidate, MarketRow, Method, PreparedRow};
use stock_select::screening::{PoolSource, ScreenRequest, run_screen_with_loader};

#[test]
fn screen_prepared_cache_feeds_real_ma_and_zx_values_into_factor_export() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(129);
    let start_date = pick_date - Duration::days(366);
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        dsn: "postgresql://fixture".to_string(),
        recompute: false,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    run_screen_with_loader(request, |_dsn, _start_date, _end_date| {
        Ok((1..=130)
            .map(|day| {
                let close = 100.0 + day as f64;
                MarketRow {
                    ts_code: "000001.SZ".to_string(),
                    trade_date: first_date + Duration::days(day as i64 - 1),
                    open: close - 0.5,
                    high: close + 1.0,
                    low: close - 2.0,
                    close,
                    vol: 1000.0 + day as f64 * 10.0,
                    turnover_rate: Some(1.0 + day as f64 / 100.0),
                }
            })
            .collect())
    })
    .unwrap();

    let prepared = load_prepared_cache(temp.path(), Method::B2, pick_date, start_date, pick_date)
        .unwrap()
        .unwrap();
    let latest = prepared
        .iter()
        .find(|row| row.ts_code == "000001.SZ" && row.trade_date == pick_date)
        .unwrap();

    assert_eq!(latest.close, 230.0);
    assert_eq!(latest.ma25, Some(218.0));
    assert_eq!(latest.ma60, Some(200.5));
    assert!(latest.zxdkx.is_some());
    assert_ne!(latest.zxdq, Some(latest.close));

    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: latest.close,
        turnover_n: latest.turnover_n,
        signal: Some("B2".to_string()),
        yellow_b1: None,
    };
    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B2, None);
    let factors = &rows[0].factors;

    assert_eq!(
        factors.get("close_to_ma25_pct"),
        Some(&FactorValue::Number(5.5046))
    );
    assert_eq!(
        factors.get("ma25_slope_5d_pct"),
        Some(&FactorValue::Number(2.3474))
    );
    assert_eq!(
        factors.get("close_to_zxdkx_pct"),
        Some(&FactorValue::Number(12.8142))
    );
    assert_eq!(
        factors.get("ma25_to_zxdkx_pct"),
        Some(&FactorValue::Number(6.9283))
    );
    assert_eq!(
        factors.get("zxdkx_slope_5d_pct"),
        Some(&FactorValue::Number(2.5141))
    );
    assert_eq!(
        factors.get("zxdq_slope_5d_pct"),
        Some(&FactorValue::Number(2.3148))
    );
}

#[test]
fn b3_uses_method_registered_factor_profile_matching_b2_for_now() {
    let pick_date = NaiveDate::from_ymd_opt(2026, 5, 25).unwrap();
    let prepared = vec![prepared_row("000001.SZ", pick_date, 10.0, 1000.0)];
    let candidate = Candidate {
        code: "000001.SZ".to_string(),
        pick_date,
        close: 10.0,
        turnover_n: prepared[0].turnover_n,
        signal: Some("B3".to_string()),
        yellow_b1: None,
    };

    let b2_profile = factor_profile_for_method(Method::B2);
    let b3_profile = factor_profile_for_method(Method::B3);
    let rows = build_candidate_factor_rows(&[candidate], &prepared, Method::B3, None);

    assert_ne!(b2_profile.bundles, b3_profile.bundles);
    assert_eq!(rows[0].method, Method::B3);
    assert_eq!(rows[0].diagnostics["factor_profile"], "b3");
    assert_eq!(
        rows[0].diagnostics["factor_bundles"],
        serde_json::json!(["raw_common", "b3_semantic"])
    );
    assert!(rows[0].factors.contains_key("trend_structure"));
    assert_eq!(
        rows[0].factors.get("signal"),
        Some(&FactorValue::Category("B3".to_string()))
    );
}

#[test]
fn turnover_top_pool_uses_real_ma25_ma60_trend_filter() {
    let temp = tempfile::tempdir().unwrap();
    let first_date = NaiveDate::from_ymd_opt(2026, 1, 1).unwrap();
    let pick_date = first_date + Duration::days(129);
    let request = ScreenRequest {
        method: Method::B2,
        pick_date,
        runtime_root: temp.path().to_path_buf(),
        dsn: "postgresql://fixture".to_string(),
        recompute: true,
        pool_source: PoolSource::TurnoverTop,
        pool_file: None,
        export_factors: false,
        environment_state: None,
    };

    let output_path = run_screen_with_loader(request, |_dsn, _start_date, _end_date| {
        let mut rows = Vec::new();
        for offset in 0..130 {
            let trade_date = first_date + Duration::days(offset);
            let weak_close = if offset < 70 { 200.0 } else { 100.0 };
            let strong_close = 100.0 + offset as f64 * 0.3;
            rows.push(market_row("000001.SZ", trade_date, weak_close, 5000.0));
            rows.push(market_row("000002.SZ", trade_date, strong_close, 1000.0));
        }
        Ok(rows)
    })
    .unwrap();

    let payload: serde_json::Value =
        serde_json::from_slice(&std::fs::read(output_path).unwrap()).unwrap();
    let candidates = payload["candidates"].as_array().unwrap();

    assert!(
        candidates.iter().all(|row| row["code"] != "000001.SZ"),
        "weak MA structure must not pass turnover-top pool only because turnover is high"
    );
    assert_eq!(payload["stats"]["total_symbols"], 1);
    assert_eq!(payload["stats"]["eligible"], 1);
}

fn market_row(ts_code: &str, trade_date: NaiveDate, close: f64, vol: f64) -> MarketRow {
    MarketRow {
        ts_code: ts_code.to_string(),
        trade_date,
        open: close - 0.5,
        high: close + 1.0,
        low: close - 2.0,
        close,
        vol,
        turnover_rate: Some(vol / 100.0),
    }
}

fn prepared_row(ts_code: &str, trade_date: NaiveDate, close: f64, volume: f64) -> PreparedRow {
    PreparedRow {
        ts_code: ts_code.to_string(),
        trade_date,
        open: close - 0.5,
        high: close + 1.0,
        low: close - 2.0,
        close,
        volume,
        turnover_n: 12.0,
        turnover_rate: Some(volume / 100.0),
        k: 50.0,
        d: 40.0,
        j: 60.0,
        zxdq: Some(close - 1.0),
        zxdkx: Some(close - 1.5),
        dif: 0.3,
        dea: 0.2,
        macd_hist: 0.1,
        ma25: Some(close - 2.0),
        ma60: Some(close - 3.0),
        ma144: Some(close - 4.0),
        chg_d: Some(1.0),
        weekly_ma_bull: true,
        max_vol_not_bearish: true,
        v_shrink: true,
        safe_mode: true,
        lt_filter: true,
        yellow_b1: false,
    }
}
