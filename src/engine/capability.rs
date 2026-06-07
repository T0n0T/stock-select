use crate::model::Method;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SelectionCapability {
    pub method: Method,
    pub screen: bool,
    pub chart: bool,
    pub factor_extraction: bool,
    pub model_inference: bool,
    pub llm_review: bool,
    pub review_merge: bool,
    pub review_list: bool,
    pub run: bool,
    pub analyze_symbol: bool,
    pub model_family: Option<&'static str>,
}

pub fn method_capability(method: Method) -> SelectionCapability {
    match method {
        Method::B2 => SelectionCapability {
            method,
            screen: true,
            chart: true,
            factor_extraction: true,
            model_inference: true,
            llm_review: true,
            review_merge: true,
            review_list: true,
            run: true,
            analyze_symbol: true,
            model_family: Some("lightgbm"),
        },
        Method::B1 => SelectionCapability {
            method,
            screen: true,
            chart: true,
            factor_extraction: false,
            model_inference: false,
            llm_review: false,
            review_merge: false,
            review_list: false,
            run: false,
            analyze_symbol: true,
            model_family: None,
        },
        Method::B3 => SelectionCapability {
            method,
            screen: true,
            chart: true,
            factor_extraction: true,
            model_inference: true,
            llm_review: true,
            review_merge: true,
            review_list: true,
            run: true,
            analyze_symbol: true,
            model_family: Some("lightgbm"),
        },
        Method::Lsh => SelectionCapability {
            method,
            screen: true,
            chart: true,
            factor_extraction: true,
            model_inference: true,
            llm_review: true,
            review_merge: true,
            review_list: true,
            run: true,
            analyze_symbol: true,
            model_family: Some("lightgbm"),
        },
        Method::Dribull => SelectionCapability {
            method,
            screen: true,
            chart: true,
            factor_extraction: false,
            model_inference: false,
            llm_review: false,
            review_merge: false,
            review_list: false,
            run: false,
            analyze_symbol: false,
            model_family: None,
        },
    }
}

pub fn ensure_model_run_supported(method: Method) -> anyhow::Result<()> {
    let capability = method_capability(method);
    if capability.run && capability.model_inference {
        return Ok(());
    }

    anyhow::bail!(
        "{} model review is not available: no trained LightGBM model artifact is enabled for this method",
        method.as_str()
    )
}
