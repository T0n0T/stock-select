use crate::environment_profiles::MethodEnvironmentProfile;

const BASELINE_SCORE_WEIGHTS: [(&str, f64); 5] = [
    ("trend_structure", 0.18),
    ("price_position", 0.18),
    ("volume_behavior", 0.24),
    ("previous_abnormal_move", 0.20),
    ("macd_phase", 0.20),
];

const B2_BASELINE_SCORE_WEIGHTS: [(&str, f64); 5] = [
    ("trend_structure", 0.14),
    ("price_position", 0.22),
    ("volume_behavior", 0.00),
    ("previous_abnormal_move", 0.14),
    ("macd_phase", 0.35),
];

const B1_BASELINE_SCORE_WEIGHTS: [(&str, f64); 5] = [
    ("trend_structure", 0.23),
    ("price_position", 0.20),
    ("volume_behavior", 0.22),
    ("previous_abnormal_move", 0.20),
    ("macd_phase", 0.15),
];

pub fn compute_weighted_total(scores: &[(&str, f64)]) -> f64 {
    round2(weighted_sum(scores, &BASELINE_SCORE_WEIGHTS))
}

pub fn compute_b1_weighted_total(scores: &[(&str, f64)]) -> f64 {
    round2(weighted_sum(scores, &B1_BASELINE_SCORE_WEIGHTS))
}

pub fn compute_b2_weighted_total(scores: &[(&str, f64)], signal: Option<&str>) -> f64 {
    let total = weighted_sum(scores, &B2_BASELINE_SCORE_WEIGHTS) + b2_signal_score(signal) * 0.15;
    round2(total)
}

pub fn compute_weighted_total_for_profile(
    scores: &[(&str, f64)],
    profile: &MethodEnvironmentProfile,
    signal: Option<&str>,
) -> f64 {
    let mut total = 0.0;
    for (field, weight) in &profile.weights {
        total += score_value(scores, field) * weight;
    }
    total += b2_signal_score(signal) * profile.signal_weight.unwrap_or(0.0);
    round2(total)
}

pub fn b2_signal_score(signal: Option<&str>) -> f64 {
    match signal.unwrap_or("").trim().to_ascii_uppercase().as_str() {
        "B3" | "B3+" => 5.0,
        "B2" => 4.0,
        _ => 3.0,
    }
}

pub fn infer_signal_type(
    latest_close: f64,
    latest_open: f64,
    trend_structure: f64,
    volume_behavior: f64,
    price_position: f64,
    ignore_volume_risk: bool,
) -> &'static str {
    if trend_structure <= 2.0 {
        return "distribution_risk";
    }
    if !ignore_volume_risk {
        if volume_behavior <= 1.0 {
            return "distribution_risk";
        }
        if volume_behavior <= 2.0 && trend_structure < 4.0 {
            return "distribution_risk";
        }
    }
    if latest_close >= latest_open && trend_structure >= 4.0 && price_position >= 3.0 {
        return "trend_start";
    }
    "rebound"
}

pub fn infer_verdict(
    total_score: f64,
    volume_behavior: f64,
    signal_type: &str,
    method: &str,
) -> &'static str {
    if volume_behavior <= 1.0 || signal_type == "distribution_risk" {
        return "FAIL";
    }
    let is_hcr = method.trim().eq_ignore_ascii_case("hcr");
    let pass_threshold = if is_hcr { 3.5 } else { 4.0 };
    let watch_threshold = if is_hcr { 3.0 } else { 3.2 };
    if total_score >= pass_threshold {
        return "PASS";
    }
    if total_score >= watch_threshold {
        return "WATCH";
    }
    "FAIL"
}

pub fn infer_verdict_for_profile(
    total_score: f64,
    volume_behavior: f64,
    signal_type: &str,
    profile: &MethodEnvironmentProfile,
) -> &'static str {
    if volume_behavior <= 1.0 || signal_type == "distribution_risk" {
        return "FAIL";
    }
    if total_score >= profile.pass_threshold {
        return "PASS";
    }
    if total_score >= profile.watch_threshold {
        return "WATCH";
    }
    "FAIL"
}

pub fn validate_score_field(field: &str, value: f64) -> anyhow::Result<f64> {
    if !value.is_finite() || !(0.0..=5.0).contains(&value) {
        anyhow::bail!("Invalid score field: {field}");
    }
    Ok(value)
}

fn weighted_sum(scores: &[(&str, f64)], weights: &[(&str, f64)]) -> f64 {
    weights
        .iter()
        .map(|(field, weight)| score_value(scores, field) * weight)
        .sum()
}

fn score_value(scores: &[(&str, f64)], field: &str) -> f64 {
    scores
        .iter()
        .find(|(key, _value)| *key == field)
        .map(|(_key, value)| *value)
        .unwrap_or_else(|| panic!("missing score field: {field}"))
}

fn round2(value: f64) -> f64 {
    format!("{value:.2}")
        .parse::<f64>()
        .expect("formatted finite f64 should parse")
}
