use chrono::NaiveDate;
use serde_json::json;
use stock_select_rs::cli::{IntradayScreenArgs, PoolSource, run_intraday_screen_with_provider};
use stock_select_rs::intraday::{RawRtKRow, StaticRtKProvider};
use stock_select_rs::model::{MarketRow, Method};

#[test]
fn intraday_screen_refreshes_date_scoped_candidate_and_shared_prepared_cache() {
    let temp = tempfile::tempdir().unwrap();
    let trade_date = NaiveDate::from_ymd_opt(2026, 4, 9).unwrap();
    let previous_trade_date = NaiveDate::from_ymd_opt(2026, 4, 8).unwrap();
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
                "vol": 2234567000.0,
                "amount": 252300000.0,
                "trade_time": "11:31:07"
            }))],
        ),
        ("*.SZ", vec![]),
        ("*.BJ", vec![]),
    ]);

    let path = run_intraday_screen_with_provider(
        IntradayScreenArgs {
            method: Method::B2,
            trade_date,
            run_id: "2026-04-09T11-31-08-123456+08-00".to_string(),
            dsn: Some("postgresql://example".to_string()),
            runtime_root: Some(temp.path().to_path_buf()),
            recompute: true,
            pool_source: PoolSource::TurnoverTop,
            pool_file: None,
            tushare_token: Some("token".to_string()),
            progress: false,
        },
        &provider,
        "11:31:08",
        |_dsn, _trade_date| Ok(previous_trade_date),
        |_dsn, _start, end| {
            assert_eq!(end, previous_trade_date);
            Ok(vec![MarketRow {
                ts_code: "600000.SH".to_string(),
                trade_date: previous_trade_date,
                open: 9.8,
                high: 10.0,
                low: 9.7,
                close: 9.9,
                vol: 100.0,
            }])
        },
    )
    .unwrap();

    assert_eq!(
        path,
        temp.path().join("candidates/2026-04-09.intraday.b2.json")
    );
    assert!(
        temp.path()
            .join("prepared/2026-04-09.intraday.bin")
            .exists()
    );
    assert!(
        temp.path()
            .join("prepared/2026-04-09.intraday.meta.json")
            .exists()
    );

    let payload: serde_json::Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
    assert_eq!(payload["mode"], "intraday_snapshot");
    assert_eq!(payload["trade_date"], "2026-04-09");
    assert_eq!(payload["run_id"], "2026-04-09T11-31-08-123456+08-00");
    assert_eq!(payload["fetched_at"], "2026-04-09T11-31-08-123456+08-00");
    assert_eq!(payload["source"], "tushare_rt_k");
}
