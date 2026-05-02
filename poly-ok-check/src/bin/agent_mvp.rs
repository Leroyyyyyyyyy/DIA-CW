use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use anyhow::Context;
use chrono::{Duration as ChronoDuration, Utc};
use poly_ok_check::adapters::default_fx::ExchangeRateHostFxProvider;
use poly_ok_check::adapters::default_rss::RssNewsProvider;
use poly_ok_check::adapters::polymarket::PolymarketQuoteAdapter;
use poly_ok_check::adapters::session::AlwaysOpenSessionProvider;
use poly_ok_check::agent::{AgentConfig, MarketTradingAgent};
use poly_ok_check::archive::JsonlSliceArchiveWriter;
use poly_ok_check::config::HubConfig;
use poly_ok_check::contracts::PortfolioView;
use poly_ok_check::data_hub::{HubFreshnessPolicy, InMemoryMarketDataHub, RetryPolicy};
use poly_ok_check::polymarket_agent::PolymarketAgent;
use poly_ok_check::storage::{PostgresHistoricalSliceStore, RedisRealtimeSliceStore};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let config_path = std::env::var("HUB_CONFIG").unwrap_or_else(|_| "hub.toml".to_string());
    let config = HubConfig::from_file(&config_path).with_context(|| {
        format!(
            "failed to load hub config from {}",
            PathBuf::from(&config_path).display()
        )
    })?;
    config.validate()?;

    let quote_provider = Arc::new(PolymarketQuoteAdapter::new(Duration::from_millis(
        config.quote.rest_fallback_interval_ms,
    ))?);
    let fx_provider = Arc::new(
        ExchangeRateHostFxProvider::new(config.fx.quote_ccys.clone())
            .with_endpoint(config.fx.endpoint.clone()),
    );
    let news_provider = Arc::new(RssNewsProvider::new(
        config.news.feed_map(),
        config.news.market_rules.clone(),
    ));
    let session_provider = Arc::new(AlwaysOpenSessionProvider::new(
        config.session.timezone.clone(),
        config.session.note.clone(),
    ));

    let archive = Arc::new(JsonlSliceArchiveWriter::new(
        PathBuf::from(&config.archive.dir),
        config.archive.prefix.clone(),
        config.archive.retention_days,
    )?);

    let mut hub = InMemoryMarketDataHub::new(
        quote_provider,
        fx_provider,
        session_provider,
        news_provider,
        HubFreshnessPolicy {
            soft_slo_ms: config.freshness.soft_slo_ms,
            stale_after_ms: config.freshness.stale_after_ms,
        },
        config.fx.base_ccy.clone(),
        ChronoDuration::hours(config.news.lookback_hours),
        config.news.fetch_limit,
    )
    .with_slices_retention(config.slice.in_memory_retention)
    .with_slice_archive(archive)
    .with_retry_policy(RetryPolicy {
        backoff_secs: config.storage.postgres.retry_backoff_secs.clone(),
    });

    if config.storage.redis.enabled {
        let store = Arc::new(RedisRealtimeSliceStore::new(
            &config.storage.redis.url,
            config.storage.redis.key_prefix.clone(),
            config.storage.redis.ttl_hours.saturating_mul(3600),
        )?);
        hub = hub.with_realtime_store(store);
    }

    if config.storage.postgres.enabled {
        let store =
            Arc::new(PostgresHistoricalSliceStore::connect(&config.storage.postgres.url).await?);
        hub = hub.with_historical_store(store);
    }

    let hub = Arc::new(hub);
    let bootstrap = hub.bootstrap_markets(&config.markets).await;
    println!(
        "agent_mvp bootstrap_markets ok={} failed={}",
        bootstrap.ok_markets, bootstrap.failed_markets
    );

    let hub_ts = Utc::now();
    let slice = hub
        .assemble_and_publish_slice(hub_ts, &config.markets)
        .await
        .context("failed to assemble slice for agent input")?;
    println!(
        "agent_mvp slice hub_ts={} markets={} stale={} partial={}",
        slice.hub_ts.to_rfc3339(),
        slice.slice_meta.market_count,
        slice.slice_meta.stale_count,
        slice.slice_meta.partial_count
    );

    let agent = PolymarketAgent::new(
        "poly-mvp-agent",
        AgentConfig {
            watchlist: config.markets.clone(),
            min_edge: std::env::var("AGENT_MIN_EDGE")
                .ok()
                .and_then(|x| x.parse::<f64>().ok())
                .unwrap_or(0.01),
            max_candidates: std::env::var("AGENT_MAX_CANDIDATES")
                .ok()
                .and_then(|x| x.parse::<usize>().ok())
                .unwrap_or(5),
        },
    );

    let opportunities = agent
        .propose_opportunities(hub.as_ref(), &PortfolioView::default(), Utc::now())
        .await
        .context("agent propose_opportunities failed")?;
    let health = agent.health().await;

    println!("{}", serde_json::to_string_pretty(&opportunities)?);
    println!("{}", serde_json::to_string_pretty(&health)?);

    Ok(())
}
