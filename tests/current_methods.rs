use std::str::FromStr;

use assert_cmd::Command;
use predicates::prelude::*;
use stock_select::model::Method;

#[test]
fn old_model_metadata_requires_explicit_encoding() {
    let metadata = serde_json::json!({
        "numeric_columns": ["close"], "categorical_columns": [], "feature_names": ["close"]
    });
    assert!(
        serde_json::from_value::<stock_select::engine::inference::ModelFeatureMetadata>(metadata)
            .is_err()
    );
}

#[test]
fn model_metadata_requires_the_current_training_schema() {
    let metadata = serde_json::json!({
        "numeric_columns": ["close"], "categorical_columns": [], "categorical_levels": {},
        "categorical_encoding": "one_hot", "feature_names": ["close"]
    });
    for field in [
        "numeric_columns",
        "categorical_columns",
        "categorical_levels",
        "feature_names",
    ] {
        let mut incomplete = metadata.clone();
        incomplete.as_object_mut().unwrap().remove(field);
        assert!(
            serde_json::from_value::<stock_select::engine::inference::ModelFeatureMetadata>(
                incomplete
            )
            .is_err(),
            "{field}"
        );
    }
}

#[test]
fn current_methods_round_trip_through_text_and_json() {
    for (name, method) in [
        ("b2", Method::B2),
        ("scm", Method::Scm),
        ("pbm", Method::Pbm),
    ] {
        assert_eq!(Method::from_str(name).unwrap(), method);
        assert_eq!(method.to_string(), name);
        assert_eq!(
            serde_json::from_value::<Method>(serde_json::json!(name)).unwrap(),
            method
        );
    }
}

#[test]
fn retired_methods_are_rejected_by_text_and_artifact_parsers() {
    for name in ["b1", "b3", "lsh", "qianlong", "dribull"] {
        assert!(Method::from_str(name).is_err(), "{name} must not parse");
        assert!(serde_json::from_value::<Method>(serde_json::json!(name)).is_err());
    }
}

#[test]
fn retired_methods_fail_at_cli_parsing_for_every_artifact_workflow() {
    for command in [
        "screen",
        "run",
        "review",
        "review-list",
        "review-merge",
        "chart",
    ] {
        for method in ["b1", "b3", "lsh", "qianlong", "dribull"] {
            Command::cargo_bin("stock-select-rs")
                .unwrap()
                .args([command, "--method", method])
                .assert()
                .failure()
                .stderr(predicate::str::contains(format!(
                    "unsupported method: {method}"
                )));
        }
    }
}
