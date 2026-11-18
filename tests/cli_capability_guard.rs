use assert_cmd::Command;
use predicates::prelude::*;

#[test]
fn b2_review_requires_pick_date_for_artifact_lookup() {
    let mut cmd = Command::cargo_bin("stock-select-rs").unwrap();
    cmd.args(["review", "--method", "b2"])
        .assert()
        .failure()
        .stderr(predicate::str::contains("review requires --pick-date"));
}
