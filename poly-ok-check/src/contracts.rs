use std::collections::BTreeMap;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OrderLevel {
    pub price: f64,
    pub size: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct BookTicker {
    pub bids: Vec<OrderLevel>,
    pub asks: Vec<OrderLevel>,
    pub best_bid: Option<f64>,
    pub best_ask: Option<f64>,
    pub midpoint: Option<f64>,
    pub spread: Option<f64>,
    pub last_trade: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct FxQuote {
    pub pair: String,
    pub rate: f64,
    pub as_of: DateTime<Utc>,
    pub provider: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum MarketSessionState {
    Open,
    Closed,
    PreOpen,
    Halted,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MarketSession {
    pub market_id: String,
    pub state: MarketSessionState,
    pub timezone: String,
    pub opens_at: Option<DateTime<Utc>>,
    pub closes_at: Option<DateTime<Utc>>,
    pub note: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct NewsEvent {
    pub event_id: String,
    pub market_id: String,
    pub headline: String,
    pub source: String,
    pub url: Option<String>,
    pub published_at: DateTime<Utc>,
    pub tags: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct QualityFlags {
    pub stale: bool,
    pub partial: bool,
    pub source_lag_ms: i64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MarketSnapshot {
    pub as_of: DateTime<Utc>,
    pub market_id: String,
    pub book_ticker: BookTicker,
    pub fx_context: Vec<FxQuote>,
    pub session_state: MarketSession,
    pub news_refs: Vec<String>,
    pub quality_flags: QualityFlags,
    pub carried_forward: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HubSliceMeta {
    pub market_count: usize,
    pub stale_count: usize,
    pub partial_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct HubSlice {
    pub hub_ts: DateTime<Utc>,
    pub ingestion_ts: DateTime<Utc>,
    pub markets: BTreeMap<String, MarketSnapshot>,
    pub slice_meta: HubSliceMeta,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub enum OpportunityDirection {
    LongYes,
    LongNo,
    Flat,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OpportunityCandidate {
    pub agent_id: String,
    pub market_id: String,
    pub direction: OpportunityDirection,
    pub confidence: f64,
    pub expected_edge: f64,
    pub time_horizon_secs: u64,
    pub risk_hints: BTreeMap<String, f64>,
    pub trace_id: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PortfolioPosition {
    pub market_id: String,
    pub side: OpportunityDirection,
    pub notional_usd: f64,
    pub entry_price: f64,
    pub opened_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PortfolioView {
    pub cash_usd: f64,
    pub active_positions: Vec<PortfolioPosition>,
    pub max_active_opportunities: u32,
}

impl Default for PortfolioView {
    fn default() -> Self {
        Self {
            cash_usd: 0.0,
            active_positions: Vec::new(),
            max_active_opportunities: 1,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PositionCheck {
    pub market_id: String,
    pub status: String,
    pub detail: String,
    pub as_of: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct AgentHealth {
    pub status: String,
    pub lag_ms: i64,
    pub last_error: Option<String>,
    pub observed_at: DateTime<Utc>,
}
