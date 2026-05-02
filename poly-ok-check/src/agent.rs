use async_trait::async_trait;
use chrono::{DateTime, Utc};

use crate::contracts::{AgentHealth, OpportunityCandidate, PortfolioView, PositionCheck};
use crate::data_hub::MarketDataHub;

#[derive(Debug, Clone)]
pub struct AgentConfig {
    pub watchlist: Vec<String>,
    pub min_edge: f64,
    pub max_candidates: usize,
}

impl Default for AgentConfig {
    fn default() -> Self {
        Self {
            watchlist: Vec::new(),
            min_edge: 0.0,
            max_candidates: 1,
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum AgentError {
    #[error("agent data error: {0}")]
    Data(String),
    #[error("agent runtime error: {0}")]
    Runtime(String),
}

#[async_trait]
pub trait MarketTradingAgent: Send + Sync {
    fn id(&self) -> &str;
    fn config(&self) -> &AgentConfig;
    async fn propose_opportunities(
        &self,
        hub: &dyn MarketDataHub,
        portfolio: &PortfolioView,
        now: DateTime<Utc>,
    ) -> Result<Vec<OpportunityCandidate>, AgentError>;
    async fn monitor_positions(
        &self,
        hub: &dyn MarketDataHub,
        portfolio: &PortfolioView,
        now: DateTime<Utc>,
    ) -> Result<Vec<PositionCheck>, AgentError>;
    async fn health(&self) -> AgentHealth;
}
