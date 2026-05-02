use std::sync::Arc;

use async_trait::async_trait;
use chrono::{Duration, Utc};
use poly_ok_check::contracts::{
    BookTicker, FxQuote, MarketSession, MarketSessionState, OrderLevel,
};
use poly_ok_check::data_hub::{
    DataHubError, FxProvider, HubFreshnessPolicy, InMemoryMarketDataHub, MarketDataHub,
    MarketQuoteProvider, NewsProvider, QuoteUpdate, SessionProvider,
};

fn assert_hub_impl<T: MarketDataHub>() {}

struct StubQuoteProvider;
struct StubFxProvider;
struct StubSessionProvider;
struct StubNewsProvider;

#[async_trait]
impl MarketQuoteProvider for StubQuoteProvider {
    async fn fetch_quote(&self, market_id: &str) -> Result<QuoteUpdate, DataHubError> {
        Ok(QuoteUpdate {
            market_id: market_id.to_string(),
            as_of: Utc::now(),
            book_ticker: BookTicker {
                bids: vec![OrderLevel {
                    price: 0.49,
                    size: 100.0,
                }],
                asks: vec![OrderLevel {
                    price: 0.51,
                    size: 100.0,
                }],
                best_bid: Some(0.49),
                best_ask: Some(0.51),
                midpoint: Some(0.50),
                spread: Some(0.02),
                last_trade: Some(0.50),
            },
        })
    }
}

#[async_trait]
impl FxProvider for StubFxProvider {
    async fn fetch_all(&self, _base_ccy: &str) -> Result<Vec<FxQuote>, DataHubError> {
        Ok(vec![FxQuote {
            pair: "USD/CNY".to_string(),
            rate: 7.2,
            as_of: Utc::now(),
            provider: "stub".to_string(),
        }])
    }
}

#[async_trait]
impl SessionProvider for StubSessionProvider {
    async fn resolve_session(
        &self,
        market_id: &str,
        _ts: chrono::DateTime<Utc>,
    ) -> Result<MarketSession, DataHubError> {
        Ok(MarketSession {
            market_id: market_id.to_string(),
            state: MarketSessionState::Open,
            timezone: "UTC".to_string(),
            opens_at: None,
            closes_at: None,
            note: Some("24x7".to_string()),
        })
    }
}

#[async_trait]
impl NewsProvider for StubNewsProvider {
    async fn fetch_news(
        &self,
        _market_id: &str,
        _since: chrono::DateTime<Utc>,
        _limit: usize,
    ) -> Result<Vec<poly_ok_check::contracts::NewsEvent>, DataHubError> {
        Ok(Vec::new())
    }
}

#[test]
fn trait_contracts_compile() {
    assert_hub_impl::<InMemoryMarketDataHub>();

    let _hub = InMemoryMarketDataHub::new(
        Arc::new(StubQuoteProvider),
        Arc::new(StubFxProvider),
        Arc::new(StubSessionProvider),
        Arc::new(StubNewsProvider),
        HubFreshnessPolicy::default(),
        "USD",
        Duration::hours(8),
        32,
    );
}
