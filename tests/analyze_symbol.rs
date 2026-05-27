use chrono::NaiveDate;
use serde_json::Value;
use stock_select_rs::cli::{AnalyzeSymbolArgs, run_analyze_symbol_with_loaders};
use stock_select_rs::model::{MarketRow, Method};

fn market_row(code: &str, day: u32, close: f64) -> MarketRow {
    MarketRow {
        ts_code: code.to_string(),
        trade_date: NaiveDate::from_ymd_opt(2026, 4, day).unwrap(),
        open: close - 0.2,
        high: close + 0.3,
        low: close - 0.4,
        close,
        vol: 100_000.0 + day as f64,
    }
}

#[test]
fn analyze_symbol_writes_result_even_when_not_selected() {
    let temp = tempfile::tempdir().unwrap();
    let pick = NaiveDate::from_ymd_opt(2026, 4, 21).unwrap();
    let path = run_analyze_symbol_with_loaders(
        AnalyzeSymbolArgs {
            method: Method::B2,
            symbol: "002350".to_string(),
            pick_date: Some(pick),
            dsn: Some("postgresql://example".to_string()),
            runtime_root: Some(temp.path().to_path_buf()),
            environment_state: Some("weak".to_string()),
            environment_reason: Some("test env".to_string()),
        },
        |_dsn, _symbol, start, end| {
            assert!(start < pick);
            assert_eq!(end, pick);
            Ok((1..=21)
                .map(|day| market_row("002350.SZ", day, 10.0 + day as f64 * 0.01))
                .collect())
        },
        |_dsn, _symbol| unreachable!("explicit pick_date should not resolve latest date"),
        |_code, _rows, out_path| {
            std::fs::write(out_path, b"png").unwrap();
            Ok(())
        },
    )
    .unwrap();

    assert_eq!(
        path,
        temp.path()
            .join("ad_hoc/2026-04-21.b2.002350.SZ/result.json")
    );
    let payload: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
    assert_eq!(payload["code"], "002350.SZ");
    assert_eq!(payload["pick_date"], "2026-04-21");
    assert_eq!(payload["method"], "b2");
    assert_eq!(payload["selected_as_candidate"], false);
    assert!(payload["screen_conditions"].is_object());
    assert!(payload["baseline_review"]["total_score"].is_number());
    assert!(
        payload["chart_path"]
            .as_str()
            .unwrap()
            .ends_with("002350.SZ_day.png")
    );
}
