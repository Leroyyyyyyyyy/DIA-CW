use std::collections::HashMap;
use std::fs;
use std::path::Path;

use serde::Deserialize;

use crate::data_hub::DataHubError;

#[derive(Debug, Clone, Deserialize)]
pub struct HubConfig {
    #[serde(default)]
    pub markets: Vec<String>,
    #[serde(default)]
    pub freshness: FreshnessConfig,
    #[serde(default)]
    pub fx: FxConfig,
    #[serde(default)]
    pub news: NewsConfig,
    #[serde(default)]
    pub archive: ArchiveConfig,
    #[serde(default)]
    pub quote: QuoteConfig,
    #[serde(default)]
    pub session: SessionConfig,
    #[serde(default)]
    pub slice: SliceConfig,
    #[serde(default)]
    pub storage: StorageConfig,
}

impl HubConfig {
    pub fn from_file(path: impl AsRef<Path>) -> Result<Self, DataHubError> {
        let raw = fs::read_to_string(path).map_err(|e| DataHubError::Config(e.to_string()))?;
        toml::from_str(&raw).map_err(|e| DataHubError::Config(e.to_string()))
    }

    pub fn validate(&self) -> Result<(), DataHubError> {
        if self.markets.is_empty() {
            return Err(DataHubError::Config(
                "markets must not be empty in hub config".to_string(),
            ));
        }
        if self.fx.quote_ccys.is_empty() {
            return Err(DataHubError::Config(
                "fx.quote_ccys must not be empty in hub config".to_string(),
            ));
        }
        if self.storage.redis.enabled && self.storage.redis.url.trim().is_empty() {
            return Err(DataHubError::Config(
                "storage.redis.url must be set when redis is enabled".to_string(),
            ));
        }
        if self.storage.postgres.enabled && self.storage.postgres.url.trim().is_empty() {
            return Err(DataHubError::Config(
                "storage.postgres.url must be set when postgres is enabled".to_string(),
            ));
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct FreshnessConfig {
    #[serde(default = "default_soft_slo")]
    pub soft_slo_ms: i64,
    #[serde(default = "default_stale_after")]
    pub stale_after_ms: i64,
}

fn default_soft_slo() -> i64 {
    500
}

fn default_stale_after() -> i64 {
    2_000
}

impl Default for FreshnessConfig {
    fn default() -> Self {
        Self {
            soft_slo_ms: default_soft_slo(),
            stale_after_ms: default_stale_after(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct FxConfig {
    #[serde(default = "default_fx_base")]
    pub base_ccy: String,
    #[serde(default = "default_fx_quotes")]
    pub quote_ccys: Vec<String>,
    #[serde(default = "default_fx_endpoint")]
    pub endpoint: String,
}

fn default_fx_base() -> String {
    "USD".to_string()
}

fn default_fx_quotes() -> Vec<String> {
    vec!["CNY".to_string(), "EUR".to_string(), "JPY".to_string()]
}

fn default_fx_endpoint() -> String {
    "https://api.exchangerate.host/latest".to_string()
}

impl Default for FxConfig {
    fn default() -> Self {
        Self {
            base_ccy: default_fx_base(),
            quote_ccys: default_fx_quotes(),
            endpoint: default_fx_endpoint(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct NewsConfig {
    #[serde(default)]
    pub feeds: Vec<NewsFeedConfig>,
    #[serde(default)]
    pub market_rules: Vec<MarketNewsRule>,
    #[serde(default = "default_news_lookback")]
    pub lookback_hours: i64,
    #[serde(default = "default_news_limit")]
    pub fetch_limit: usize,
}

fn default_news_lookback() -> i64 {
    8
}

fn default_news_limit() -> usize {
    32
}

impl Default for NewsConfig {
    fn default() -> Self {
        Self {
            feeds: Vec::new(),
            market_rules: Vec::new(),
            lookback_hours: default_news_lookback(),
            fetch_limit: default_news_limit(),
        }
    }
}

impl NewsConfig {
    pub fn feed_map(&self) -> HashMap<String, String> {
        let mut out = HashMap::new();
        for feed in &self.feeds {
            out.insert(feed.source.clone(), feed.url.clone());
        }
        out
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct NewsFeedConfig {
    pub source: String,
    pub url: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct MarketNewsRule {
    pub market_id: String,
    #[serde(default)]
    pub feed_sources: Vec<String>,
    #[serde(default)]
    pub keywords: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ArchiveConfig {
    #[serde(default = "default_archive_dir")]
    pub dir: String,
    #[serde(default = "default_archive_prefix")]
    pub prefix: String,
    #[serde(default = "default_archive_retention")]
    pub retention_days: i64,
}

fn default_archive_dir() -> String {
    "data/hub_archive".to_string()
}

fn default_archive_prefix() -> String {
    "slices".to_string()
}

fn default_archive_retention() -> i64 {
    30
}

impl Default for ArchiveConfig {
    fn default() -> Self {
        Self {
            dir: default_archive_dir(),
            prefix: default_archive_prefix(),
            retention_days: default_archive_retention(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct QuoteConfig {
    #[serde(default = "default_rest_interval")]
    pub rest_fallback_interval_ms: u64,
}

fn default_rest_interval() -> u64 {
    1_000
}

impl Default for QuoteConfig {
    fn default() -> Self {
        Self {
            rest_fallback_interval_ms: default_rest_interval(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct SessionConfig {
    #[serde(default = "default_session_tz")]
    pub timezone: String,
    #[serde(default = "default_session_note")]
    pub note: String,
}

fn default_session_tz() -> String {
    "UTC".to_string()
}

fn default_session_note() -> String {
    "Polymarket 24x7".to_string()
}

impl Default for SessionConfig {
    fn default() -> Self {
        Self {
            timezone: default_session_tz(),
            note: default_session_note(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct SliceConfig {
    #[serde(default = "default_slice_interval_ms")]
    pub interval_ms: u64,
    #[serde(default = "default_slice_retention")]
    pub in_memory_retention: usize,
}

fn default_slice_interval_ms() -> u64 {
    1_000
}

fn default_slice_retention() -> usize {
    3_600
}

impl Default for SliceConfig {
    fn default() -> Self {
        Self {
            interval_ms: default_slice_interval_ms(),
            in_memory_retention: default_slice_retention(),
        }
    }
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct StorageConfig {
    #[serde(default)]
    pub redis: RedisStorageConfig,
    #[serde(default)]
    pub postgres: PostgresStorageConfig,
}

#[derive(Debug, Clone, Deserialize)]
pub struct RedisStorageConfig {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "default_redis_url")]
    pub url: String,
    #[serde(default = "default_redis_key_prefix")]
    pub key_prefix: String,
    #[serde(default = "default_redis_ttl_hours")]
    pub ttl_hours: u64,
}

fn default_redis_url() -> String {
    "redis://127.0.0.1:6379/".to_string()
}

fn default_redis_key_prefix() -> String {
    "dh".to_string()
}

fn default_redis_ttl_hours() -> u64 {
    24
}

impl Default for RedisStorageConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            url: default_redis_url(),
            key_prefix: default_redis_key_prefix(),
            ttl_hours: default_redis_ttl_hours(),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct PostgresStorageConfig {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "default_pg_url")]
    pub url: String,
    #[serde(default = "default_pg_retry_backoff")]
    pub retry_backoff_secs: Vec<u64>,
}

fn default_pg_url() -> String {
    "postgres://postgres:postgres@127.0.0.1:5432/polyquant".to_string()
}

fn default_pg_retry_backoff() -> Vec<u64> {
    vec![1, 2, 5, 10, 30]
}

impl Default for PostgresStorageConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            url: default_pg_url(),
            retry_backoff_secs: default_pg_retry_backoff(),
        }
    }
}
