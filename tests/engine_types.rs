use chrono::NaiveDate;
use serde_json::json;
use stock_select::engine::types::{
    DisplayRow, FactorRow, FactorValue, LlmAnnotation, RankedCandidate, SelectionCandidate,
};
use stock_select::model::Method;

#[test]
fn selection_candidate_round_trips_as_json() {
    let candidate = SelectionCandidate {
        code: "000001.SZ".to_string(),
        name: Some("平安银行".to_string()),
        method: Method::B2,
        pick_date: NaiveDate::from_ymd_opt(2026, 5, 25).unwrap(),
        close: Some(10.5),
        turnover_n: Some(1200.0),
        signal: Some("B2".to_string()),
        raw_payload: json!({"source": "fixture"}),
    };

    let encoded = serde_json::to_value(&candidate).unwrap();
    assert_eq!(encoded["code"], "000001.SZ");
    let decoded: SelectionCandidate = serde_json::from_value(encoded).unwrap();
    assert_eq!(decoded.method, Method::B2);
}

#[test]
fn factor_row_preserves_number_category_bool_and_missing() {
    let mut row = FactorRow::new("000001.SZ", Method::B2);
    row.factors
        .insert("close_to_zxdkx_pct".to_string(), FactorValue::Number(1.2));
    row.factors
        .insert("env".to_string(), FactorValue::Category("weak".to_string()));
    row.factors
        .insert("event_flag".to_string(), FactorValue::Bool(true));
    row.factors
        .insert("turnover_rate".to_string(), FactorValue::Missing);

    let encoded = serde_json::to_value(&row).unwrap();
    assert_eq!(encoded["factors"]["close_to_zxdkx_pct"], 1.2);
    assert_eq!(encoded["factors"]["env"], "weak");
    assert_eq!(encoded["factors"]["event_flag"], true);
    assert!(encoded["factors"]["turnover_rate"].is_null());
}

#[test]
fn ranked_candidate_and_llm_annotation_have_distinct_roles() {
    let ranked = RankedCandidate {
        code: "000001.SZ".to_string(),
        model_score: 0.75,
        model_rank: 1,
        feature_vector_path: Some("feature_vectors.json".to_string()),
    };
    let annotation = LlmAnnotation {
        code: ranked.code.clone(),
        llm_action: "CAUTION".to_string(),
        llm_confidence: Some(0.7),
        llm_risk_flags: vec!["量能不足".to_string()],
        llm_comment: Some("等待确认".to_string()),
        raw_response_path: None,
    };
    let display = DisplayRow::from_ranked(&ranked, Some(&annotation), Some("平安银行"));
    assert_eq!(display.model_rank, Some(1));
    assert_eq!(display.llm_action.as_deref(), Some("CAUTION"));
}
