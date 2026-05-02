use std::time::Instant;

use anyhow::{Context, bail};
use polymarket_client_sdk::clob::types::request::OrderBookSummaryRequest;
use polymarket_client_sdk::clob::{Client, Config};
use polymarket_client_sdk::types::U256;

#[derive(Debug, Clone)]
struct Candidate {
    question: String,
    token_id: U256,
}

fn env_usize(name: &str, default: usize) -> usize {
    std::env::var(name)
        .ok()
        .and_then(|v| v.parse::<usize>().ok())
        .unwrap_or(default)
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let started = Instant::now();
    let max_markets = env_usize("POLY_VALIDATE_MARKETS", 80);
    let max_tokens_to_try = env_usize("POLY_VALIDATE_TOKENS", 120);

    let client = Client::new("https://clob.polymarket.com", Config::default())?;
    let ok = client.ok().await.context("clob /ok failed")?;
    println!("ok: {ok}");

    let page = client
        .sampling_markets(None)
        .await
        .context("sampling_markets failed")?;
    println!("sampling_markets_count: {}", page.data.len());
    if page.data.is_empty() {
        bail!("validation failed: sampling_markets returned empty data");
    }

    let mut candidates = Vec::new();
    for market in page.data.into_iter().take(max_markets) {
        if !market.enable_order_book
            || !market.active
            || market.closed
            || market.archived
            || !market.accepting_orders
        {
            continue;
        }

        for token in market.tokens {
            candidates.push(Candidate {
                question: market.question.clone(),
                token_id: token.token_id,
            });
            if candidates.len() >= max_tokens_to_try {
                break;
            }
        }
        if candidates.len() >= max_tokens_to_try {
            break;
        }
    }

    if candidates.is_empty() {
        bail!("validation failed: no active tokens found from sampling_markets");
    }
    println!("candidate_tokens: {}", candidates.len());

    let mut selected: Option<(Candidate, usize, usize)> = None;
    for c in candidates {
        let req = OrderBookSummaryRequest::builder()
            .token_id(c.token_id)
            .build();
        match client.order_book(&req).await {
            Ok(book) => {
                let bid_n = book.bids.len();
                let ask_n = book.asks.len();
                if bid_n > 0 || ask_n > 0 {
                    println!("selected_question: {}", c.question);
                    println!("selected_token_id: {}", c.token_id);
                    println!("order_book_levels: bids={bid_n}, asks={ask_n}");
                    if let Some(top_bid) = book.bids.first() {
                        println!("top_bid: {}@{}", top_bid.price, top_bid.size);
                    }
                    if let Some(top_ask) = book.asks.first() {
                        println!("top_ask: {}@{}", top_ask.price, top_ask.size);
                    }
                    selected = Some((c, bid_n, ask_n));
                    break;
                }
            }
            Err(e) => {
                eprintln!("token {} order_book error: {e}", c.token_id);
            }
        }
    }

    if selected.is_none() {
        bail!("validation failed: no token with non-empty order book found");
    }

    println!(
        "VALIDATION_PASS elapsed_ms={}",
        started.elapsed().as_millis()
    );
    Ok(())
}
