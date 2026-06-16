use assert_cmd::Command;
use predicates::prelude::*;

fn write_file(path: &std::path::Path) {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).unwrap();
    }
    std::fs::write(path, "artifact\n").unwrap();
}

#[test]
fn clean_intraday_removes_runtime_intraday_artifacts_without_touching_models_or_eod() {
    let temp = tempfile::tempdir().unwrap();
    let runtime = temp.path();

    let intraday_paths = [
        runtime.join("candidates/2026-06-05.intraday.b2.json"),
        runtime.join("prepared/2026-06-05.intraday.bin.zst"),
        runtime.join("prepared/2026-06-05.intraday.bin"),
        runtime.join("prepared/2026-06-05.intraday.meta.json"),
        runtime.join("factors/2026-06-05.intraday.b2/factors.json"),
        runtime.join("charts/2026-06-05.intraday.b2/000001.SZ_day.png"),
        runtime.join("charts/2026-06-05.intraday.b2.payload.json"),
        runtime.join("select/2026-06-05.intraday.b2/display.json"),
    ];
    for path in &intraday_paths {
        write_file(path);
    }

    let retained_paths = [
        runtime.join("candidates/2026-06-05.b2.json"),
        runtime.join("prepared/2026-06-05.bin.zst"),
        runtime.join("prepared/2026-06-05.meta.json"),
        runtime.join("factors/2026-06-05.b2/factors.json"),
        runtime.join("charts/2026-06-05.b2/000001.SZ_day.png"),
        runtime.join("select/2026-06-05.b2/display.json"),
        runtime.join("models/b2/model_state.json"),
        runtime.join("models/b2_intraday/model.txt"),
        runtime.join("models/archive/b2_intraday/20260605T120000Z/model.txt"),
    ];
    for path in &retained_paths {
        write_file(path);
    }

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "clean-intraday",
        "--runtime-root",
        runtime.to_str().unwrap(),
    ])
    .assert()
    .success()
    .stdout(predicate::str::contains(
        "clean-intraday complete: removed=8",
    ));

    for path in &intraday_paths {
        assert!(!path.exists(), "{} should be removed", path.display());
    }
    for path in &retained_paths {
        assert!(path.exists(), "{} should be retained", path.display());
    }
}

#[test]
fn clean_intraday_dry_run_reports_intraday_artifacts_without_deleting() {
    let temp = tempfile::tempdir().unwrap();
    let runtime = temp.path();
    let intraday_path = runtime.join("select/2026-06-05.intraday.b2/display.json");
    let eod_path = runtime.join("select/2026-06-05.b2/display.json");
    write_file(&intraday_path);
    write_file(&eod_path);

    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args([
        "clean-intraday",
        "--runtime-root",
        runtime.to_str().unwrap(),
        "--dry-run",
    ])
    .assert()
    .success()
    .stdout(predicate::str::contains(
        "clean-intraday dry-run: removable=1",
    ));

    assert!(intraday_path.exists());
    assert!(eod_path.exists());
}
