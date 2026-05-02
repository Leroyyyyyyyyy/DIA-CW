use async_trait::async_trait;
use chrono::{DateTime, Utc};

use crate::contracts::{MarketSession, MarketSessionState};
use crate::data_hub::{DataHubError, SessionProvider};

pub struct AlwaysOpenSessionProvider {
    timezone: String,
    note: String,
}

impl AlwaysOpenSessionProvider {
    pub fn new(timezone: impl Into<String>, note: impl Into<String>) -> Self {
        Self {
            timezone: timezone.into(),
            note: note.into(),
        }
    }
}

#[async_trait]
impl SessionProvider for AlwaysOpenSessionProvider {
    async fn resolve_session(
        &self,
        market_id: &str,
        _ts: DateTime<Utc>,
    ) -> Result<MarketSession, DataHubError> {
        Ok(MarketSession {
            market_id: market_id.to_string(),
            state: MarketSessionState::Open,
            timezone: self.timezone.clone(),
            opens_at: None,
            closes_at: None,
            note: Some(self.note.clone()),
        })
    }
}
