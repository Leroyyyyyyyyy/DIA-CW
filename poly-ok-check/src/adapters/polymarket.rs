use std::str::FromStr;
use std::sync::Arc;
use std::time::Duration;

use async_stream::stream;
use async_trait::async_trait;
use chrono::Utc;
use futures::StreamExt;
use polymarket_client_sdk::clob;
use polymarket_client_sdk::clob::types::request::OrderBookSummaryRequest;
use polymarket_client_sdk::clob::ws::Client as WsClient;
use polymarket_client_sdk::types::U256;

use crate::contracts::{BookTicker, OrderLevel};
use crate::data_hub::{
    DataHubError, MarketQuoteProvider, QuoteStream, QuoteStreamProvider, QuoteUpdate,
};

#[derive(Clone)]
pub struct PolymarketQuoteAdapter {
    rest_client: Arc<clob::Client>,
    rest_fallback_interval: Duration,
}

impl PolymarketQuoteAdapter {
    pub fn new(rest_fallback_interval: Duration) -> Result<Self, DataHubError> {
        let rest_client = clob::Client::new(
            "https://clob.polymarket.com",
            clob::Config::builder().use_server_time(true).build(),
        )
        .map_err(|e| DataHubError::Provider(format!("init polymarket rest client failed: {e}")))?;

        Ok(Self {
            rest_client: Arc::new(rest_client),
            rest_fallback_interval,
        })
    }

    fn parse_token_id(&self, market_id: &str) -> Result<U256, DataHubError> {
        U256::from_str(market_id).map_err(|_| {
            DataHubError::Config(format!("invalid token_id in markets config: {market_id}"))
        })
    }

    fn decimal_to_f64<T: std::fmt::Display>(&self, value: T) -> f64 {
        value.to_string().parse::<f64>().unwrap_or(0.0)
    }

    fn map_levels<T, FP, FS>(&self, levels: &[T], price_fn: FP, size_fn: FS) -> Vec<OrderLevel>
    where
        FP: Fn(&T) -> String,
        FS: Fn(&T) -> String,
    {
        levels
            .iter()
            .map(|x| OrderLevel {
                price: self.decimal_to_f64(price_fn(x)),
                size: self.decimal_to_f64(size_fn(x)),
            })
            .collect()
    }

    fn to_book_ticker(&self, bids: Vec<OrderLevel>, asks: Vec<OrderLevel>) -> BookTicker {
        let best_bid = bids.first().map(|x| x.price);
        let best_ask = asks.first().map(|x| x.price);
        let midpoint = match (best_bid, best_ask) {
            (Some(bid), Some(ask)) => Some((bid + ask) / 2.0),
            _ => None,
        };
        let spread = match (best_bid, best_ask) {
            (Some(bid), Some(ask)) => Some((ask - bid).max(0.0)),
            _ => None,
        };
        BookTicker {
            bids,
            asks,
            best_bid,
            best_ask,
            midpoint,
            spread,
            last_trade: midpoint,
        }
    }
}

#[async_trait]
impl MarketQuoteProvider for PolymarketQuoteAdapter {
    async fn fetch_quote(&self, market_id: &str) -> Result<QuoteUpdate, DataHubError> {
        let token_id = self.parse_token_id(market_id)?;
        let req = OrderBookSummaryRequest::builder()
            .token_id(token_id)
            .build();
        let book = self
            .rest_client
            .order_book(&req)
            .await
            .map_err(|e| DataHubError::Provider(format!("order_book failed: {e}")))?;
        let bids = self.map_levels(&book.bids, |x| x.price.to_string(), |x| x.size.to_string());
        let asks = self.map_levels(&book.asks, |x| x.price.to_string(), |x| x.size.to_string());
        Ok(QuoteUpdate {
            market_id: market_id.to_string(),
            as_of: Utc::now(),
            book_ticker: self.to_book_ticker(bids, asks),
        })
    }
}

#[async_trait]
impl QuoteStreamProvider for PolymarketQuoteAdapter {
    async fn stream_quotes(&self, market_ids: Vec<String>) -> Result<QuoteStream, DataHubError> {
        if market_ids.is_empty() {
            return Err(DataHubError::Config(
                "market_ids must not be empty for quote stream".to_string(),
            ));
        }
        let token_ids = market_ids
            .iter()
            .map(|market_id| self.parse_token_id(market_id))
            .collect::<Result<Vec<_>, _>>()?;

        let adapter = self.clone();
        let s = stream! {
            let backoffs_secs = [1u64, 2u64, 5u64, 10u64];
            let mut backoff_idx = 0usize;

            loop {
                let ws_client = WsClient::default();
                match ws_client.subscribe_orderbook(token_ids.clone()) {
                    Ok(ws_stream) => {
                        let mut ws_stream = Box::pin(ws_stream);
                        backoff_idx = 0;
                        while let Some(next) = ws_stream.next().await {
                            match next {
                                Ok(book) => {
                                    let bids = adapter.map_levels(&book.bids, |x| x.price.to_string(), |x| x.size.to_string());
                                    let asks = adapter.map_levels(&book.asks, |x| x.price.to_string(), |x| x.size.to_string());
                                    yield Ok(QuoteUpdate {
                                        market_id: book.asset_id.to_string(),
                                        as_of: Utc::now(),
                                        book_ticker: adapter.to_book_ticker(bids, asks),
                                    });
                                }
                                Err(err) => {
                                    yield Err(DataHubError::Provider(format!("ws orderbook error: {err}")));
                                    break;
                                }
                            }
                        }
                        yield Err(DataHubError::Provider("ws stream ended".to_string()));
                    }
                    Err(err) => {
                        yield Err(DataHubError::Provider(format!("ws subscribe failed: {err}")));
                    }
                }

                let wait_secs = backoffs_secs[backoff_idx.min(backoffs_secs.len() - 1)];
                backoff_idx = (backoff_idx + 1).min(backoffs_secs.len() - 1);

                // During reconnect backoff, keep hub alive with 1s REST fallback polling.
                let fallback_deadline = tokio::time::Instant::now() + Duration::from_secs(wait_secs);
                while tokio::time::Instant::now() < fallback_deadline {
                    for market_id in &market_ids {
                        match adapter.fetch_quote(market_id).await {
                            Ok(quote) => yield Ok(quote),
                            Err(err) => yield Err(err),
                        }
                    }
                    tokio::time::sleep(adapter.rest_fallback_interval).await;
                }
            }
        };
        Ok(Box::pin(s))
    }
}
