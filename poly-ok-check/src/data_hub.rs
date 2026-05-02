use std::collections::{BTreeMap, HashMap};
use std::pin::Pin;
use std::sync::Arc;

use async_trait::async_trait;
use chrono::{DateTime, Duration, Utc};
use futures::Stream;
use thiserror::Error;
use tokio::sync::{RwLock, broadcast};
use tokio_stream::StreamExt;
use tokio_stream::wrappers::BroadcastStream;

use crate::contracts::{
    BookTicker, FxQuote, HubSlice, HubSliceMeta, MarketSession, MarketSessionState, MarketSnapshot,
    NewsEvent, QualityFlags,
};

pub type SnapshotStream = Pin<Box<dyn Stream<Item = MarketSnapshot> + Send>>;
pub type SliceStream = Pin<Box<dyn Stream<Item = HubSlice> + Send>>;
pub type QuoteStream = Pin<Box<dyn Stream<Item = Result<QuoteUpdate, DataHubError>> + Send>>;

#[derive(Debug, Error)]
pub enum DataHubError {
    #[error("provider error: {0}")]
    Provider(String),
    #[error("not found: {0}")]
    NotFound(String),
    #[error("io error: {0}")]
    Io(String),
    #[error("config error: {0}")]
    Config(String),
    #[error("storage error: {0}")]
    Storage(String),
}

#[derive(Debug, Clone)]
pub struct HubFreshnessPolicy {
    pub soft_slo_ms: i64,
    pub stale_after_ms: i64,
}

impl Default for HubFreshnessPolicy {
    fn default() -> Self {
        Self {
            soft_slo_ms: 500,
            stale_after_ms: 2_000,
        }
    }
}

#[derive(Debug, Clone)]
pub struct RetryPolicy {
    pub backoff_secs: Vec<u64>,
}

impl Default for RetryPolicy {
    fn default() -> Self {
        Self {
            backoff_secs: vec![1, 2, 5, 10, 30],
        }
    }
}

#[derive(Debug, Clone)]
pub struct QuoteUpdate {
    pub market_id: String,
    pub as_of: DateTime<Utc>,
    pub book_ticker: BookTicker,
}

#[derive(Debug, Clone, Default)]
pub struct BootstrapSummary {
    pub ok_markets: usize,
    pub failed_markets: usize,
    pub last_error: Option<String>,
}

#[async_trait]
pub trait MarketDataHub: Send + Sync {
    async fn get_snapshot(&self, market_id: &str) -> Result<MarketSnapshot, DataHubError>;
    async fn get_fx(&self, base_ccy: &str) -> Result<Vec<FxQuote>, DataHubError>;
    async fn get_session(
        &self,
        market_id: &str,
        ts: DateTime<Utc>,
    ) -> Result<MarketSession, DataHubError>;
    async fn get_news(
        &self,
        market_id: &str,
        since: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<NewsEvent>, DataHubError>;
    async fn subscribe_snapshots(&self, market_id: &str) -> Result<SnapshotStream, DataHubError>;
    async fn get_slice(&self, hub_ts: DateTime<Utc>) -> Result<HubSlice, DataHubError>;
    async fn list_slices_range(
        &self,
        from_ts: DateTime<Utc>,
        to_ts: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<HubSlice>, DataHubError>;
    async fn get_market_at_time(
        &self,
        market_id: &str,
        hub_ts: DateTime<Utc>,
    ) -> Result<MarketSnapshot, DataHubError>;
}

#[async_trait]
pub trait MarketQuoteProvider: Send + Sync {
    async fn fetch_quote(&self, market_id: &str) -> Result<QuoteUpdate, DataHubError>;
}

#[async_trait]
pub trait QuoteStreamProvider: Send + Sync {
    async fn stream_quotes(&self, market_ids: Vec<String>) -> Result<QuoteStream, DataHubError>;
}

#[async_trait]
pub trait FxProvider: Send + Sync {
    async fn fetch_all(&self, base_ccy: &str) -> Result<Vec<FxQuote>, DataHubError>;
}

#[async_trait]
pub trait SessionProvider: Send + Sync {
    async fn resolve_session(
        &self,
        market_id: &str,
        ts: DateTime<Utc>,
    ) -> Result<MarketSession, DataHubError>;
}

#[async_trait]
pub trait NewsProvider: Send + Sync {
    async fn fetch_news(
        &self,
        market_id: &str,
        since: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<NewsEvent>, DataHubError>;
}

#[async_trait]
pub trait RealtimeSliceStore: Send + Sync {
    async fn put_slice(&self, slice: &HubSlice) -> Result<(), DataHubError>;
    async fn get_slice(&self, hub_ts: DateTime<Utc>) -> Result<Option<HubSlice>, DataHubError>;
    async fn list_slices_range(
        &self,
        from_ts: DateTime<Utc>,
        to_ts: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<HubSlice>, DataHubError>;
}

#[async_trait]
pub trait HistoricalSliceStore: Send + Sync {
    async fn persist_slice(&self, slice: &HubSlice) -> Result<(), DataHubError>;
    async fn get_slice(&self, hub_ts: DateTime<Utc>) -> Result<Option<HubSlice>, DataHubError>;
    async fn list_slices_range(
        &self,
        from_ts: DateTime<Utc>,
        to_ts: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<HubSlice>, DataHubError>;
}

pub trait SliceArchive: Send + Sync {
    fn archive_slice(&self, slice: &HubSlice) -> Result<(), DataHubError>;
}

pub struct InMemoryMarketDataHub {
    quote_provider: Arc<dyn MarketQuoteProvider>,
    fx_provider: Arc<dyn FxProvider>,
    session_provider: Arc<dyn SessionProvider>,
    news_provider: Arc<dyn NewsProvider>,
    policy: HubFreshnessPolicy,
    fx_base_ccy: String,
    news_lookback: Duration,
    news_limit: usize,
    latest_cache: RwLock<HashMap<String, MarketSnapshot>>,
    fx_cache: RwLock<HashMap<String, Vec<FxQuote>>>,
    session_cache: RwLock<HashMap<String, MarketSession>>,
    news_cache: RwLock<HashMap<String, Vec<NewsEvent>>>,
    snapshot_channels: RwLock<HashMap<String, broadcast::Sender<MarketSnapshot>>>,
    slices_cache: RwLock<BTreeMap<i64, HubSlice>>,
    slices_retention: usize,
    slice_sender: broadcast::Sender<HubSlice>,
    realtime_store: Option<Arc<dyn RealtimeSliceStore>>,
    historical_store: Option<Arc<dyn HistoricalSliceStore>>,
    slice_archive: Option<Arc<dyn SliceArchive>>,
    retry_policy: RetryPolicy,
}

impl InMemoryMarketDataHub {
    pub fn new(
        quote_provider: Arc<dyn MarketQuoteProvider>,
        fx_provider: Arc<dyn FxProvider>,
        session_provider: Arc<dyn SessionProvider>,
        news_provider: Arc<dyn NewsProvider>,
        policy: HubFreshnessPolicy,
        fx_base_ccy: impl Into<String>,
        news_lookback: Duration,
        news_limit: usize,
    ) -> Self {
        let (slice_sender, _) = broadcast::channel(512);
        Self {
            quote_provider,
            fx_provider,
            session_provider,
            news_provider,
            policy,
            fx_base_ccy: fx_base_ccy.into(),
            news_lookback,
            news_limit,
            latest_cache: RwLock::new(HashMap::new()),
            fx_cache: RwLock::new(HashMap::new()),
            session_cache: RwLock::new(HashMap::new()),
            news_cache: RwLock::new(HashMap::new()),
            snapshot_channels: RwLock::new(HashMap::new()),
            slices_cache: RwLock::new(BTreeMap::new()),
            slices_retention: 3_600,
            slice_sender,
            realtime_store: None,
            historical_store: None,
            slice_archive: None,
            retry_policy: RetryPolicy::default(),
        }
    }

    pub fn with_realtime_store(mut self, store: Arc<dyn RealtimeSliceStore>) -> Self {
        self.realtime_store = Some(store);
        self
    }

    pub fn with_historical_store(mut self, store: Arc<dyn HistoricalSliceStore>) -> Self {
        self.historical_store = Some(store);
        self
    }

    pub fn with_slice_archive(mut self, archive: Arc<dyn SliceArchive>) -> Self {
        self.slice_archive = Some(archive);
        self
    }

    pub fn with_slices_retention(mut self, retention: usize) -> Self {
        self.slices_retention = retention.max(1);
        self
    }

    pub fn with_retry_policy(mut self, retry_policy: RetryPolicy) -> Self {
        if !retry_policy.backoff_secs.is_empty() {
            self.retry_policy = retry_policy;
        }
        self
    }

    pub async fn bootstrap_markets(&self, markets: &[String]) -> BootstrapSummary {
        let mut summary = BootstrapSummary::default();
        for market_id in markets {
            match self.refresh_snapshot(market_id).await {
                Ok(_) => {
                    summary.ok_markets += 1;
                }
                Err(err) => {
                    summary.failed_markets += 1;
                    summary.last_error = Some(format!("{market_id}: {err}"));
                }
            }
        }
        summary
    }

    pub async fn ingest_quote(&self, quote: QuoteUpdate) -> Result<MarketSnapshot, DataHubError> {
        let market_id = quote.market_id.clone();
        let mut partial = false;

        let fx_context = match self.fx_provider.fetch_all(&self.fx_base_ccy).await {
            Ok(fx) => {
                self.fx_cache
                    .write()
                    .await
                    .insert(self.fx_base_ccy.clone(), fx.clone());
                fx
            }
            Err(_) => {
                partial = true;
                self.fx_cache
                    .read()
                    .await
                    .get(&self.fx_base_ccy)
                    .cloned()
                    .unwrap_or_default()
            }
        };

        let session_state = match self
            .session_provider
            .resolve_session(&market_id, quote.as_of)
            .await
        {
            Ok(session) => {
                self.session_cache
                    .write()
                    .await
                    .insert(market_id.clone(), session.clone());
                session
            }
            Err(_) => {
                partial = true;
                self.session_cache
                    .read()
                    .await
                    .get(&market_id)
                    .cloned()
                    .unwrap_or(MarketSession {
                        market_id: market_id.clone(),
                        state: MarketSessionState::Halted,
                        timezone: "UTC".to_string(),
                        opens_at: None,
                        closes_at: None,
                        note: Some("session unavailable".to_string()),
                    })
            }
        };

        let since = quote.as_of - self.news_lookback;
        let news = match self
            .news_provider
            .fetch_news(&market_id, since, self.news_limit)
            .await
        {
            Ok(events) => {
                self.news_cache
                    .write()
                    .await
                    .insert(market_id.clone(), events.clone());
                events
            }
            Err(_) => {
                partial = true;
                self.news_cache
                    .read()
                    .await
                    .get(&market_id)
                    .cloned()
                    .unwrap_or_default()
            }
        };

        let quality_flags = self.compute_quality(&quote.as_of, partial);
        let snapshot = MarketSnapshot {
            as_of: quote.as_of,
            market_id: market_id.clone(),
            book_ticker: quote.book_ticker,
            fx_context,
            session_state,
            news_refs: news.into_iter().map(|x| x.event_id).collect(),
            quality_flags,
            carried_forward: false,
        };

        self.latest_cache
            .write()
            .await
            .insert(market_id.clone(), snapshot.clone());

        let sender = self.get_or_create_snapshot_channel(&market_id).await;
        let _ = sender.send(snapshot.clone());
        Ok(snapshot)
    }

    fn compute_quality_from_lag(&self, lag_ms: i64, partial: bool) -> QualityFlags {
        QualityFlags {
            stale: lag_ms > self.policy.stale_after_ms,
            partial: partial || lag_ms > self.policy.soft_slo_ms,
            source_lag_ms: lag_ms,
        }
    }

    fn compute_quality(&self, as_of: &DateTime<Utc>, partial: bool) -> QualityFlags {
        let lag_ms = (Utc::now() - *as_of).num_milliseconds().max(0);
        self.compute_quality_from_lag(lag_ms, partial)
    }

    async fn get_or_create_snapshot_channel(
        &self,
        market_id: &str,
    ) -> broadcast::Sender<MarketSnapshot> {
        if let Some(ch) = self.snapshot_channels.read().await.get(market_id).cloned() {
            return ch;
        }
        let mut write = self.snapshot_channels.write().await;
        if let Some(ch) = write.get(market_id).cloned() {
            return ch;
        }
        let (tx, _) = broadcast::channel(512);
        write.insert(market_id.to_string(), tx.clone());
        tx
    }

    fn apply_carry_forward(
        &self,
        snapshot: &MarketSnapshot,
        hub_ts: DateTime<Utc>,
    ) -> MarketSnapshot {
        let mut output = snapshot.clone();
        let lag_ms = (hub_ts - snapshot.as_of).num_milliseconds().max(0);
        let provider_partial = snapshot.quality_flags.partial
            && snapshot.quality_flags.source_lag_ms <= self.policy.soft_slo_ms;
        output.quality_flags = self.compute_quality_from_lag(lag_ms, provider_partial);
        output.carried_forward = lag_ms > self.policy.stale_after_ms;
        output
    }

    async fn build_empty_snapshot(&self, market_id: &str, hub_ts: DateTime<Utc>) -> MarketSnapshot {
        MarketSnapshot {
            as_of: hub_ts,
            market_id: market_id.to_string(),
            book_ticker: BookTicker {
                bids: Vec::new(),
                asks: Vec::new(),
                best_bid: None,
                best_ask: None,
                midpoint: None,
                spread: None,
                last_trade: None,
            },
            fx_context: self
                .fx_cache
                .read()
                .await
                .get(&self.fx_base_ccy)
                .cloned()
                .unwrap_or_default(),
            session_state: self
                .session_cache
                .read()
                .await
                .get(market_id)
                .cloned()
                .unwrap_or(MarketSession {
                    market_id: market_id.to_string(),
                    state: MarketSessionState::Halted,
                    timezone: "UTC".to_string(),
                    opens_at: None,
                    closes_at: None,
                    note: Some("no market data yet".to_string()),
                }),
            news_refs: Vec::new(),
            quality_flags: QualityFlags {
                stale: true,
                partial: true,
                source_lag_ms: 0,
            },
            carried_forward: true,
        }
    }

    pub async fn assemble_and_publish_slice(
        &self,
        hub_ts: DateTime<Utc>,
        markets: &[String],
    ) -> Result<HubSlice, DataHubError> {
        let latest = self.latest_cache.read().await;
        let mut market_map = BTreeMap::new();
        let mut stale_count = 0usize;
        let mut partial_count = 0usize;

        for market_id in markets {
            let snap = match latest.get(market_id) {
                Some(snapshot) => self.apply_carry_forward(snapshot, hub_ts),
                None => self.build_empty_snapshot(market_id, hub_ts).await,
            };
            if snap.quality_flags.stale {
                stale_count += 1;
            }
            if snap.quality_flags.partial {
                partial_count += 1;
            }
            market_map.insert(market_id.clone(), snap);
        }
        drop(latest);

        let slice = HubSlice {
            hub_ts,
            ingestion_ts: Utc::now(),
            markets: market_map,
            slice_meta: HubSliceMeta {
                market_count: markets.len(),
                stale_count,
                partial_count,
            },
        };

        {
            let mut write = self.slices_cache.write().await;
            write.insert(slice.hub_ts.timestamp_millis(), slice.clone());
            while write.len() > self.slices_retention {
                let first = write.keys().next().copied();
                if let Some(key) = first {
                    write.remove(&key);
                } else {
                    break;
                }
            }
        }

        for (market_id, snapshot) in &slice.markets {
            let sender = self.get_or_create_snapshot_channel(market_id).await;
            let _ = sender.send(snapshot.clone());
        }
        let _ = self.slice_sender.send(slice.clone());

        if let Some(archive) = &self.slice_archive {
            archive.archive_slice(&slice)?;
        }

        if let Some(realtime) = &self.realtime_store {
            realtime.put_slice(&slice).await?;
        }

        if let Some(historical) = &self.historical_store {
            let historical = Arc::clone(historical);
            let slice_clone = slice.clone();
            let backoffs = self.retry_policy.backoff_secs.clone();
            tokio::spawn(async move {
                let mut attempt = 0usize;
                loop {
                    if historical.persist_slice(&slice_clone).await.is_ok() {
                        break;
                    }
                    let wait_secs = backoffs
                        .get(attempt)
                        .copied()
                        .or_else(|| backoffs.last().copied())
                        .unwrap_or(5);
                    attempt = attempt.saturating_add(1);
                    tokio::time::sleep(std::time::Duration::from_secs(wait_secs)).await;
                }
            });
        }

        Ok(slice)
    }

    pub async fn refresh_snapshot(&self, market_id: &str) -> Result<MarketSnapshot, DataHubError> {
        let quote = self.quote_provider.fetch_quote(market_id).await?;
        self.ingest_quote(quote).await
    }

    pub async fn subscribe_slices(&self) -> Result<SliceStream, DataHubError> {
        let receiver = self.slice_sender.subscribe();
        let stream = BroadcastStream::new(receiver).filter_map(Result::ok);
        Ok(Box::pin(stream))
    }
}

#[async_trait]
impl MarketDataHub for InMemoryMarketDataHub {
    async fn get_snapshot(&self, market_id: &str) -> Result<MarketSnapshot, DataHubError> {
        let cached = self.latest_cache.read().await.get(market_id).cloned();
        match cached {
            Some(snapshot) if !snapshot.quality_flags.stale => Ok(snapshot),
            _ => self.refresh_snapshot(market_id).await,
        }
    }

    async fn get_fx(&self, base_ccy: &str) -> Result<Vec<FxQuote>, DataHubError> {
        match self.fx_provider.fetch_all(base_ccy).await {
            Ok(fx) => {
                self.fx_cache
                    .write()
                    .await
                    .insert(base_ccy.to_string(), fx.clone());
                Ok(fx)
            }
            Err(err) => self.fx_cache.read().await.get(base_ccy).cloned().ok_or(err),
        }
    }

    async fn get_session(
        &self,
        market_id: &str,
        ts: DateTime<Utc>,
    ) -> Result<MarketSession, DataHubError> {
        if let Some(cached) = self.session_cache.read().await.get(market_id).cloned() {
            return Ok(cached);
        }
        let session = self.session_provider.resolve_session(market_id, ts).await?;
        self.session_cache
            .write()
            .await
            .insert(market_id.to_string(), session.clone());
        Ok(session)
    }

    async fn get_news(
        &self,
        market_id: &str,
        since: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<NewsEvent>, DataHubError> {
        match self.news_provider.fetch_news(market_id, since, limit).await {
            Ok(news) => {
                self.news_cache
                    .write()
                    .await
                    .insert(market_id.to_string(), news.clone());
                Ok(news)
            }
            Err(err) => self
                .news_cache
                .read()
                .await
                .get(market_id)
                .cloned()
                .ok_or(err),
        }
    }

    async fn subscribe_snapshots(&self, market_id: &str) -> Result<SnapshotStream, DataHubError> {
        let sender = self.get_or_create_snapshot_channel(market_id).await;
        let receiver = sender.subscribe();
        let stream = BroadcastStream::new(receiver).filter_map(Result::ok);
        Ok(Box::pin(stream))
    }

    async fn get_slice(&self, hub_ts: DateTime<Utc>) -> Result<HubSlice, DataHubError> {
        if let Some(slice) = self
            .slices_cache
            .read()
            .await
            .get(&hub_ts.timestamp_millis())
            .cloned()
        {
            return Ok(slice);
        }
        if let Some(store) = &self.realtime_store {
            if let Some(slice) = store.get_slice(hub_ts).await? {
                return Ok(slice);
            }
        }
        if let Some(store) = &self.historical_store {
            if let Some(slice) = store.get_slice(hub_ts).await? {
                return Ok(slice);
            }
        }
        Err(DataHubError::NotFound(format!(
            "slice not found at hub_ts={}",
            hub_ts.to_rfc3339()
        )))
    }

    async fn list_slices_range(
        &self,
        from_ts: DateTime<Utc>,
        to_ts: DateTime<Utc>,
        limit: usize,
    ) -> Result<Vec<HubSlice>, DataHubError> {
        if let Some(store) = &self.realtime_store {
            let slices = store.list_slices_range(from_ts, to_ts, limit).await?;
            if !slices.is_empty() {
                return Ok(slices);
            }
        }
        if let Some(store) = &self.historical_store {
            return store.list_slices_range(from_ts, to_ts, limit).await;
        }
        let read = self.slices_cache.read().await;
        let mut out = Vec::new();
        for (_, slice) in read.range(from_ts.timestamp_millis()..=to_ts.timestamp_millis()) {
            out.push(slice.clone());
            if out.len() >= limit {
                break;
            }
        }
        Ok(out)
    }

    async fn get_market_at_time(
        &self,
        market_id: &str,
        hub_ts: DateTime<Utc>,
    ) -> Result<MarketSnapshot, DataHubError> {
        let slice = self.get_slice(hub_ts).await?;
        slice.markets.get(market_id).cloned().ok_or_else(|| {
            DataHubError::NotFound(format!("market not found in slice: {market_id}"))
        })
    }
}
