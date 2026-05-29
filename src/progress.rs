use std::io::Write;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ProgressReporter {
    enabled: bool,
}

impl ProgressReporter {
    pub fn new(enabled: bool) -> Self {
        Self { enabled }
    }

    pub fn enabled(self) -> bool {
        self.enabled
    }

    pub fn step(
        self,
        stage: &str,
        step: &str,
        status: &str,
        fields: impl IntoIterator<Item = (&'static str, String)>,
    ) {
        let mut stderr = std::io::stderr();
        self.write_step(&mut stderr, stage, step, status, fields);
    }

    pub fn write_step<W, K, V>(
        self,
        writer: &mut W,
        stage: &str,
        step: &str,
        status: &str,
        fields: impl IntoIterator<Item = (K, V)>,
    ) where
        W: Write,
        K: AsRef<str>,
        V: AsRef<str>,
    {
        if !self.enabled {
            return;
        }
        let _ = write!(writer, "[{stage}] step={step} status={status}");
        for (key, value) in fields {
            let _ = write!(writer, " {}={}", key.as_ref(), value.as_ref());
        }
        let _ = writeln!(writer);
    }
}
