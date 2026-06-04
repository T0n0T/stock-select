use stock_select::engine::llm::{final_action_for_annotation, merge_llm_annotations};
use stock_select::engine::types::{LlmAnnotation, RankedCandidate};

fn ranked(code: &str, rank: usize) -> RankedCandidate {
    RankedCandidate {
        code: code.to_string(),
        model_score: 1.0 / rank as f64,
        model_rank: rank,
        feature_vector_path: None,
    }
}

#[test]
fn llm_annotation_does_not_change_model_rank() {
    let ranked_rows = vec![ranked("000001.SZ", 1), ranked("000002.SZ", 2)];
    let annotations = vec![LlmAnnotation {
        code: "000002.SZ".to_string(),
        llm_action: "REJECT".to_string(),
        llm_confidence: Some(0.9),
        llm_risk_flags: vec!["放量失败".to_string()],
        llm_comment: Some("风险较高".to_string()),
        raw_response_path: None,
    }];

    let merged = merge_llm_annotations(&ranked_rows, &annotations);
    assert_eq!(merged[0].model_rank, Some(1));
    assert_eq!(merged[1].model_rank, Some(2));
    assert_eq!(merged[1].llm_action.as_deref(), Some("REJECT"));
}

#[test]
fn final_action_maps_llm_action_without_using_verdict() {
    assert_eq!(final_action_for_annotation(None), "UNREVIEWED");
    assert_eq!(final_action_for_annotation(Some("KEEP")), "KEEP");
    assert_eq!(final_action_for_annotation(Some("CAUTION")), "CAUTION");
    assert_eq!(final_action_for_annotation(Some("REJECT")), "REJECT");
}
