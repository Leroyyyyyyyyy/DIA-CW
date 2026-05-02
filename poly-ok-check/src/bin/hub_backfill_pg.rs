use std::fs;
use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::sync::Arc;

use anyhow::Context;
use poly_ok_check::config::HubConfig;
use poly_ok_check::contracts::HubSlice;
use poly_ok_check::data_hub::HistoricalSliceStore;
use poly_ok_check::storage::PostgresHistoricalSliceStore;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config_path = std::env::var("HUB_CONFIG").unwrap_or_else(|_| "hub.toml".to_string());
    let config = HubConfig::from_file(&config_path).with_context(|| {
        format!(
            "failed to load hub config from {}",
            PathBuf::from(&config_path).display()
        )
    })?;
    config.validate()?;

    if !config.storage.postgres.enabled {
        anyhow::bail!("storage.postgres.enabled must be true for backfill");
    }

    let store: Arc<dyn HistoricalSliceStore> =
        Arc::new(PostgresHistoricalSliceStore::connect(&config.storage.postgres.url).await?);

    let archive_dir = PathBuf::from(&config.archive.dir);
    let mut paths: Vec<_> = fs::read_dir(&archive_dir)?
        .filter_map(Result::ok)
        .map(|x| x.path())
        .filter(|x| x.is_file())
        .collect();
    paths.sort();

    let mut total = 0usize;
    for path in paths {
        if path.extension().and_then(|x| x.to_str()) != Some("jsonl") {
            continue;
        }
        let file = fs::File::open(&path)?;
        let reader = BufReader::new(file);
        for line in reader.lines() {
            let line = line?;
            if line.trim().is_empty() {
                continue;
            }
            let slice: HubSlice = serde_json::from_str(&line)
                .with_context(|| format!("invalid json in {}", path.display()))?;
            store.persist_slice(&slice).await?;
            total += 1;
        }
    }

    println!("backfill complete, persisted slices={total}");
    Ok(())
}
