#[test]
fn docs_describe_db_native_screening_path_instead_of_legacy_daily_market_loader() {
    let architecture = include_str!("../docs/architecture.md");
    let workflow = include_str!("../docs/workflow.md");
    let screening_methods = include_str!("../docs/screening-methods.md");

    for (name, contents) in [
        ("docs/architecture.md", architecture),
        ("docs/workflow.md", workflow),
        ("docs/screening-methods.md", screening_methods),
    ] {
        assert!(
            !contents.contains("fetch_daily_window()"),
            "{name} still references legacy fetch_daily_window()"
        );
        assert!(
            !contents.contains("3 年行情窗口"),
            "{name} still describes the legacy three-year screening window"
        );
        assert!(
            !contents.contains("读取 `daily_market` 获取上证指数和国证 2000 数据"),
            "{name} still points EOD environment docs at daily_market"
        );
        assert!(
            !contents.contains("PostgreSQL<br/>daily_market"),
            "{name} still diagrams daily_market as the screening source"
        );
    }

    assert!(architecture.contains("fetch_db_native_daily_window()"));
    assert!(architecture.contains("stock-cache DB-native"));
    assert!(workflow.contains("DB-native stock-cache"));
    assert!(screening_methods.contains("约 252 个交易日"));
}
