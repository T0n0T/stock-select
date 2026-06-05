use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq)]
pub struct MethodEnvironmentProfile {
    pub method: String,
    pub state: String,
    pub weights: BTreeMap<String, f64>,
    pub signal_weight: Option<f64>,
    pub pass_threshold: f64,
    pub watch_threshold: f64,
    pub subscore_mode: BTreeMap<String, String>,
    pub llm_focus: String,
}

pub fn get_method_environment_profile(
    method: &str,
    state: &str,
) -> anyhow::Result<MethodEnvironmentProfile> {
    let method = method.trim().to_ascii_lowercase();
    let state = state.trim().to_ascii_lowercase();
    match (method.as_str(), state.as_str()) {
        ("b1", "weak") => Ok(MethodEnvironmentProfile {
            method,
            state,
            weights: weights([
                ("trend_structure", 0.23),
                ("price_position", 0.22),
                ("volume_behavior", 0.22),
                ("previous_abnormal_move", 0.20),
                ("macd_phase", 0.13),
            ]),
            signal_weight: None,
            pass_threshold: 4.25,
            watch_threshold: 3.3,
            subscore_mode: modes([
                ("price_position", "left_side_favored"),
                ("trend_structure", "support_preserving"),
            ]),
            llm_focus:
                "优先高分给回调充分、支撑有效、赔率优先的结构，弱环境下更严格压制高位和追高样本。"
                    .to_string(),
        }),
        ("b1", "neutral") => Ok(MethodEnvironmentProfile {
            method,
            state,
            weights: weights([
                ("trend_structure", 0.23),
                ("price_position", 0.20),
                ("volume_behavior", 0.22),
                ("previous_abnormal_move", 0.20),
                ("macd_phase", 0.15),
            ]),
            signal_weight: None,
            pass_threshold: 4.0,
            watch_threshold: 3.2,
            subscore_mode: modes([
                ("price_position", "default"),
                ("trend_structure", "default"),
            ]),
            llm_focus: "优先高分给结构完整且赔率仍可接受的回调低点。".to_string(),
        }),
        ("b1", "strong") => Ok(MethodEnvironmentProfile {
            method,
            state,
            weights: weights([
                ("trend_structure", 0.25),
                ("price_position", 0.17),
                ("volume_behavior", 0.23),
                ("previous_abnormal_move", 0.20),
                ("macd_phase", 0.15),
            ]),
            signal_weight: None,
            pass_threshold: 4.0,
            watch_threshold: 3.2,
            subscore_mode: modes([
                ("price_position", "less_left_bias"),
                ("trend_structure", "restart_favored"),
            ]),
            llm_focus: "优先高分给回调后接近再启动，而不是纯防守抄底。".to_string(),
        }),
        ("b2", "weak") => Ok(MethodEnvironmentProfile {
            method,
            state,
            weights: weights([
                ("trend_structure", 0.24),
                ("price_position", 0.14),
                ("volume_behavior", 0.00),
                ("previous_abnormal_move", 0.22),
                ("macd_phase", 0.25),
            ]),
            signal_weight: Some(0.15),
            pass_threshold: 4.15,
            watch_threshold: 3.3,
            subscore_mode: modes([
                ("price_position", "low_risk_required"),
                ("macd_phase", "strict"),
                ("trend_structure", "pullback_only"),
                ("previous_abnormal_move", "strict"),
            ]),
            llm_focus: "弱环境下要压制高位右侧追启动，优先保留位置更安全且承接更强的样本。"
                .to_string(),
        }),
        ("b2", "neutral") => Ok(MethodEnvironmentProfile {
            method,
            state,
            weights: weights([
                ("trend_structure", 0.16),
                ("price_position", 0.25),
                ("volume_behavior", 0.10),
                ("previous_abnormal_move", 0.14),
                ("macd_phase", 0.20),
            ]),
            signal_weight: Some(0.15),
            pass_threshold: 4.0,
            watch_threshold: 3.3,
            subscore_mode: modes([
                ("price_position", "default"),
                ("macd_phase", "default"),
                ("trend_structure", "default"),
                ("previous_abnormal_move", "default"),
            ]),
            llm_focus: "中性环境下优先高分给结构完整且没有明显过热的启动样本。".to_string(),
        }),
        ("b2", "strong") => Ok(MethodEnvironmentProfile {
            method,
            state,
            weights: weights([
                ("trend_structure", 0.10),
                ("price_position", 0.20),
                ("volume_behavior", 0.00),
                ("previous_abnormal_move", 0.20),
                ("macd_phase", 0.35),
            ]),
            signal_weight: Some(0.15),
            pass_threshold: 3.95,
            watch_threshold: 3.3,
            subscore_mode: modes([
                ("price_position", "breakout_tolerant"),
                ("macd_phase", "aggressive"),
                ("trend_structure", "aggressive"),
                ("previous_abnormal_move", "lenient"),
            ]),
            llm_focus: "强环境下优先高分给右侧启动确认和强 MACD 共振。".to_string(),
        }),
        _ => anyhow::bail!("Unsupported environment profile method/state: {method} {state}"),
    }
}

fn weights(items: impl IntoIterator<Item = (&'static str, f64)>) -> BTreeMap<String, f64> {
    items
        .into_iter()
        .map(|(key, value)| (key.to_string(), value))
        .collect()
}

fn modes(
    items: impl IntoIterator<Item = (&'static str, &'static str)>,
) -> BTreeMap<String, String> {
    items
        .into_iter()
        .map(|(key, value)| (key.to_string(), value.to_string()))
        .collect()
}
