use stock_select::engine::logging::{SelectionEvent, format_event_line};

#[test]
fn format_event_line_matches_existing_progress_style() {
    let line = format_event_line(SelectionEvent {
        stage: "inference",
        status: "done",
        method: "b2",
        rows: Some(108),
        elapsed_secs: Some(0.123),
    });
    assert_eq!(
        line,
        "[selection] stage=inference method=b2 status=done rows=108 elapsed=0.123s"
    );
}
