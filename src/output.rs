use std::time::{SystemTime, UNIX_EPOCH};

use chrono::NaiveDate;

use crate::cache::{atomic_write_json, candidate_output_path};
use crate::model::{Candidate, Method, ScreenResult};

pub fn build_screen_result(
    method: Method,
    pick_date: NaiveDate,
    candidates: Vec<Candidate>,
    stats: std::collections::BTreeMap<String, usize>,
) -> ScreenResult {
    ScreenResult {
        method,
        pick_date,
        pool_source: "turnover-top".to_string(),
        screen_version: (method == Method::B1).then_some(2),
        generated_at: Some(generated_at_epoch_seconds()),
        count: Some(candidates.len()),
        candidates,
        stats,
    }
}

pub fn write_screen_result(
    runtime_root: &std::path::Path,
    result: &ScreenResult,
) -> anyhow::Result<std::path::PathBuf> {
    let path = candidate_output_path(runtime_root, result.pick_date, result.method);
    atomic_write_json(&path, result)?;
    Ok(path)
}

fn generated_at_epoch_seconds() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    seconds.to_string()
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeMap;

    use chrono::NaiveDate;

    use super::*;

    #[test]
    fn writes_candidate_json_with_expected_shape() {
        let temp = tempfile::tempdir().unwrap();
        let pick = NaiveDate::from_ymd_opt(2026, 5, 26).unwrap();
        let result = build_screen_result(
            Method::B2,
            pick,
            vec![Candidate {
                code: "000001.SZ".to_string(),
                pick_date: pick,
                close: 10.5,
                turnover_n: 123.0,
                signal: Some("B2".to_string()),
                yellow_b1: None,
            }],
            BTreeMap::from([("selected".to_string(), 1)]),
        );
        let path = write_screen_result(temp.path(), &result).unwrap();
        let value: serde_json::Value =
            serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(value["method"], "b2");
        assert_eq!(value["pick_date"], "2026-05-26");
        assert_eq!(value["count"], 1);
        assert_eq!(value["pool_source"], "turnover-top");
        assert_eq!(value["candidates"][0]["signal"], "B2");
    }

    #[test]
    fn b1_candidate_json_includes_python_compatibility_fields() {
        let temp = tempfile::tempdir().unwrap();
        let pick = NaiveDate::from_ymd_opt(2026, 5, 26).unwrap();
        let result = build_screen_result(
            Method::B1,
            pick,
            vec![Candidate {
                code: "000001.SZ".to_string(),
                pick_date: pick,
                close: 10.5,
                turnover_n: 123.0,
                signal: None,
                yellow_b1: Some(false),
            }],
            BTreeMap::new(),
        );
        let path = write_screen_result(temp.path(), &result).unwrap();
        let value: serde_json::Value =
            serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
        assert_eq!(value["screen_version"], 2);
        assert_eq!(value["pool_source"], "turnover-top");
        assert_eq!(value["candidates"][0]["yellow_b1"], false);
    }
}
