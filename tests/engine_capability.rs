use std::str::FromStr;
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
    assert!(capability.review_merge);
    assert!(capability.review_list);
    assert!(capability.run);
    assert_eq!(capability.model_family.as_deref(), Some("lightgbm"));
}

#[test]
fn scm_and_pbm_are_independent_model_first_methods() {
    for method_name in ["scm", "pbm"] {
        let method = Method::from_str(method_name).unwrap();
        assert_eq!(method.as_str(), method_name);

        let capability = method_capability(method);
        assert!(capability.screen);
        assert!(capability.factor_extraction);
        assert!(capability.model_inference);
        assert!(capability.llm_review);
        assert!(capability.review_merge);
        assert!(capability.review_list);
        assert!(capability.run);
        assert_eq!(capability.model_family.as_deref(), Some("lightgbm"));
        ensure_model_run_supported(method).unwrap();
    }
}

#[test]
fn capability_struct_is_copyable_for_cli_checks() {
    let capability: SelectionCapability = method_capability(Method::B2);
    let copy = capability;
    assert_eq!(copy.method, Method::B2);
}
