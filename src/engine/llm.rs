use std::collections::BTreeMap;

use crate::engine::types::{DisplayRow, LlmAnnotation, RankedCandidate};

pub fn merge_llm_annotations(
    ranked_rows: &[RankedCandidate],
    annotations: &[LlmAnnotation],
) -> Vec<DisplayRow> {
    let by_code = annotations
        .iter()
        .map(|annotation| (annotation.code.as_str(), annotation))
        .collect::<BTreeMap<_, _>>();

    ranked_rows
        .iter()
        .map(|ranked| {
            DisplayRow::from_ranked(ranked, by_code.get(ranked.code.as_str()).copied(), None)
        })
        .collect()
}

pub fn final_action_for_annotation(action: Option<&str>) -> &'static str {
    match action.unwrap_or("UNREVIEWED").to_ascii_uppercase().as_str() {
        "KEEP" => "KEEP",
        "CAUTION" => "CAUTION",
        "REJECT" => "REJECT",
        _ => "UNREVIEWED",
    }
}
