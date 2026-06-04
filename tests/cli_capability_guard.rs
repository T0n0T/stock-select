use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn review_rejects_b1_without_model_support() {
    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args(["review", "--method", "b1"])
        .assert()
        .failure()
        .stderr(predicate::str::contains("b1 model review is not available"));
}

#[test]
fn run_rejects_b1_without_model_support() {
    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args(["run", "--method", "b1"])
        .assert()
        .failure()
        .stderr(predicate::str::contains("b1 model review is not available"));
}

#[test]
fn b2_review_requires_pick_date_for_artifact_lookup() {
    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args(["review", "--method", "b2"])
        .assert()
        .failure()
        .stderr(predicate::str::contains("review requires --pick-date"));
}
