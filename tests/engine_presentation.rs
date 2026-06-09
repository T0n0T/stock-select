use stock_select::engine::presentation::{format_display_lines, limit_display_rows};
use stock_select::engine::types::DisplayRow;

fn row(code: &str, rank: usize, score: f64) -> DisplayRow {
    DisplayRow {
        code: code.to_string(),
        name: None,
        industry: None,
        model_rank: Some(rank),
        model_score: Some(score),
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
