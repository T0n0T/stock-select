use std::fs;
use std::path::PathBuf;

use serde_json::Value;

fn b2_python_golden_root() -> PathBuf {
    PathBuf::from(std::env::var("HOME").expect("HOME must be set"))
        .join(".agents/skills/stock-select/runtime/reviews/2026-05-25.b2")
}

#[test]
fn b2_python_golden_fixture_shape_is_stable() {
    let root = b2_python_golden_root();
    let summary: Value =
        serde_json::from_slice(&fs::read(root.join("summary.json")).unwrap()).unwrap();
    if summary.get("environment_snapshot").is_some() {
        eprintln!(
            "skip b2 Python golden fixture shape check; runtime contains Rust native review summary: {root:?}"
        );
        return;
    }
    assert_eq!(summary["pick_date"], "2026-05-25");
    assert_eq!(summary["method"], "b2");
    assert_eq!(summary["reviewed_count"], 139);
    assert_eq!(summary["recommendations"].as_array().unwrap().len(), 0);
    assert_eq!(summary["excluded"].as_array().unwrap().len(), 139);
    assert_eq!(summary["failures"].as_array().unwrap().len(), 0);

    let review_files = fs::read_dir(&root)
        .unwrap()
        .map(|entry| entry.unwrap().path())
        .filter(|path| path.extension().and_then(|value| value.to_str()) == Some("json"))
        .filter(|path| {
            !matches!(
                path.file_name().and_then(|value| value.to_str()),
                Some("summary.json" | "llm_review_tasks.json")
            )
        })
        .collect::<Vec<_>>();
    assert_eq!(review_files.len(), 139);

    let tasks: Value =
        serde_json::from_slice(&fs::read(root.join("llm_review_tasks.json")).unwrap()).unwrap();
    assert_eq!(tasks["pick_date"], "2026-05-25");
    assert_eq!(tasks["method"], "b2");
    assert!(
        tasks["prompt_path"]
            .as_str()
            .is_some_and(|value| value.ends_with("prompt-b2.md"))
    );
    assert_eq!(tasks["max_concurrency"], 6);
    assert_eq!(tasks["tasks"].as_array().unwrap().len(), 5);
}
