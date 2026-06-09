use std::collections::BTreeMap;

use crate::engine::types::DisplayRow;
use crate::model::InstrumentInfo;

pub fn limit_display_rows(
    mut rows: Vec<DisplayRow>,
    limit: Option<usize>,
) -> anyhow::Result<Vec<DisplayRow>> {
    if let Some(limit) = limit {
        if limit == 0 {
            anyhow::bail!("review-list limit must be greater than 0");
        }
        rows.truncate(limit);
    }
    Ok(rows)
}

pub fn format_display_lines(rows: &[DisplayRow]) -> Vec<String> {
    rows.iter()
        .map(|row| {
            let rank = row
                .model_rank
                .map(|value| value.to_string())
                .unwrap_or_else(|| "-".to_string());
            let name = row.name.as_deref().unwrap_or("-");
            let industry = row.industry.as_deref().unwrap_or("-");
            let score = row
                .model_score
                .map(|value| format!("{value:.6}"))
                .unwrap_or_else(|| "-".to_string());
            let bias = review_signal_symbol(row.llm_action.as_deref());
            format!("{rank}\t{}\t{name}\t{industry}\t{score}\t{bias}", row.code)
        })
        .collect()
}

pub fn review_signal_symbol(action: Option<&str>) -> &'static str {
    match action.map(str::to_ascii_uppercase).as_deref() {
        Some("KEEP") => "↑",
        Some("CAUTION") => "→",
        Some("REJECT") => "↓",
        _ => "-",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn row(code: &str, name: Option<&str>, rank: usize) -> DisplayRow {
        DisplayRow {
            code: code.to_string(),
            name: name.map(str::to_string),
            industry: None,
            model_rank: Some(rank),
            model_score: Some(0.5),
            llm_action: None,
            llm_risk_flags: Vec::new(),
            llm_comment: None,
        }
    }

    #[test]
    fn fills_missing_display_instrument_info_without_overwriting_existing_values() {
        let mut instruments = BTreeMap::new();
        instruments.insert(
            "000001.SZ".to_string(),
            InstrumentInfo {
                name: Some("平安银行".to_string()),
                industry: Some("银行".to_string()),
            },
        );
        instruments.insert(
            "000002.SZ".to_string(),
            InstrumentInfo {
                name: Some("万科A".to_string()),
                industry: Some("房地产".to_string()),
            },
        );

        let mut rows = vec![
            row("000001.SZ", None, 1),
            row("000002.SZ", Some("已有名称"), 2),
        ];
        rows[1].industry = Some("已有行业".to_string());

        fill_missing_display_instrument_info(&mut rows, &instruments);

        assert_eq!(rows[0].name.as_deref(), Some("平安银行"));
        assert_eq!(rows[0].industry.as_deref(), Some("银行"));
        assert_eq!(rows[1].name.as_deref(), Some("已有名称"));
        assert_eq!(rows[1].industry.as_deref(), Some("已有行业"));
    }
}

pub fn fill_missing_display_instrument_info(
    rows: &mut [DisplayRow],
    instruments: &BTreeMap<String, InstrumentInfo>,
) {
    for row in rows {
        let Some(instrument) = instruments.get(&row.code) else {
            continue;
        };
        if row
            .name
            .as_deref()
            .map(str::trim)
            .filter(|name| !name.is_empty())
            .is_none()
        {
            row.name = instrument.name.clone();
        }
        if row
            .industry
            .as_deref()
            .map(str::trim)
            .filter(|industry| !industry.is_empty())
            .is_none()
        {
            row.industry = instrument.industry.clone();
        }
    }
}
