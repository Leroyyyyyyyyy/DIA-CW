use std::fs::OpenOptions;
use std::io::{BufWriter, Write};
use std::str::FromStr;
use std::time::{SystemTime, UNIX_EPOCH};

use anyhow::{Context, anyhow};
use futures::StreamExt as _;
use polymarket_client_sdk::clob::types::request::OrderBookSummaryRequest;
use polymarket_client_sdk::clob::ws::Client as WsClient;
use polymarket_client_sdk::clob::{Client as ClobClient, Config as ClobConfig};
use polymarket_client_sdk::types::U256;
use serde_json::json;

fn parse_asset_ids_from_env(raw: &str) -> anyhow::Result<Vec<U256>> {
    let ids: Result<Vec<_>, _> = raw
        .split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(U256::from_str)
        .collect();
    let ids = ids.context("Failed to parse POLY_WS_ASSET_IDS as U256 list")?;
    if ids.is_empty() {
        return Err(anyhow!("POLY_WS_ASSET_IDS is empty"));
    }
    Ok(ids)
}

async fn pick_asset_ids_from_api(limit: usize) -> anyhow::Result<Vec<U256>> {
    let client = ClobClient::new("https://clob.polymarket.com", ClobConfig::default())?;
    let page = client
        .sampling_markets(None)
        .await
        .context("sampling_markets failed while auto-selecting assets")?;

    let mut ids = Vec::new();
    for market in page.data {
        if !market.enable_order_book
            || !market.active
            || market.closed
            || market.archived
            || !market.accepting_orders
        {
            continue;
        }

        for token in market.tokens {
            ids.push(token.token_id);
            if ids.len() >= limit {
                return Ok(ids);
            }
        }
    }

    if ids.is_empty() {
        return Err(anyhow!("No suitable assets found from sampling_markets"));
    }
    Ok(ids)
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let asset_ids = match std::env::var("POLY_WS_ASSET_IDS") {
        Ok(raw) => parse_asset_ids_from_env(&raw)?,
        Err(_) => {
            let n = std::env::var("POLY_WS_AUTO_N")
                .ok()
                .and_then(|s| s.parse::<usize>().ok())
                .unwrap_or(12);
            println!(
                "POLY_WS_ASSET_IDS not set, auto-selecting {n} assets from sampling_markets..."
            );
            pick_asset_ids_from_api(n).await?
        }
    };
    let out_path = std::env::var("POLY_WS_OUT").unwrap_or_else(|_| "orderbook.jsonl".to_string());

    let file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&out_path)
        .with_context(|| format!("Failed to open output file: {out_path}"))?;
    let mut writer = BufWriter::new(file);
    let boot_ms = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .context("SystemTime before UNIX_EPOCH")?
        .as_millis();
    let startup = json!({
        "type": "startup",
        "received_ms": boot_ms,
        "assets": asset_ids.iter().map(|x| x.to_string()).collect::<Vec<_>>(),
        "output_file": out_path,
    });
    writeln!(writer, "{startup}")?;
    writer.flush()?;

    // Write a bootstrap REST snapshot so the file is never empty even if WS is quiet.
    let rest_client = ClobClient::new("https://clob.polymarket.com", ClobConfig::default())?;
    for asset_id in asset_ids.iter().take(5) {
        let req = OrderBookSummaryRequest::builder()
            .token_id(*asset_id)
            .build();
        match rest_client.order_book(&req).await {
            Ok(book) => {
                let bids: Vec<String> = book
                    .bids
                    .iter()
                    .map(|x| format!("{}@{}", x.price, x.size))
                    .collect();
                let asks: Vec<String> = book
                    .asks
                    .iter()
                    .map(|x| format!("{}@{}", x.price, x.size))
                    .collect();
                let line = json!({
                    "type": "bootstrap_snapshot",
                    "received_ms": SystemTime::now()
                        .duration_since(UNIX_EPOCH)
                        .context("SystemTime before UNIX_EPOCH")?
                        .as_millis(),
                    "asset_id": asset_id.to_string(),
                    "bids": bids,
                    "asks": asks
                });
                writeln!(writer, "{line}")?;
            }
            Err(e) => {
                let line = json!({
                    "type": "bootstrap_error",
                    "asset_id": asset_id.to_string(),
                    "error": e.to_string()
                });
                writeln!(writer, "{line}")?;
            }
        }
    }
    writer.flush()?;

    let client = WsClient::default();
    println!("ws_client_created");
    println!("subscribing_orderbook...");
    let stream = client.subscribe_orderbook(asset_ids.clone())?;
    let mut stream = Box::pin(stream);
    println!("subscribed_orderbook_ok");

    println!("subscribed_assets: {}", asset_ids.len());
    println!("output_file: {out_path}");
    println!("press Ctrl+C to stop");

    let mut frames: u64 = 0;
    loop {
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {
                println!("received Ctrl+C, stopping...");
                break;
            }
            next = stream.next() => {
                match next {
                    Some(Ok(book)) => {
                        frames += 1;
                        let now_ms = SystemTime::now()
                            .duration_since(UNIX_EPOCH)
                            .context("SystemTime before UNIX_EPOCH")?
                            .as_millis();

                        let bids: Vec<String> = book
                            .bids
                            .iter()
                            .map(|x| format!("{}@{}", x.price, x.size))
                            .collect();
                        let asks: Vec<String> = book
                            .asks
                            .iter()
                            .map(|x| format!("{}@{}", x.price, x.size))
                            .collect();

                        let line = json!({
                            "received_ms": now_ms,
                            "asset_id": book.asset_id.to_string(),
                            "market": book.market,
                            "exchange_ts": book.timestamp,
                            "hash": book.hash,
                            "bids": bids,
                            "asks": asks
                        });
                        writeln!(writer, "{line}")?;
                        writer.flush()?;

                        if frames % 50 == 0 {
                            println!("frames_written: {frames}");
                        }
                    }
                    Some(Err(e)) => {
                        eprintln!("ws_error: {e}");
                    }
                    None => {
                        println!("stream ended by server");
                        break;
                    }
                }
            }
        }
    }

    writer.flush()?;
    println!("done. total_frames: {frames}");
    Ok(())
}
