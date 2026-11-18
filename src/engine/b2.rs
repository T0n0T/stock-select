use crate::engine::types::{FactorRow, FactorValue};

pub(crate) fn adjust_b2_cyq_post_rerank_score(score: f64, row: &FactorRow) -> f64 {
    match factor_category(row, "env") {
        Some("neutral") => {
            let penalty = factor_number(row, "cyq_winner_rate")
                .map(|winner_rate| ((winner_rate - 80.0) / 20.0).clamp(0.0, 1.0) * 0.14)
                .unwrap_or(0.0);
            score - penalty
        }
        Some("strong") => {
            let penalty = match factor_number(row, "cyq_cost_90_width_pct") {
                Some(width) if width > 25.0 => 0.35,
                _ => 0.0,
            };
            score - penalty
        }
        _ => score,
    }
}

fn factor_number(row: &FactorRow, key: &str) -> Option<f64> {
    match row.factors.get(key) {
        Some(FactorValue::Number(value)) if value.is_finite() => Some(*value),
        _ => None,
    }
}

fn factor_category<'a>(row: &'a FactorRow, key: &str) -> Option<&'a str> {
    match row.factors.get(key) {
        Some(FactorValue::Category(value)) => Some(value.as_str()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::model::Method;

    fn factor_row(code: &str, env: &str) -> FactorRow {
        let mut row = FactorRow::new(code, Method::B2);
        row.factors
            .insert("env".to_string(), FactorValue::Category(env.to_string()));
        row
    }

    #[test]
    fn cyq_post_rerank_penalizes_neutral_high_winner_rate() {
        let mut row = factor_row("000001.SZ", "neutral");
        row.factors
            .insert("cyq_winner_rate".to_string(), FactorValue::Number(90.0));

        let adjusted = adjust_b2_cyq_post_rerank_score(1.0, &row);

        assert!((adjusted - 0.93).abs() < 1e-9);
    }

    #[test]
    fn cyq_post_rerank_penalizes_strong_wide_cost_distribution() {
        let mut row = factor_row("000001.SZ", "strong");
        row.factors.insert(
            "cyq_cost_90_width_pct".to_string(),
            FactorValue::Number(25.1),
        );

        let adjusted = adjust_b2_cyq_post_rerank_score(1.0, &row);

        assert!((adjusted - 0.65).abs() < 1e-9);
    }

    #[test]
    fn cyq_post_rerank_leaves_weak_environment_unchanged() {
        let mut row = factor_row("000001.SZ", "weak");
        row.factors
            .insert("cyq_winner_rate".to_string(), FactorValue::Number(100.0));
        row.factors.insert(
            "cyq_cost_90_width_pct".to_string(),
            FactorValue::Number(40.0),
        );

        let adjusted = adjust_b2_cyq_post_rerank_score(1.0, &row);

        assert_eq!(adjusted, 1.0);
    }
}
