use anyhow::Context;
use polymarket_client_sdk::clob::types::request::OrderBookSummaryRequest;
use polymarket_client_sdk::clob::{Client, Config};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let client = Client::new("https://clob.polymarket.com", Config::default())?;

    let ok = client.ok().await?;
    println!("ok: {ok}");

    let server_time = client.server_time().await?;
    println!("server_time: {server_time}");

    let page = client
        .sampling_markets(None)
        .await
        .context("sampling_markets failed")?;
    println!("sampling_markets_count: {}", page.data.len());

    let token_id = page
        .data
        .iter()
        .find(|market| {
            market.enable_order_book
                && market.active
                && !market.closed
                && !market.archived
                && market.accepting_orders
                && !market.tokens.is_empty()
        })
        .and_then(|market| market.tokens.first().map(|token| token.token_id))
        .context("No active market with order book found")?;
    println!("selected_token_id: {token_id}");

    let book_req = OrderBookSummaryRequest::builder()
        .token_id(token_id)
        .build();
    let book = client.order_book(&book_req).await?;
    println!(
        "order_book: bids={}, asks={}",
        book.bids.len(),
        book.asks.len()
    );

    let tick = client.tick_size(token_id).await?;
    println!("tick_size: {}", tick.minimum_tick_size);

    let fee = client.fee_rate_bps(token_id).await?;
    println!("fee_rate_bps_base_fee: {}", fee.base_fee);

    let neg_risk = client.neg_risk(token_id).await?;
    println!("neg_risk: {}", neg_risk.neg_risk);

    Ok(())
}
