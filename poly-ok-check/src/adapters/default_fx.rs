use std::collections::HashMap;

use async_trait::async_trait;
use chrono::Utc;
use reqwest::Client;
use serde::Deserialize;

use crate::contracts::FxQuote;
use crate::data_hub::{DataHubError, FxProvider};

#[derive(Debug, Deserialize)]
struct FxResponse {
    rates: HashMap<String, f64>,
}

pub struct ExchangeRateHostFxProvider {
    client: Client,
    endpoint: String,
    quote_ccys: Vec<String>,
}

impl ExchangeRateHostFxProvider {
    pub fn new(quote_ccys: Vec<String>) -> Self {
        Self {
            client: Client::new(),
            endpoint: "https://api.exchangerate.host/latest".to_string(),
            quote_ccys,
        }
    }

    pub fn with_endpoint(mut self, endpoint: impl Into<String>) -> Self {
        self.endpoint = endpoint.into();
        self
    }
}

#[async_trait]
impl FxProvider for ExchangeRateHostFxProvider {
    async fn fetch_all(&self, base_ccy: &str) -> Result<Vec<FxQuote>, DataHubError> {
        let response = self
            .client
            .get(&self.endpoint)
            .query(&[("base", base_ccy)])
            .send()
            .await
            .map_err(|e| DataHubError::Provider(format!("fx request failed: {e}")))?;

        let payload: FxResponse = response
            .json()
            .await
            .map_err(|e| DataHubError::Provider(format!("fx decode failed: {e}")))?;

        let now = Utc::now();
        let mut out = Vec::new();
        for quote_ccy in &self.quote_ccys {
            if let Some(rate) = payload.rates.get(quote_ccy) {
                out.push(FxQuote {
                    pair: format!("{base_ccy}/{quote_ccy}"),
                    rate: *rate,
                    as_of: now,
                    provider: "exchangerate.host".to_string(),
                });
            }
        }

        if out.is_empty() {
            return Err(DataHubError::Provider(
                "fx provider returned no requested quote currencies".to_string(),
            ));
        }

        Ok(out)
    }
}
