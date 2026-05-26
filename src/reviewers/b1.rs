use std::collections::BTreeSet;

#[derive(Debug, Clone, PartialEq)]
pub struct B1DecisionInput<'a> {
    pub signal_type: &'a str,
    pub trend_structure: f64,
    pub price_position: f64,
    pub volume_behavior: f64,
    pub previous_abnormal_move: f64,
    pub macd_phase: f64,
    pub raw_total_score: f64,
    pub environment_state: &'a str,
    pub gate_flags: Vec<&'a str>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct B1ReviewDecision {
    pub score_combo_key: String,
    pub high_return_combo_match: String,
    pub pass_family: Option<String>,
    pub pass_family_tier: String,
    pub verdict: String,
    pub total_score: f64,
    pub score_layer: Option<String>,
    pub score_layer_score: Option<f64>,
}

pub fn decide_b1_review(input: B1DecisionInput<'_>) -> B1ReviewDecision {
    let score_combo_key = build_b1_score_combo_key(&input);
    let high_return_combo_match = classify_b1_high_return_combo(&score_combo_key);
    let (pass_family, pass_family_tier) = classify_b1_pass_family(&input);
    let exact_combo_pass_allowed =
        is_b1_exact_combo_pass_allowed(&score_combo_key, input.environment_state);
    let mut verdict = if high_return_combo_match == "exact" && exact_combo_pass_allowed {
        "PASS".to_string()
    } else {
        infer_b1_family_verdict(pass_family.as_deref(), &pass_family_tier).to_string()
    };
    verdict = apply_b1_environment_verdict_gate(
        &high_return_combo_match,
        pass_family.as_deref(),
        input.environment_state,
        &verdict,
        &input.gate_flags,
    );
    let (score_layer, score_layer_score) = score_b1_layer(
        &verdict,
        input.environment_state,
        &score_combo_key,
        &input.gate_flags,
        &high_return_combo_match,
    );
    let total_score = compute_b1_calibrated_total_score(
        input.raw_total_score,
        &verdict,
        input.environment_state,
        &high_return_combo_match,
        pass_family.as_deref(),
        &pass_family_tier,
        score_layer.as_deref(),
        &input.gate_flags,
    );

    B1ReviewDecision {
        score_combo_key,
        high_return_combo_match,
        pass_family,
        pass_family_tier,
        verdict,
        total_score,
        score_layer,
        score_layer_score,
    }
}

fn build_b1_score_combo_key(input: &B1DecisionInput<'_>) -> String {
    format!(
        "{}|T{}|P{}|V{}|A{}|M{}",
        input.signal_type,
        format_b1_bucket(input.trend_structure),
        format_b1_bucket(input.price_position),
        format_b1_bucket(input.volume_behavior),
        format_b1_bucket(input.previous_abnormal_move),
        format_b1_macd_bucket(input.macd_phase)
    )
}

fn format_b1_bucket(value: f64) -> i64 {
    (value.round() as i64).clamp(1, 5)
}

fn format_b1_macd_bucket(value: f64) -> String {
    let bucket = (value * 2.0).round() / 2.0;
    format!("{:.1}", bucket.clamp(1.0, 5.0))
}

fn classify_b1_high_return_combo(combo_key: &str) -> String {
    if high_return_exact_combos().contains(combo_key) {
        "exact".to_string()
    } else {
        classify_b1_high_return_core_combo(combo_key).to_string()
    }
}

fn classify_b1_high_return_core_combo(combo_key: &str) -> &'static str {
    let parts: Vec<&str> = combo_key.split('|').collect();
    if parts.len() != 6 {
        return "none";
    }
    let signal_type = parts[0];
    let trend = parts[1];
    let price = parts[2];
    let volume = parts[3];
    let abnormal = parts[4];
    let macd = parts[5];
    if abnormal != "A5" {
        return "none";
    }
    if signal_type == "distribution_risk"
        && trend == "T2"
        && ["P3", "P4"].contains(&price)
        && ["V4", "V5"].contains(&volume)
        && macd == "M4.0"
    {
        return "dist_core";
    }
    if signal_type == "rebound"
        && trend == "T3"
        && ["P2", "P3"].contains(&price)
        && volume == "V4"
        && ["M3.5", "M4.0"].contains(&macd)
    {
        return "rebound_core";
    }
    if signal_type == "trend_start"
        && trend == "T4"
        && ["P3", "P4"].contains(&price)
        && volume == "V4"
        && ["M3.5", "M4.0"].contains(&macd)
    {
        return "trend_core";
    }
    "none"
}

fn is_b1_exact_combo_pass_allowed(combo_key: &str, environment_state: &str) -> bool {
    if !high_return_exact_combos().contains(combo_key) {
        return false;
    }
    match environment_state.to_ascii_lowercase().as_str() {
        "neutral" => true,
        "strong" => combo_key == "trend_start|T4|P3|V4|A5|M3.5",
        "weak" => combo_key == "distribution_risk|T2|P4|V4|A5|M4.0",
        _ => false,
    }
}

fn classify_b1_pass_family(input: &B1DecisionInput<'_>) -> (Option<String>, String) {
    if input.signal_type == "rebound"
        && (3.0..=4.0).contains(&input.trend_structure)
        && input.price_position == 3.0
        && input.volume_behavior >= 4.0
        && input.previous_abnormal_move >= 5.0
        && (3.3..=3.8).contains(&input.macd_phase)
    {
        return (Some("rebound".to_string()), "core".to_string());
    }
    if input.signal_type == "rebound"
        && (3.0..=4.0).contains(&input.trend_structure)
        && (2.0..=4.0).contains(&input.price_position)
        && input.volume_behavior >= 3.0
        && input.previous_abnormal_move >= 4.0
        && (3.0..=4.0).contains(&input.macd_phase)
    {
        return (Some("rebound".to_string()), "near".to_string());
    }
    if input.signal_type == "distribution_risk"
        && (2.0..=3.0).contains(&input.trend_structure)
        && input.price_position == 4.0
        && input.volume_behavior >= 4.0
        && input.previous_abnormal_move >= 5.0
        && (3.6..=4.2).contains(&input.macd_phase)
    {
        return (Some("distribution".to_string()), "core".to_string());
    }
    if input.signal_type == "distribution_risk"
        && (2.0..=3.0).contains(&input.trend_structure)
        && (3.0..=5.0).contains(&input.price_position)
        && input.volume_behavior >= 3.0
        && input.previous_abnormal_move >= 4.0
        && (3.2..=4.3).contains(&input.macd_phase)
    {
        return (Some("distribution".to_string()), "near".to_string());
    }
    if input.signal_type == "trend_start"
        && (4.0..=5.0).contains(&input.trend_structure)
        && input.price_position == 3.0
        && input.volume_behavior >= 4.0
        && input.previous_abnormal_move >= 5.0
        && (3.3..=3.8).contains(&input.macd_phase)
    {
        return (Some("trend_start".to_string()), "core".to_string());
    }
    if input.signal_type == "trend_start"
        && input.trend_structure >= 4.0
        && (3.0..=4.0).contains(&input.price_position)
        && input.volume_behavior >= 3.0
        && input.previous_abnormal_move >= 4.0
        && (3.1..=4.0).contains(&input.macd_phase)
    {
        return (Some("trend_start".to_string()), "near".to_string());
    }
    (None, "none".to_string())
}

fn infer_b1_family_verdict(family: Option<&str>, tier: &str) -> &'static str {
    if family.is_none() || tier == "none" {
        "FAIL"
    } else {
        "WATCH"
    }
}

fn apply_b1_environment_verdict_gate(
    high_return_match: &str,
    _family: Option<&str>,
    environment_state: &str,
    current_verdict: &str,
    gate_flags: &[&str],
) -> String {
    if current_verdict != "PASS" {
        return current_verdict.to_string();
    }
    let state = environment_state.to_ascii_lowercase();
    if gate_flags.contains(&"runup_over_limit") {
        return "WATCH".to_string();
    }
    if high_return_match == "exact"
        && ["neutral", "weak"].contains(&state.as_str())
        && gate_flags.contains(&"below_ma25")
    {
        return "WATCH".to_string();
    }
    current_verdict.to_string()
}

fn score_b1_layer(
    verdict: &str,
    environment_state: &str,
    score_combo_key: &str,
    gate_flags: &[&str],
    high_return_match: &str,
) -> (Option<String>, Option<f64>) {
    let state = environment_state.to_ascii_lowercase();
    let flags: BTreeSet<&str> = gate_flags.iter().copied().collect();
    let mut layer_score = 0.0;
    let layer: Option<String>;
    if verdict == "PASS" {
        layer_score = match (state.as_str(), score_combo_key) {
            ("neutral", "distribution_risk|T2|P4|V4|A5|M4.0") => 95.0,
            ("neutral", "rebound|T3|P3|V4|A5|M3.5") => 90.0,
            ("neutral", "trend_start|T4|P3|V4|A5|M3.5") => 78.0,
            ("strong", "trend_start|T4|P3|V4|A5|M3.5") => 82.0,
            ("weak", "distribution_risk|T2|P4|V4|A5|M4.0") => 84.0,
            _ => 70.0,
        };
        if flags.contains("runup_over_limit") {
            layer_score -= 8.0;
        }
        if flags.contains("below_ma25") {
            layer_score -= 6.0;
        }
        layer = Some(
            if layer_score >= 88.0 {
                "PASS-A"
            } else if layer_score >= 80.0 {
                "PASS-B"
            } else {
                "PASS-C"
            }
            .to_string(),
        );
    } else if verdict == "WATCH" {
        layer_score = match (state.as_str(), score_combo_key) {
            ("strong", "trend_start|T4|P3|V4|A5|M3.5") => 76.0,
            ("neutral", "distribution_risk|T2|P4|V4|A5|M4.0") => 72.0,
            ("neutral", "rebound|T3|P3|V4|A5|M3.5") => 70.0,
            ("weak", "distribution_risk|T2|P4|V4|A5|M4.0") => 72.0,
            _ => 50.0,
        };
        let core_watch_score = match (state.as_str(), high_return_match) {
            ("neutral", "dist_core") => 62.0,
            ("neutral", "rebound_core") => 70.0,
            ("neutral", "trend_core") => 70.0,
            ("strong", "trend_core") => 74.0,
            ("weak", "rebound_core") => 58.0,
            _ => 0.0,
        };
        if core_watch_score > layer_score {
            layer_score = core_watch_score;
        }
        if flags.contains("runup_over_limit") {
            layer_score += 2.0;
        }
        if flags.contains("below_ma25") {
            layer_score -= 4.0;
        }
        layer = Some(
            if layer_score >= 70.0 {
                "WATCH-A"
            } else if layer_score >= 55.0 {
                "WATCH-B"
            } else {
                "WATCH-C"
            }
            .to_string(),
        );
    } else {
        layer = None;
    }
    let score = layer.as_ref().map(|_| round2(layer_score));
    (layer, score)
}

fn compute_b1_calibrated_total_score(
    raw_total_score: f64,
    verdict: &str,
    environment_state: &str,
    high_return_match: &str,
    pass_family: Option<&str>,
    pass_family_tier: &str,
    score_layer: Option<&str>,
    gate_flags: &[&str],
) -> f64 {
    let flags: BTreeSet<&str> = gate_flags.iter().copied().collect();
    let state = environment_state.to_ascii_lowercase();
    let mut score = if high_return_match == "exact" {
        let mut score = 4.72;
        if score_layer == Some("PASS-A") {
            score += 0.12;
        } else if score_layer == Some("PASS-B") {
            score += 0.06;
        } else if verdict == "WATCH" {
            score -= 0.22;
        }
        if state == "neutral" {
            score += 0.03;
        }
        score
    } else if ["dist_core", "rebound_core", "trend_core"].contains(&high_return_match) {
        let mut score = match high_return_match {
            "dist_core" => 4.28,
            "rebound_core" => 4.22,
            "trend_core" => 4.18,
            _ => unreachable!(),
        };
        if score_layer == Some("WATCH-A") {
            score += 0.08;
        } else if score_layer == Some("WATCH-C") {
            score -= 0.12;
        }
        score
    } else if pass_family.is_some() && pass_family_tier == "core" {
        3.88
    } else if pass_family.is_some() && pass_family_tier == "near" {
        3.62
    } else {
        raw_total_score.min(3.35)
    };
    if flags.contains("runup_over_limit") {
        score -= 0.18;
    }
    if flags.contains("below_ma25") && high_return_match != "exact" {
        score -= 0.12;
    }
    if flags.contains("cooldown_active") && !["exact", "dist_core"].contains(&high_return_match) {
        score -= 0.08;
    }
    if verdict == "FAIL" {
        score = score.min(3.85);
    }
    round2(score.clamp(0.0, 5.0))
}

fn high_return_exact_combos() -> BTreeSet<&'static str> {
    BTreeSet::from([
        "rebound|T3|P3|V4|A5|M3.5",
        "distribution_risk|T2|P4|V4|A5|M4.0",
        "trend_start|T4|P3|V4|A5|M3.5",
    ])
}

fn round2(value: f64) -> f64 {
    format!("{value:.2}")
        .parse::<f64>()
        .expect("formatted finite f64 should parse")
}
