use stock_select_rs::progress::ProgressReporter;

#[test]
fn progress_reporter_writes_structured_lines_when_enabled() {
    let mut out = Vec::new();
    let reporter = ProgressReporter::new(true);

    reporter.write_step(&mut out, "screen", "fetch", "start", [("rows", "0")]);

    let line = String::from_utf8(out).unwrap();
    assert_eq!(line, "[screen] step=fetch status=start rows=0\n");
}

#[test]
fn progress_reporter_is_silent_when_disabled() {
    let mut out = Vec::new();
    let reporter = ProgressReporter::new(false);

    reporter.write_step(&mut out, "chart", "render", "start", [("parts", "2")]);

    assert!(out.is_empty());
}
