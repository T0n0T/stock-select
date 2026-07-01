use chrono::NaiveDate;
use serde_json::json;
use stock_select::intraday::{
    MacdPeriodState, RawRtKRow, StaticRtKProvider, TushareRestProvider, TushareRtKResponse,
    build_intraday_market_rows, build_intraday_market_rows_with_macd_states,
    derive_live_macd_from_period_state, fetch_rt_k_snapshot, normalize_rt_k_rows,
    parse_tushare_rt_k_response, tushare_rt_k_request_payload,
};
use stock_select::model::MarketRow;

#[test]
fn normalize_rt_k_rows_maps_chinese_columns_and_daily_units() {
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let rows = normalize_rt_k_rows(
        vec![RawRtKRow::from_value(json!({
            "代码": "600000",
            "名称": "浦发银行",
            "开盘价": 10.1,
            "最高价": 10.5,
            "最低价": 10.0,
            "最新价": 10.34,
            "成交量": 2234567,
            "成交额": 252300000.0,
            "更新时间": "11:31:07"
        }))],
        trade_date,
        "10:00:00",
    )
    .unwrap();

    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0].ts_code, "600000.SH");
    assert_eq!(rows[0].name, "浦发银行");
    assert_eq!(rows[0].trade_date, trade_date);
    assert_eq!(rows[0].trade_time, "11:31:07");
    assert_eq!(rows[0].vol, 22345.67);
    assert_eq!(rows[0].amount, 252300.0);
}

#[test]
fn normalize_rt_k_rows_accepts_english_columns_and_sorts_by_code() {
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let rows = normalize_rt_k_rows(
        vec![
            RawRtKRow::from_value(json!({
                "ts_code": "600000.SH",
                "name": "浦发银行",
                "open": 10.1,
                "high": 10.5,
                "low": 10.0,
                "close": 10.34,
                "vol": 2234567,
                "amount": 252300000.0,
                "trade_time": "11:31:07"
            })),
            RawRtKRow::from_value(json!({
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "open": 12.1,
                "high": 12.5,
                "low": 12.0,
                "close": 12.34,
                "vol": 1234567,
                "amount": 152300000.0,
                "trade_time": "11:31:08"
            })),
        ],
        trade_date,
        "10:00:00",
    )
    .unwrap();

    assert_eq!(
        rows.iter()
            .map(|row| row.ts_code.as_str())
            .collect::<Vec<_>>(),
        vec!["000001.SZ", "600000.SH"]
    );
    assert_eq!(rows[0].vol, 12345.67);
    assert_eq!(rows[0].amount, 152300.0);
}

#[test]
fn normalize_rt_k_rows_uses_fallback_trade_time_when_missing() {
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let rows = normalize_rt_k_rows(
        vec![RawRtKRow::from_value(json!({
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "open": 12.1,
            "high": 12.5,
            "low": 12.0,
            "close": 12.34,
            "vol": 1234567,
            "amount": 152300000.0
        }))],
        trade_date,
        "14:22:11",
    )
    .unwrap();

    assert_eq!(rows[0].trade_time, "14:22:11");
}

#[test]
fn fetch_rt_k_snapshot_batches_market_wildcards_and_normalizes_rows() {
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let provider = StaticRtKProvider::new([
        (
            "*.SH",
            vec![RawRtKRow::from_value(json!({
                "ts_code": "600000.SH",
                "name": "浦发银行",
                "open": 10.1,
                "high": 10.5,
                "low": 10.0,
                "close": 10.34,
                "vol": 2234567,
                "amount": 252300000.0,
                "trade_time": "11:31:07"
            }))],
        ),
        (
            "*.SZ",
            vec![RawRtKRow::from_value(json!({
                "ts_code": "000001.SZ",
                "name": "平安银行",
                "open": 12.1,
                "high": 12.5,
                "low": 12.0,
                "close": 12.34,
                "vol": 1234567,
                "amount": 152300000.0,
                "trade_time": "11:31:08"
            }))],
        ),
        ("*.BJ", vec![]),
    ]);

    let rows = fetch_rt_k_snapshot(&provider, trade_date, "10:00:00").unwrap();

    assert_eq!(provider.calls(), vec!["*.SH", "*.SZ", "*.BJ"]);
    assert_eq!(
        rows.iter()
            .map(|row| row.ts_code.as_str())
            .collect::<Vec<_>>(),
        vec!["000001.SZ", "600000.SH"]
    );
}

#[test]
fn fetch_rt_k_snapshot_rejects_empty_market_results() {
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let provider = StaticRtKProvider::default();

    let err = fetch_rt_k_snapshot(&provider, trade_date, "10:00:00").unwrap_err();

    assert!(
        err.to_string()
            .contains("Tushare rt_k returned no usable rows")
    );
}

#[test]
fn tushare_rt_k_request_payload_uses_custom_market_wildcard() {
    let payload = tushare_rt_k_request_payload("secret-token", "*.SH");

    assert_eq!(payload["api_name"], "rt_k");
    assert_eq!(payload["token"], "secret-token");
    assert_eq!(payload["params"]["ts_code"], "*.SH");
}

#[test]
fn parse_tushare_rt_k_response_maps_fields_and_items() {
    let response: TushareRtKResponse = serde_json::from_value(json!({
        "code": 0,
        "msg": "",
        "data": {
            "fields": ["ts_code", "name", "open", "high", "low", "close", "vol", "amount", "trade_time"],
            "items": [
                ["000001.SZ", "平安银行", 12.1, 12.5, 12.0, 12.34, 1234567, 152300000.0, "11:31:08"]
            ]
        }
    }))
    .unwrap();

    let rows = parse_tushare_rt_k_response(response).unwrap();

    let normalized = normalize_rt_k_rows(
        rows,
        NaiveDate::from_ymd_opt(2026, 4, 9).unwrap(),
        "10:00:00",
    )
    .unwrap();
    assert_eq!(normalized[0].ts_code, "000001.SZ");
    assert_eq!(normalized[0].vol, 12345.67);
}

#[test]
fn parse_tushare_rt_k_response_surfaces_api_error() {
    let response: TushareRtKResponse = serde_json::from_value(json!({
        "code": -2001,
        "msg": "token invalid"
    }))
    .unwrap();

    let err = parse_tushare_rt_k_response(response).unwrap_err();

    assert!(
        err.to_string()
            .contains("Tushare rt_k API error -2001: token invalid")
    );
}

#[test]
fn derive_live_macd_from_period_state_uses_completed_state_and_live_qfq_price() {
    let state = MacdPeriodState {
        ts_code: "000001.SZ".to_string(),
        period_type: "weekly".to_string(),
        ema12: 10.0,
        ema26: 9.0,
        dea: 0.5,
        period_count: 42,
    };

    let live = derive_live_macd_from_period_state(&state, 13.0);

    let expected_ema12 = 10.0 * (11.0 / 13.0) + 13.0 * (2.0 / 13.0);
    let expected_ema26 = 9.0 * (25.0 / 27.0) + 13.0 * (2.0 / 27.0);
    let expected_dif = expected_ema12 - expected_ema26;
    let expected_dea = 0.5 * 0.8 + expected_dif * 0.2;
    let expected_hist = expected_dif - expected_dea;

    assert_eq!(live.ts_code, "000001.SZ");
    assert_eq!(live.period_type, "weekly");
    assert!((live.dif - expected_dif).abs() < 1e-12);
    assert!((live.dea - expected_dea).abs() < 1e-12);
    assert!((live.hist - expected_hist).abs() < 1e-12);
    assert_eq!(live.period_count, 43);
}

#[test]
fn tushare_rest_provider_rejects_empty_token() {
    let err = TushareRestProvider::new("  ".to_string()).unwrap_err();

    assert!(
        err.to_string()
            .contains("A Tushare token is required for intraday mode")
    );
}

#[test]
fn build_intraday_market_rows_replaces_existing_same_day_snapshot_rows() {
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let history = vec![
        MarketRow {
            ts_code: "000001.SZ".to_string(),
            trade_date: NaiveDate::from_ymd_opt(2026, 4, 8).unwrap(),
            open: 10.0,
            high: 10.2,
            low: 9.9,
            close: 10.1,
            vol: 100.0,
            turnover_rate: Some(1.0),
            adj_factor: None,
            db_factors: Default::default(),
        },
        MarketRow {
            ts_code: "000001.SZ".to_string(),
            trade_date,
            open: 10.1,
            high: 10.3,
            low: 10.0,
            close: 10.2,
            vol: 200.0,
            turnover_rate: Some(2.0),
            adj_factor: None,
            db_factors: Default::default(),
        },
    ];
    let snapshot = normalize_rt_k_rows(
        vec![RawRtKRow::from_value(json!({
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "open": 12.1,
            "high": 12.5,
            "low": 12.0,
            "close": 12.34,
            "vol": 1234567,
            "amount": 152300000.0
        }))],
        trade_date,
        "10:00:00",
    )
    .unwrap();

    let rows = build_intraday_market_rows(history, &snapshot, trade_date);

    assert_eq!(rows.len(), 2);
    assert_eq!(rows[1].trade_date, trade_date);
    assert_eq!(rows[1].close, 12.34);
    assert_eq!(rows[1].vol, 12345.67);
    let expected_vwap = 152300.0 * 10.0 / 12345.67;
    assert!((rows[1].db_factors["chip_vwap"] - expected_vwap).abs() < 1e-9);
}

#[test]
fn build_intraday_market_rows_uses_pick_date_adj_factor_for_snapshot_rows() {
    let previous_date = NaiveDate::from_ymd_opt(2026, 4, 8).unwrap();
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let history = vec![
        MarketRow {
            ts_code: "000001.SZ".to_string(),
            trade_date: previous_date,
            open: 10.0,
            high: 10.2,
            low: 9.9,
            close: 10.1,
            vol: 100.0,
            turnover_rate: Some(1.0),
            adj_factor: Some(0.5),
            db_factors: Default::default(),
        },
        MarketRow {
            ts_code: "000001.SZ".to_string(),
            trade_date,
            open: 5.0,
            high: 5.2,
            low: 4.9,
            close: 5.1,
            vol: 200.0,
            turnover_rate: Some(2.0),
            adj_factor: Some(1.0),
            db_factors: Default::default(),
        },
    ];
    let snapshot = normalize_rt_k_rows(
        vec![RawRtKRow::from_value(json!({
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "open": 5.1,
            "high": 5.4,
            "low": 5.0,
            "close": 5.3,
            "vol": 1234567,
            "amount": 152300000.0
        }))],
        trade_date,
        "10:00:00",
    )
    .unwrap();

    let rows = build_intraday_market_rows(history, &snapshot, trade_date);

    let snapshot_row = rows
        .iter()
        .find(|row| row.ts_code == "000001.SZ" && row.trade_date == trade_date)
        .unwrap();
    assert_eq!(snapshot_row.adj_factor, Some(1.0));
}

#[test]
fn build_intraday_market_rows_derives_live_macd_from_period_state_with_qfq_price() {
    let previous_date = NaiveDate::from_ymd_opt(2026, 4, 8).unwrap();
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let history = vec![MarketRow {
        ts_code: "000001.SZ".to_string(),
        trade_date: previous_date,
        open: 10.0,
        high: 10.4,
        low: 9.8,
        close: 10.0,
        vol: 100.0,
        turnover_rate: Some(1.0),
        adj_factor: Some(2.0),
        db_factors: Default::default(),
    }];
    let snapshot = normalize_rt_k_rows(
        vec![RawRtKRow::from_value(json!({
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "open": 5.0,
            "high": 5.4,
            "low": 4.9,
            "close": 5.3,
            "vol": 1234567,
            "amount": 152300000.0
        }))],
        trade_date,
        "10:00:00",
    )
    .unwrap();
    let states = vec![MacdPeriodState {
        ts_code: "000001.SZ".to_string(),
        period_type: "daily".to_string(),
        ema12: 10.0,
        ema26: 9.0,
        dea: 0.5,
        period_count: 100,
    }];

    let rows = build_intraday_market_rows_with_macd_states(history, &snapshot, trade_date, &states);

    let snapshot_row = rows
        .iter()
        .find(|row| row.ts_code == "000001.SZ" && row.trade_date == trade_date)
        .unwrap();
    let live = derive_live_macd_from_period_state(&states[0], 10.6);
    assert_eq!(snapshot_row.db_factors["intraday_price_live_qfq"], 10.6);
    assert!((snapshot_row.db_factors["macd_daily_dif"] - live.dif).abs() < 1e-12);
    assert!((snapshot_row.db_factors["macd_daily_dea"] - live.dea).abs() < 1e-12);
    assert!((snapshot_row.db_factors["macd_daily_hist"] - live.hist).abs() < 1e-12);
    assert_eq!(snapshot_row.db_factors["macd_daily_period_count"], 101.0);
}

#[test]
fn build_intraday_market_rows_carries_previous_day_ths_factors_for_snapshot_rows() {
    let previous_date = NaiveDate::from_ymd_opt(2026, 4, 8).unwrap();
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let mut db_factors = std::collections::BTreeMap::new();
    db_factors.insert("rolling_ma25_qfq".to_string(), 10.2);
    db_factors.insert("ths_sector_count".to_string(), 3.0);
    db_factors.insert("ths_main_pct_change".to_string(), 2.4);
    db_factors.insert("stock_vs_ths_main_pct_change".to_string(), 0.8);
    db_factors.insert("stock_env_sector_score".to_string(), 3.4);
    db_factors.insert("unrelated_previous_eod_factor".to_string(), 99.0);
    db_factors.insert("ths_main_net_amount".to_string(), f64::NAN);
    let history = vec![MarketRow {
        ts_code: "000001.SZ".to_string(),
        trade_date: previous_date,
        open: 10.0,
        high: 10.4,
        low: 9.8,
        close: 10.0,
        vol: 100.0,
        turnover_rate: Some(1.0),
        adj_factor: Some(2.0),
        db_factors,
    }];
    let snapshot = normalize_rt_k_rows(
        vec![RawRtKRow::from_value(json!({
            "ts_code": "000001.SZ",
            "name": "平安银行",
            "open": 5.0,
            "high": 5.4,
            "low": 4.9,
            "close": 5.3,
            "vol": 1234567,
            "amount": 152300000.0
        }))],
        trade_date,
        "10:00:00",
    )
    .unwrap();

    let rows = build_intraday_market_rows(history, &snapshot, trade_date);

    let snapshot_row = rows
        .iter()
        .find(|row| row.ts_code == "000001.SZ" && row.trade_date == trade_date)
        .unwrap();
    assert_eq!(snapshot_row.db_factors["rolling_ma25_qfq"], 10.2);
    assert_eq!(snapshot_row.db_factors["ths_sector_count"], 3.0);
    assert_eq!(snapshot_row.db_factors["ths_main_pct_change"], 2.4);
    assert_eq!(snapshot_row.db_factors["stock_vs_ths_main_pct_change"], 0.8);
    assert_eq!(snapshot_row.db_factors["stock_env_sector_score"], 3.4);
    assert_eq!(
        snapshot_row.db_factors["intraday_structure_source_previous_eod"],
        1.0
    );
    assert!(
        !snapshot_row
            .db_factors
            .contains_key("unrelated_previous_eod_factor")
    );
    assert!(!snapshot_row.db_factors.contains_key("ths_main_net_amount"));
}
