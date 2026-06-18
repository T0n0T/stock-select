use std::collections::BTreeMap;
use stock_select::engine::inference::{
    LightGbmRuntimeModel, ModelFeatureMetadata, build_feature_vector, default_model_dir,
    resolve_method_model_artifacts, resolve_method_model_artifacts_for_mode,
    resolve_method_model_artifacts_for_route, resolve_method_model_artifacts_with_overrides,
};
use stock_select::engine::types::{FactorRow, FactorValue};
use stock_select::model::Method;

#[test]
fn lightgbm_default_model_dirs_match_runtime_contract() {
    assert_eq!(default_model_dir(Method::B2).unwrap(), "models/b2");
    assert_eq!(default_model_dir(Method::B3).unwrap(), "models/b3");
    assert_eq!(default_model_dir(Method::Lsh).unwrap(), "models/lsh");
    assert!(default_model_dir(Method::B1).is_none());
}

#[test]
fn b2_model_resolution_accepts_complete_default_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::B2).unwrap());
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::write(model_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(model_dir.join("model_metadata.json"), "{}\n").unwrap();

    let resolved = resolve_method_model_artifacts(Method::B2, temp.path()).unwrap();
    assert_eq!(resolved.model_path, Some(model_dir.join("model.txt")));
    assert_eq!(
        resolved.metadata_path,
        Some(model_dir.join("model_metadata.json"))
    );
}

#[test]
fn b2_eod_model_resolution_uses_default_b2_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::B2).unwrap());
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::write(model_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(model_dir.join("model_metadata.json"), "{}\n").unwrap();
    std::fs::write(
        model_dir.join("model_state.json"),
        serde_json::json!({
            "eod": {"status": "ready", "model_dir": "models/b2"},
            "intraday": {"status": "blocked", "reason": "intraday feature coverage is incomplete"}
        })
        .to_string(),
    )
    .unwrap();

    let resolved = resolve_method_model_artifacts_for_mode(Method::B2, temp.path(), false).unwrap();

    assert_eq!(resolved.model_path, Some(model_dir.join("model.txt")));
    assert_eq!(
        resolved.metadata_path,
        Some(model_dir.join("model_metadata.json"))
    );
}

#[test]
fn b2_intraday_model_resolution_rejects_blocked_state() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::B2).unwrap());
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::write(model_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(model_dir.join("model_metadata.json"), "{}\n").unwrap();
    std::fs::write(
        model_dir.join("model_state.json"),
        serde_json::json!({
            "eod": {"status": "ready", "model_dir": "models/b2"},
            "intraday": {"status": "blocked", "reason": "intraday model is not published yet"}
        })
        .to_string(),
    )
    .unwrap();

    let err = resolve_method_model_artifacts_for_mode(Method::B2, temp.path(), true).unwrap_err();

    assert!(
        err.to_string()
            .contains("intraday model is not published yet")
    );
}

#[test]
fn b2_intraday_model_resolution_requires_state_before_using_model() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::B2).unwrap());
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::write(model_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(model_dir.join("model_metadata.json"), "{}\n").unwrap();

    let err = resolve_method_model_artifacts_for_mode(Method::B2, temp.path(), true).unwrap_err();

    assert!(err.to_string().contains("intraday model state is missing"));
}

#[test]
fn b2_intraday_model_resolution_uses_intraday_dir_when_ready() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::B2).unwrap());
    let intraday_dir = temp.path().join("models/b2_intraday");
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::create_dir_all(&intraday_dir).unwrap();
    std::fs::write(model_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(model_dir.join("model_metadata.json"), "{}\n").unwrap();
    std::fs::write(intraday_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(intraday_dir.join("model_metadata.json"), "{}\n").unwrap();
    std::fs::write(
        model_dir.join("model_state.json"),
        serde_json::json!({
            "eod": {"status": "ready", "model_dir": "models/b2"},
            "intraday": {"status": "ready", "model_dir": "models/b2_intraday"}
        })
        .to_string(),
    )
    .unwrap();

    let resolved = resolve_method_model_artifacts_for_mode(Method::B2, temp.path(), true).unwrap();

    assert_eq!(resolved.model_path, Some(intraday_dir.join("model.txt")));
    assert_eq!(
        resolved.metadata_path,
        Some(intraday_dir.join("model_metadata.json"))
    );
}

#[test]
fn lsh_intraday_model_resolution_uses_intraday_dir_when_ready() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::Lsh).unwrap());
    let intraday_dir = temp.path().join("models/lsh_intraday");
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::create_dir_all(&intraday_dir).unwrap();
    std::fs::write(intraday_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(intraday_dir.join("model_metadata.json"), "{}\n").unwrap();
    std::fs::write(
        model_dir.join("model_state.json"),
        serde_json::json!({
            "eod": {"status": "blocked", "reason": "eod model is not published yet"},
            "intraday": {"status": "ready", "model_dir": "models/lsh_intraday"}
        })
        .to_string(),
    )
    .unwrap();

    let resolved = resolve_method_model_artifacts_for_mode(Method::Lsh, temp.path(), true).unwrap();

    assert_eq!(resolved.model_path, Some(intraday_dir.join("model.txt")));
    assert_eq!(
        resolved.metadata_path,
        Some(intraday_dir.join("model_metadata.json"))
    );
}

#[test]
fn b2_model_resolution_accepts_cli_artifact_overrides() {
    let temp = tempfile::tempdir().unwrap();
    let model_path = temp.path().join("custom-model.txt");
    let metadata_path = temp.path().join("custom-metadata.json");
    std::fs::write(&model_path, "tree\n").unwrap();
    std::fs::write(&metadata_path, "{}\n").unwrap();

    let resolved = resolve_method_model_artifacts_with_overrides(
        Method::B2,
        temp.path(),
        Some(model_path.as_path()),
        Some(metadata_path.as_path()),
    )
    .unwrap();

    assert_eq!(resolved.model_path, Some(model_path));
    assert_eq!(resolved.metadata_path, Some(metadata_path));
}

#[test]
fn b2_model_resolution_does_not_use_legacy_default_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp
        .path()
        .join("models/b2_rank_layer/lgbm_manifest_top_numeric");
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::write(model_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(model_dir.join("model_metadata.json"), "{}\n").unwrap();

    let err = resolve_method_model_artifacts(Method::B2, temp.path()).unwrap_err();
    assert!(
        err.to_string()
            .contains("missing default b2 model artifacts")
    );
}

#[test]
fn b2_model_resolution_rejects_half_deployed_model() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::B2).unwrap());
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::write(model_dir.join("model.txt"), "tree\n").unwrap();

    let err = resolve_method_model_artifacts(Method::B2, temp.path()).unwrap_err();
    assert!(
        err.to_string()
            .contains("incomplete default b2 model artifacts")
    );
}

#[test]
fn b1_model_resolution_is_unsupported() {
    let temp = tempfile::tempdir().unwrap();
    let err = resolve_method_model_artifacts(Method::B1, temp.path()).unwrap_err();
    assert!(err.to_string().contains("b1 model review is not available"));
}

#[test]
fn b3_model_resolution_accepts_complete_default_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::B3).unwrap());
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::write(model_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(model_dir.join("model_metadata.json"), "{}\n").unwrap();

    let resolved = resolve_method_model_artifacts(Method::B3, temp.path()).unwrap();
    assert_eq!(resolved.model_path, Some(model_dir.join("model.txt")));
    assert_eq!(
        resolved.metadata_path,
        Some(model_dir.join("model_metadata.json"))
    );
}

#[test]
fn b3_model_resolution_uses_routed_artifact_for_env_condition() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::B3).unwrap());
    let strong_dir = model_dir.join("models/strong_sw4");
    let fallback_dir = model_dir.join("models/neutral_rf");
    std::fs::create_dir_all(&strong_dir).unwrap();
    std::fs::create_dir_all(&fallback_dir).unwrap();
    std::fs::write(
        model_dir.join("model_routing.json"),
        serde_json::json!({
            "version": 1,
            "default_model": "neutral_rf",
            "models": {
                "strong_sw4": "models/strong_sw4",
                "neutral_rf": "models/neutral_rf"
            },
            "routes": [
                {"when": {"env": "strong"}, "model": "strong_sw4"}
            ]
        })
        .to_string(),
    )
    .unwrap();
    std::fs::write(strong_dir.join("model.txt"), "strong\n").unwrap();
    std::fs::write(strong_dir.join("model_metadata.json"), "{}\n").unwrap();
    std::fs::write(fallback_dir.join("model.txt"), "fallback\n").unwrap();
    std::fs::write(fallback_dir.join("model_metadata.json"), "{}\n").unwrap();

    let routed = resolve_method_model_artifacts_for_route(
        Method::B3,
        temp.path(),
        false,
        [("env", Some("strong"))],
    )
    .unwrap();
    let fallback = resolve_method_model_artifacts_for_route(
        Method::B3,
        temp.path(),
        false,
        [("env", Some("weak"))],
    )
    .unwrap();

    assert_eq!(routed.model_path, Some(strong_dir.join("model.txt")));
    assert_eq!(
        routed.metadata_path,
        Some(strong_dir.join("model_metadata.json"))
    );
    assert_eq!(fallback.model_path, Some(fallback_dir.join("model.txt")));
    assert_eq!(
        fallback.metadata_path,
        Some(fallback_dir.join("model_metadata.json"))
    );
}

#[test]
fn b3_model_resolution_accepts_routed_model_manifest_without_top_level_model() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::B3).unwrap());
    let strong_dir = model_dir.join("models/strong_sw4");
    std::fs::create_dir_all(&strong_dir).unwrap();
    std::fs::write(strong_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(strong_dir.join("model_metadata.json"), "{}\n").unwrap();
    std::fs::write(
        model_dir.join("model_routing.json"),
        serde_json::json!({
            "version": 1,
            "default_model": "strong_sw4",
            "models": {"strong_sw4": "models/strong_sw4"},
            "routes": [{"when": {"env": "strong"}, "model": "strong_sw4"}]
        })
        .to_string(),
    )
    .unwrap();

    let resolved = resolve_method_model_artifacts(Method::B3, temp.path()).unwrap();

    assert_eq!(resolved.model_dir, Some(model_dir.clone()));
    assert_eq!(
        resolved.routing_path,
        Some(model_dir.join("model_routing.json"))
    );
    assert_eq!(resolved.model_path, None);
    assert_eq!(resolved.metadata_path, None);
}

#[test]
fn lsh_model_resolution_accepts_complete_default_artifacts() {
    let temp = tempfile::tempdir().unwrap();
    let model_dir = temp.path().join(default_model_dir(Method::Lsh).unwrap());
    std::fs::create_dir_all(&model_dir).unwrap();
    std::fs::write(model_dir.join("model.txt"), "tree\n").unwrap();
    std::fs::write(model_dir.join("model_metadata.json"), "{}\n").unwrap();

    let resolved = resolve_method_model_artifacts(Method::Lsh, temp.path()).unwrap();
    assert_eq!(resolved.model_path, Some(model_dir.join("model.txt")));
    assert_eq!(
        resolved.metadata_path,
        Some(model_dir.join("model_metadata.json"))
    );
}

#[test]
fn feature_vector_follows_metadata_order_and_defaults_missing_numeric_to_zero() {
    let metadata = ModelFeatureMetadata {
        numeric_columns: vec!["close_to_zxdkx_pct".to_string(), "missing_pct".to_string()],
        categorical_columns: vec!["env".to_string()],
        categorical_levels: BTreeMap::from([(
            "env".to_string(),
            vec!["weak".to_string(), "strong".to_string()],
        )]),
        categorical_encoding: "one_hot".to_string(),
        categorical_code_maps: BTreeMap::new(),
        feature_names: vec![
            "close_to_zxdkx_pct".to_string(),
            "missing_pct".to_string(),
            "env=weak".to_string(),
            "env=strong".to_string(),
        ],
    };
    let mut row = FactorRow::new("000001.SZ", Method::B2);
    row.factors
        .insert("close_to_zxdkx_pct".to_string(), FactorValue::Number(1.5));
    row.factors
        .insert("env".to_string(), FactorValue::Category("weak".to_string()));

    let vector = build_feature_vector(&row, &metadata).unwrap();
    assert_eq!(vector.feature_names, metadata.feature_names);
    assert_eq!(vector.values, vec![1.5, 0.0, 1.0, 0.0]);
    assert_eq!(vector.missing_numeric_features, vec!["missing_pct"]);
}

#[test]
fn feature_vector_native_categorical_uses_code_maps_and_missing_code() {
    let metadata = ModelFeatureMetadata {
        numeric_columns: vec!["close_to_zxdkx_pct".to_string()],
        categorical_columns: vec!["env".to_string(), "signal_type".to_string()],
        categorical_levels: BTreeMap::from([
            (
                "env".to_string(),
                vec![
                    "weak".to_string(),
                    "neutral".to_string(),
                    "strong".to_string(),
                ],
            ),
            (
                "signal_type".to_string(),
                vec!["rebound".to_string(), "trend_start".to_string()],
            ),
        ]),
        categorical_encoding: "native".to_string(),
        categorical_code_maps: BTreeMap::from([
            (
                "env".to_string(),
                BTreeMap::from([
                    ("weak".to_string(), 0),
                    ("neutral".to_string(), 1),
                    ("strong".to_string(), 2),
                ]),
            ),
            (
                "signal_type".to_string(),
                BTreeMap::from([("rebound".to_string(), 0), ("trend_start".to_string(), 1)]),
            ),
        ]),
        feature_names: vec![
            "close_to_zxdkx_pct".to_string(),
            "env".to_string(),
            "signal_type".to_string(),
        ],
    };
    let mut row = FactorRow::new("000001.SZ", Method::B2);
    row.factors
        .insert("close_to_zxdkx_pct".to_string(), FactorValue::Number(1.5));
    row.factors.insert(
        "env".to_string(),
        FactorValue::Category("neutral".to_string()),
    );

    let vector = build_feature_vector(&row, &metadata).unwrap();

    assert_eq!(vector.feature_names, metadata.feature_names);
    assert_eq!(vector.values, vec![1.5, 1.0, -1.0]);
    assert!(vector.missing_numeric_features.is_empty());
}

#[test]
fn model_feature_metadata_defaults_to_one_hot_for_legacy_models() {
    let metadata: ModelFeatureMetadata = serde_json::from_value(serde_json::json!({
        "numeric_columns": ["close_to_zxdkx_pct"],
        "categorical_columns": ["env"],
        "categorical_levels": {"env": ["weak", "strong"]},
        "feature_names": ["close_to_zxdkx_pct", "env=weak", "env=strong"]
    }))
    .unwrap();

    assert_eq!(metadata.categorical_encoding, "one_hot");
    assert!(metadata.categorical_code_maps.is_empty());
}

#[test]
fn lightgbm_runtime_loads_exported_b2_rank_model() {
    let model_path = std::path::Path::new("tests/fixtures/b2_model/model.txt");
    let model = LightGbmRuntimeModel::from_file(model_path.to_str().unwrap()).unwrap();
    let score = model
        .predict(&vec![0.0; model.num_features() as usize])
        .unwrap();
    assert!(score.is_finite());
}

#[test]
fn lightgbm_runtime_matches_python_native_categorical_predictions() {
    let fixture_dir = std::path::Path::new("tests/fixtures/native_categorical_model");
    let model =
        LightGbmRuntimeModel::from_file(fixture_dir.join("model.txt").to_str().unwrap()).unwrap();
    let metadata: ModelFeatureMetadata =
        serde_json::from_slice(&std::fs::read(fixture_dir.join("model_metadata.json")).unwrap())
            .unwrap();
    let csv = std::fs::read_to_string(fixture_dir.join("predictions.csv")).unwrap();

    for line in csv.lines().skip(1) {
        let parts: Vec<&str> = line.split(',').collect();
        assert_eq!(parts.len(), 4);
        let mut row = FactorRow::new(parts[0], Method::B2);
        row.factors.insert(
            "x".to_string(),
            FactorValue::Number(parts[1].parse::<f64>().unwrap()),
        );
        row.factors.insert(
            "env".to_string(),
            FactorValue::Category(parts[2].to_string()),
        );
        let vector = build_feature_vector(&row, &metadata).unwrap();
        let prediction = model.predict(&vector.values).unwrap();
        let expected = parts[3].parse::<f64>().unwrap();

        assert!(
            (prediction - expected).abs() < 1e-9,
            "{} expected {expected}, got {prediction}",
            parts[0]
        );
    }
}
