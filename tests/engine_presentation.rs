use stock_select::engine::presentation::{
    format_display_lines, format_display_table, limit_display_rows,
};
use stock_select::engine::types::DisplayRow;

fn row(code: &str, rank: usize, score: f64) -> DisplayRow {
    DisplayRow {
        code: code.to_string(),
        name: None,
        industry: None,
        model_rank: Some(rank),
        model_score: Some(score),
        raw_model_score: None,
        entry_assessment: None,
        llm_action: None,
        llm_risk_flags: vec![],
        llm_comment: None,
    }
}

#[test]
fn limit_display_rows_keeps_front_rows() {
    let rows = vec![row("000001.SZ", 1, 0.7), row("000002.SZ", 2, 0.6)];
    let limited = limit_display_rows(rows.clone(), Some(1)).unwrap();
    assert_eq!(limited, vec![row("000001.SZ", 1, 0.7)]);
    assert_eq!(limit_display_rows(rows.clone(), None).unwrap(), rows);
}

#[test]
fn limit_zero_is_rejected() {
    let err = limit_display_rows(vec![row("000001.SZ", 1, 0.7)], Some(0)).unwrap_err();
    assert!(err.to_string().contains("limit"));
}

#[test]
fn format_display_lines_shows_only_review_symbol_without_action_or_flags() {
    let mut item = row("000001.SZ", 1, 0.7);
    item.name = Some("平安银行".to_string());
    item.industry = Some("银行".to_string());
    item.llm_action = Some("CAUTION".to_string());
    item.llm_risk_flags = vec!["量能不足".to_string(), "高位".to_string()];

    let lines = format_display_lines(&[item]);
    assert_eq!(lines, vec!["1\t000001.SZ\t平安银行\t银行\t0.700000\t→"]);
}

#[test]
fn format_display_lines_maps_llm_actions_to_short_bias_symbols() {
    let mut keep = row("000001.SZ", 1, 0.8);
    keep.llm_action = Some("KEEP".to_string());
    let mut caution = row("000002.SZ", 2, 0.7);
    caution.llm_action = Some("CAUTION".to_string());
    let mut reject = row("000003.SZ", 3, 0.6);
    reject.llm_action = Some("REJECT".to_string());
    let unknown = row("000004.SZ", 4, 0.5);

    let lines = format_display_lines(&[keep, caution, reject, unknown]);

    assert!(lines[0].ends_with("\t↑"));
    assert!(lines[1].ends_with("\t→"));
    assert!(lines[2].ends_with("\t↓"));
    assert!(lines[3].ends_with("\t-"));
    assert!(!lines[0].contains("KEEP"));
    assert!(!lines[1].contains("CAUTION"));
    assert!(!lines[2].contains("REJECT"));
}

#[test]
fn fifth_column_shows_compact_entry_action_and_raw_score_with_independent_llm_bias() {
    let item: DisplayRow = serde_json::from_value(serde_json::json!({
        "code": "000001.SZ", "name": "平安银行", "industry": "银行",
        "model_rank": 1, "model_score": 1.0, "raw_model_score": -0.1,
        "llm_action": "KEEP", "llm_risk_flags": [],
        "entry_assessment": {"action": "observe", "reason": "未达开仓门槛", "research": true,
            "gate": {"open_min_score": 0.0, "discard_below_score": -0.2, "top_n": 2}}
    }))
    .unwrap();
    let line = format_display_lines(&[item]).pop().unwrap();
    let cols = line.split('\t').collect::<Vec<_>>();
    assert_eq!(cols.len(), 6);
    assert_eq!(cols[4], "观察 | -0.100000");
    assert_eq!(cols[5], "↑");
}

#[test]
fn display_table_aligns_chinese_names_industries_and_multi_digit_ranks() {
    let items = [
        serde_json::from_value(serde_json::json!({
            "code":"688775.SH", "name":"影石创新", "industry":"消费电子", "model_rank":1,
            "raw_model_score":0.228483, "entry_assessment":{"action":"observe", "reason":"日期早于校准完成"},
            "llm_action":"KEEP", "llm_risk_flags":[]
        })).unwrap(),
        serde_json::from_value(serde_json::json!({
            "code":"002983.SZ", "name":"芯瑞达", "industry":"光学光电子", "model_rank":10,
            "raw_model_score":null, "entry_assessment":{"action":"observe", "reason":"原分缺失"},
            "llm_action":"REJECT", "llm_risk_flags":[]
        })).unwrap(),
    ];
    let lines = format_display_table(&items);
    assert_eq!(
        lines,
        [
            "排名  代码       名称      行业        开仓 / 原分       LLM",
            "────  ─────────  ────────  ──────────  ────────────────  ───",
            "   1  688775.SH  影石创新  消费电子    观察 | +0.228483   ↑",
            "  10  002983.SZ  芯瑞达    光学光电子  观察 | 缺失        ↓",
        ]
    );
}

#[test]
fn display_table_handles_empty_results_and_missing_instrument_info() {
    assert_eq!(format_display_table(&[]), ["暂无入选股票"]);
    let lines = format_display_table(&[row("000001.SZ", 1, 0.7)]);
    assert_eq!(lines.len(), 3);
    assert!(lines[0].contains("评分"));
    assert!(lines[2].contains("000001.SZ  -     -     0.700000"));
}
