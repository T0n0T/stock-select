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
fn format_display_lines_includes_model_and_llm_fields() {
    let mut item = row("000001.SZ", 1, 0.7);
    item.name = Some("平安银行".to_string());
    item.industry = Some("银行".to_string());
    item.llm_action = Some("CAUTION".to_string());
    item.llm_risk_flags = vec!["量能不足".to_string(), "高位".to_string()];

    let lines = format_display_lines(&[item]);
    assert_eq!(
        lines,
        vec!["1\t000001.SZ\t平安银行\t银行\t0.700000\tCAUTION\t量能不足,高位"]
    );
}
