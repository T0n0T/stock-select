use serde_json::json;
use stock_select::engine::artifacts::{
    SelectionRunPaths, read_selection_json, write_selection_json,
};
use stock_select::model::Method;

#[test]
fn selection_run_paths_are_date_method_scoped() {
    let root = tempfile::tempdir().unwrap();
    let paths = SelectionRunPaths::new(root.path(), Method::B2, "2026-05-25");

    assert_eq!(paths.run_dir, root.path().join("select/2026-05-25.b2"));
    assert_eq!(paths.ranked_path(), paths.run_dir.join("ranked.json"));
    assert_eq!(paths.display_path(), paths.run_dir.join("display.json"));
}

#[test]
fn selection_json_write_is_readable() {
    let root = tempfile::tempdir().unwrap();
    let paths = SelectionRunPaths::new(root.path(), Method::B2, "2026-05-25");
    let payload = json!({"rows": [{"code": "000001.SZ", "model_rank": 1}]});

    write_selection_json(&paths.ranked_path(), &payload).unwrap();
    let loaded = read_selection_json(&paths.ranked_path()).unwrap();

    assert_eq!(loaded, payload);
}
