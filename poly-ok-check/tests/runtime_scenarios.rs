use std::sync::Arc;

use async_trait::async_trait;
use chrono::{Duration, Utc};
use futures::StreamExt;
use poly_ok_check::contracts::{
    BookTicker, FxQuote, MarketSession, MarketSessionState, NewsEvent, OrderLevel,
};
use poly_ok_check::data_hub::{
    DataHubError, FxProvider, HubFreshnessPolicy, InMemoryMarketDataHub, MarketDataHub,
    MarketQuoteProvider, NewsProvider, QuoteUpdate, SessionProvider,
};
use poly_ok_check::storage::{InMemoryHistoricalSliceStore, InMemoryRealtimeSliceStore};

fn make_quote(market_id: &str, as_of: chrono::DateTime<Utc>) -> QuoteUpdate {
    QuoteUpdate {
        market_id: market_id.to_string(),
        as_of,
        book_ticker: BookTicker {
            bids: vec![OrderLevel {
                price: 0.49,
                size: 220.0,
            }],
            asks: vec![OrderLevel {
                price: 0.51,
                size: 240.0,
            }],
            best_bid: Some(0.49),
            best_ask: Some(0.51),
            midpoint: Some(0.50),
            spread: Some(0.02),
            last_trade: Some(0.495),
        },
    }
}

struct OkQuoteProvider;
struct OkFxProvider;
struct FailFxProvider;
struct AlwaysOpenProvider;
struct OkNewsProvider;
struct FailNewsProvider;

#[async_trait]
impl MarketQuoteProvider for OkQuoteProvider {
    async fn fetch_quote(&self, market_id: &str) -> Result<QuoteUpdate, DataHubError> {
        Ok(make_quote(market_id, Utc::now()))
    }
}

#[async_trait]
impl FxProvider for OkFxProvider {
    async fn fetch_all(&self, _base_ccy: &str) -> Result<Vec<FxQuote>, DataHubError> {
        Ok(vec![FxQuote {
            pair: "USD/CNY".to_string(),
            rate: 7.2,
            as_of: Utc::now(),
            provider: "ok-fx".to_string(),
        }])
    }
}

#[async_trait]
impl FxProvider for FailFxProvider {
    async fn fetch_all(&self, _base_ccy: &str) -> Result<Vec<FxQuote>, DataHubError> {
        Err(DataHubError::Provider("fx down".to_string()))
    }
}

#[async_trait]
impl SessionProvider for AlwaysOpenProvider {
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
impl NewsProvider for OkNewsProvider {
    async fn fetch_news(
        &self,
        market_id: &str,
        since: chrono::DateTime<Utc>,
        _limit: usize,
    ) -> Result<Vec<NewsEvent>, DataHubError> {
        Ok(vec![NewsEvent {
            event_id: "news-1".to_string(),
            market_id: market_id.to_string(),
            headline: "macro headline".to_string(),
            source: "test".to_string(),
            url: None,
            published_at: since + Duration::minutes(1),
            tags: vec!["macro".to_string()],
        }])
    }
}

#[async_trait]
impl NewsProvider for FailNewsProvider {
    async fn fetch_news(
        &self,
        _market_id: &str,
        _since: chrono::DateTime<Utc>,
        _limit: usize,
    ) -> Result<Vec<NewsEvent>, DataHubError> {
        Err(DataHubError::Provider("rss down".to_string()))
    }
}

#[tokio::test]
async fn normal_path_snapshot_is_complete() {
    let hub = InMemoryMarketDataHub::new(
        Arc::new(OkQuoteProvider),
        Arc::new(OkFxProvider),
        Arc::new(AlwaysOpenProvider),
        Arc::new(OkNewsProvider),
        HubFreshnessPolicy::default(),
        "USD",
        Duration::hours(8),
        32,
    );

    let snapshot = hub.get_snapshot("market-1").await.expect("snapshot");
    assert!(!snapshot.quality_flags.partial);
    assert!(!snapshot.fx_context.is_empty());
    assert!(!snapshot.news_refs.is_empty());
    assert!(!snapshot.carried_forward);
}

#[tokio::test]
async fn degraded_path_marks_partial_when_fx_or_news_fails() {
    let hub = InMemoryMarketDataHub::new(
        Arc::new(OkQuoteProvider),
        Arc::new(FailFxProvider),
        Arc::new(AlwaysOpenProvider),
        Arc::new(FailNewsProvider),
        HubFreshnessPolicy::default(),
        "USD",
        Duration::hours(8),
        32,
    );

    let snapshot = hub.get_snapshot("market-2").await.expect("snapshot");
    assert!(snapshot.quality_flags.partial);
}

#[tokio::test]
async fn stale_path_marks_stale_but_keeps_output() {
    struct StaleQuoteProvider;

    #[async_trait]
    impl MarketQuoteProvider for StaleQuoteProvider {
        async fn fetch_quote(&self, market_id: &str) -> Result<QuoteUpdate, DataHubError> {
            Ok(make_quote(
                market_id,
                Utc::now() - Duration::milliseconds(4_000),
            ))
        }
    }

    let hub = InMemoryMarketDataHub::new(
        Arc::new(StaleQuoteProvider),
        Arc::new(OkFxProvider),
        Arc::new(AlwaysOpenProvider),
        Arc::new(OkNewsProvider),
        HubFreshnessPolicy {
            soft_slo_ms: 500,
            stale_after_ms: 2_000,
        },
        "USD",
        Duration::hours(8),
        32,
    );

    let snapshot = hub.get_snapshot("market-3").await.expect("snapshot");
    assert!(snapshot.quality_flags.stale);
    assert!(snapshot.quality_flags.partial);
}

#[tokio::test]
async fn subscribe_receives_updates() {
    let hub = Arc::new(InMemoryMarketDataHub::new(
        Arc::new(OkQuoteProvider),
        Arc::new(OkFxProvider),
        Arc::new(AlwaysOpenProvider),
        Arc::new(OkNewsProvider),
        HubFreshnessPolicy::default(),
        "USD",
        Duration::hours(8),
        32,
    ));

    let mut stream = hub
        .subscribe_snapshots("market-4")
        .await
        .expect("subscribe");

    let _ = hub.get_snapshot("market-4").await.expect("snapshot");
    let next = tokio::time::timeout(std::time::Duration::from_secs(2), stream.next())
        .await
        .expect("timeout waiting for stream item");
    assert!(next.is_some());
}

#[tokio::test]
async fn slice_assembly_keeps_recent_snapshots_fresh() {
    let hub = InMemoryMarketDataHub::new(
        Arc::new(OkQuoteProvider),
        Arc::new(OkFxProvider),
        Arc::new(AlwaysOpenProvider),
        Arc::new(OkNewsProvider),
        HubFreshnessPolicy::default(),
        "USD",
        Duration::hours(8),
        32,
    );

    let first = Utc::now();
    let _ = hub
        .ingest_quote(make_quote("market-5", first))
        .await
        .expect("ingest");

    let hub_ts = first + Duration::milliseconds(100);
    let slice = hub
        .assemble_and_publish_slice(hub_ts, &["market-5".to_string()])
        .await
        .expect("slice");
    let m = slice.markets.get("market-5").expect("market in slice");
    assert_eq!(slice.hub_ts, hub_ts);
    assert!(!m.carried_forward);
    assert!(!m.quality_flags.stale);
    assert!(!m.quality_flags.partial);
}

#[tokio::test]
async fn slice_assembly_marks_warn_band_as_partial_without_stale() {
    let hub = InMemoryMarketDataHub::new(
        Arc::new(OkQuoteProvider),
        Arc::new(OkFxProvider),
        Arc::new(AlwaysOpenProvider),
        Arc::new(OkNewsProvider),
        HubFreshnessPolicy::default(),
        "USD",
        Duration::hours(8),
        32,
    );

    let first = Utc::now();
    let _ = hub
        .ingest_quote(make_quote("market-5b", first))
        .await
        .expect("ingest");

    let hub_ts = first + Duration::seconds(1);
    let slice = hub
        .assemble_and_publish_slice(hub_ts, &["market-5b".to_string()])
        .await
        .expect("slice");
    let m = slice.markets.get("market-5b").expect("market in slice");
    assert!(!m.carried_forward);
    assert!(!m.quality_flags.stale);
    assert!(m.quality_flags.partial);
}

#[tokio::test]
async fn slice_assembly_marks_stale_slices_as_carried_forward() {
    let hub = InMemoryMarketDataHub::new(
        Arc::new(OkQuoteProvider),
        Arc::new(OkFxProvider),
        Arc::new(AlwaysOpenProvider),
        Arc::new(OkNewsProvider),
        HubFreshnessPolicy::default(),
        "USD",
        Duration::hours(8),
        32,
    );

    let first = Utc::now();
    let _ = hub
        .ingest_quote(make_quote("market-5c", first))
        .await
        .expect("ingest");

    let hub_ts = first + Duration::seconds(3);
    let slice = hub
        .assemble_and_publish_slice(hub_ts, &["market-5c".to_string()])
        .await
        .expect("slice");
    let m = slice.markets.get("market-5c").expect("market in slice");
    assert!(m.carried_forward);
    assert!(m.quality_flags.stale);
    assert!(m.quality_flags.partial);
}

#[tokio::test]
async fn realtime_and_historical_fallback_for_slice_queries() {
    let realtime = Arc::new(InMemoryRealtimeSliceStore::new());
    let historical = Arc::new(InMemoryHistoricalSliceStore::new());
    let hub = InMemoryMarketDataHub::new(
        Arc::new(OkQuoteProvider),
        Arc::new(OkFxProvider),
        Arc::new(AlwaysOpenProvider),
        Arc::new(OkNewsProvider),
        HubFreshnessPolicy::default(),
        "USD",
        Duration::hours(8),
        32,
    )
    .with_realtime_store(realtime)
    .with_historical_store(historical);

    let now = Utc::now();
    let _ = hub
        .ingest_quote(make_quote("market-6", now))
        .await
        .expect("ingest");
    let _ = hub
        .assemble_and_publish_slice(now, &["market-6".to_string()])
        .await
        .expect("slice");

    let fetched = hub.get_slice(now).await.expect("get slice");
    assert_eq!(fetched.hub_ts, now);

    let by_market = hub
        .get_market_at_time("market-6", now)
        .await
        .expect("market at time");
    assert_eq!(by_market.market_id, "market-6");

    let range = hub
        .list_slices_range(now - Duration::seconds(1), now + Duration::seconds(1), 10)
        .await
        .expect("range");
    assert!(!range.is_empty());
}

#[tokio::test]
async fn bootstrap_markets_seeds_first_slice_with_real_snapshot() {
    let hub = InMemoryMarketDataHub::new(
        Arc::new(OkQuoteProvider),
        Arc::new(OkFxProvider),
        Arc::new(AlwaysOpenProvider),
        Arc::new(OkNewsProvider),
        HubFreshnessPolicy::default(),
        "USD",
        Duration::hours(8),
        32,
    );

    let summary = hub.bootstrap_markets(&["market-7".to_string()]).await;
    assert_eq!(summary.ok_markets, 1);
    assert_eq!(summary.failed_markets, 0);

    let slice = hub
        .assemble_and_publish_slice(Utc::now(), &["market-7".to_string()])
        .await
        .expect("slice");
    let market = slice.markets.get("market-7").expect("market in slice");
    assert!(!market.book_ticker.bids.is_empty());
    assert_ne!(market.session_state.state, MarketSessionState::Halted);
}
