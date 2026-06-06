use stock_select::engine::capability::{
    SelectionCapability, ensure_model_run_supported, method_capability,
};
use stock_select::model::Method;

#[test]
fn b2_supports_model_first_run() {
    let capability = method_capability(Method::B2);
    assert_eq!(capability.method, Method::B2);
    assert!(capability.screen);
    assert!(capability.chart);
    assert!(capability.factor_extraction);
    assert!(capability.model_inference);
    assert!(capability.llm_review);
    assert!(capability.review_list);
    assert!(capability.run);
    assert_eq!(capability.model_family.as_deref(), Some("lightgbm"));
}

#[test]
fn b1_does_not_support_model_run_until_model_exists() {
    let capability = method_capability(Method::B1);
    assert_eq!(capability.method, Method::B1);
    assert!(capability.screen);
    assert!(capability.chart);
    assert!(!capability.factor_extraction);
    assert!(!capability.model_inference);
    assert!(!capability.llm_review);
    assert!(!capability.run);
    assert!(capability.model_family.is_none());

    let err = ensure_model_run_supported(Method::B1).unwrap_err();
    assert!(err.to_string().contains("b1 model review is not available"));
}

#[test]
fn b3_supports_screen_without_model_run() {
    let capability = method_capability(Method::B3);
    assert_eq!(capability.method, Method::B3);
    assert!(capability.screen);
    assert!(capability.chart);
    assert!(capability.factor_extraction);
    assert!(!capability.model_inference);
    assert!(!capability.llm_review);
    assert!(!capability.review_list);
    assert!(!capability.run);
    assert!(capability.model_family.is_none());

    let err = ensure_model_run_supported(Method::B3).unwrap_err();
    assert!(err.to_string().contains("b3 model review is not available"));
}

#[test]
fn capability_struct_is_copyable_for_cli_checks() {
    let capability: SelectionCapability = method_capability(Method::B2);
    let copy = capability;
    assert_eq!(copy.method, Method::B2);
}
