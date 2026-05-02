use std::fs::{self, File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use chrono::{Datelike, NaiveDate, Utc};

use crate::contracts::HubSlice;
use crate::data_hub::{DataHubError, SliceArchive};

struct ArchiveState {
    current_date: NaiveDate,
    writer: BufWriter<File>,
    last_cleanup_date: NaiveDate,
}

pub struct JsonlSliceArchiveWriter {
    root_dir: PathBuf,
    file_prefix: String,
    retention_days: i64,
    state: Mutex<Option<ArchiveState>>,
}

impl JsonlSliceArchiveWriter {
    pub fn new(
        root_dir: impl Into<PathBuf>,
        file_prefix: impl Into<String>,
        retention_days: i64,
    ) -> Result<Self, DataHubError> {
        let root_dir = root_dir.into();
        fs::create_dir_all(&root_dir).map_err(|e| DataHubError::Io(e.to_string()))?;
        Ok(Self {
            root_dir,
            file_prefix: file_prefix.into(),
            retention_days: retention_days.max(1),
            state: Mutex::new(None),
        })
    }

    fn file_path_for(&self, day: NaiveDate) -> PathBuf {
        self.root_dir.join(format!(
            "{}-{:04}-{:02}-{:02}.jsonl",
            self.file_prefix,
            day.year(),
            day.month(),
            day.day()
        ))
    }

    fn open_writer_for(&self, day: NaiveDate) -> Result<BufWriter<File>, DataHubError> {
        let path = self.file_path_for(day);
        let file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(path)
            .map_err(|e| DataHubError::Io(e.to_string()))?;
        Ok(BufWriter::new(file))
    }

    fn maybe_cleanup(&self, now_day: NaiveDate) -> Result<(), DataHubError> {
        let cutoff = now_day - chrono::Duration::days(self.retention_days);
        let entries = fs::read_dir(&self.root_dir).map_err(|e| DataHubError::Io(e.to_string()))?;
        for entry in entries {
            let entry = entry.map_err(|e| DataHubError::Io(e.to_string()))?;
            let path = entry.path();
            if !path.is_file() {
                continue;
            }
            if let Some(day) = self.extract_day_from_filename(&path) {
                if day < cutoff {
                    let _ = fs::remove_file(path);
                }
            }
        }
        Ok(())
    }

    fn extract_day_from_filename(&self, path: &Path) -> Option<NaiveDate> {
        let file_name = path.file_name()?.to_string_lossy();
        let prefix = format!("{}-", self.file_prefix);
        if !file_name.starts_with(&prefix) || !file_name.ends_with(".jsonl") {
            return None;
        }
        let date_part = file_name
            .strip_prefix(&prefix)?
            .strip_suffix(".jsonl")?
            .to_string();
        NaiveDate::parse_from_str(&date_part, "%Y-%m-%d").ok()
    }
}

impl SliceArchive for JsonlSliceArchiveWriter {
    fn archive_slice(&self, slice: &HubSlice) -> Result<(), DataHubError> {
        let now_day = Utc::now().date_naive();
        let mut guard = self
            .state
            .lock()
            .map_err(|_| DataHubError::Io("archive lock poisoned".to_string()))?;

        let needs_rotate = match guard.as_ref() {
            Some(state) => state.current_date != now_day,
            None => true,
        };
        if needs_rotate {
            let writer = self.open_writer_for(now_day)?;
            *guard = Some(ArchiveState {
                current_date: now_day,
                writer,
                last_cleanup_date: now_day,
            });
        }

        if let Some(state) = guard.as_mut() {
            if state.last_cleanup_date != now_day {
                self.maybe_cleanup(now_day)?;
                state.last_cleanup_date = now_day;
            }
            let line = serde_json::to_string(slice).map_err(|e| DataHubError::Io(e.to_string()))?;
            writeln!(state.writer, "{line}").map_err(|e| DataHubError::Io(e.to_string()))?;
            state
                .writer
                .flush()
                .map_err(|e| DataHubError::Io(e.to_string()))?;
        }

        Ok(())
    }
}
