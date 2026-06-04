#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SelectionEvent<'a> {
    pub stage: &'a str,
    pub status: &'a str,
    pub method: &'a str,
    pub rows: Option<usize>,
    pub elapsed_secs: Option<f64>,
}

pub fn format_event_line(event: SelectionEvent<'_>) -> String {
    let mut line = format!(
        "[selection] stage={} method={} status={}",
        event.stage, event.method, event.status
    );
    if let Some(rows) = event.rows {
        line.push_str(&format!(" rows={rows}"));
    }
    if let Some(elapsed) = event.elapsed_secs {
        line.push_str(&format!(" elapsed={elapsed:.3}s"));
    }
    line
}
