use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

use anyhow::Context;
use chrono::{Duration as ChronoDuration, Utc};
use futures::StreamExt;
use poly_ok_check::adapters::default_fx::ExchangeRateHostFxProvider;
use poly_ok_check::adapters::default_rss::RssNewsProvider;
use poly_ok_check::adapters::polymarket::PolymarketQuoteAdapter;
use poly_ok_check::adapters::session::AlwaysOpenSessionProvider;
use poly_ok_check::archive::JsonlSliceArchiveWriter;
use poly_ok_check::config::HubConfig;
use poly_ok_check::data_hub::{
    HubFreshnessPolicy, InMemoryMarketDataHub, MarketQuoteProvider, QuoteStreamProvider,
    RetryPolicy,
};
use poly_ok_check::storage::{PostgresHistoricalSliceStore, RedisRealtimeSliceStore};

fn should_run_rest_refresh(
    last_quote_update_at: tokio::time::Instant,
    now: tokio::time::Instant,
    interval: Duration,
) -> bool {
    now.duration_since(last_quote_update_at) >= interval
}

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

    let quote_adapter = Arc::new(PolymarketQuoteAdapter::new(Duration::from_millis(
        config.quote.rest_fallback_interval_ms,
    ))?);
    let quote_provider: Arc<dyn MarketQuoteProvider> = quote_adapter.clone();
    let stream_provider: Arc<dyn QuoteStreamProvider> = quote_adapter;

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

    println!("hub_daemon starting");
    println!("config: {config_path}");
    println!("markets: {}", config.markets.join(","));
    println!("slice_interval_ms: {}", config.slice.interval_ms);
    println!("redis_enabled: {}", config.storage.redis.enabled);
    println!("postgres_enabled: {}", config.storage.postgres.enabled);

    let bootstrap = hub.bootstrap_markets(&config.markets).await;
    println!(
        "bootstrap_markets ok={} failed={}",
        bootstrap.ok_markets, bootstrap.failed_markets
    );
    if let Some(err) = bootstrap.last_error {
        eprintln!("bootstrap warning: {err}");
    }

    let mut quote_stream = stream_provider
        .stream_quotes(config.markets.clone())
        .await
        .context("failed to start quote stream")?;
    let mut ticker = tokio::time::interval(Duration::from_millis(config.slice.interval_ms));
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    let rest_refresh_interval = Duration::from_millis(config.quote.rest_fallback_interval_ms);
    let mut rest_refresh_ticker = tokio::time::interval(rest_refresh_interval);
    rest_refresh_ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

    let mut quote_updates: u64 = 0;
    let mut slices: u64 = 0;
    let mut rest_refreshes: u64 = 0;
    let mut last_quote_update_at = tokio::time::Instant::now();

    loop {
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {
                println!("hub_daemon received Ctrl+C, stopping.");
                break;
            }
            next = quote_stream.next() => {
                match next {
                    Some(Ok(quote)) => {
                        match hub.ingest_quote(quote).await {
                            Ok(snapshot) => {
                                quote_updates += 1;
                                last_quote_update_at = tokio::time::Instant::now();
                                if quote_updates % 200 == 0 {
                                    println!(
                                        "quote_updates={} market={} partial={} stale={} lag_ms={}",
                                        quote_updates,
                                        snapshot.market_id,
                                        snapshot.quality_flags.partial,
                                        snapshot.quality_flags.stale,
                                        snapshot.quality_flags.source_lag_ms
                                    );
                                }
                            }
                            Err(err) => eprintln!("hub ingest error: {err}"),
                        }
                    }
                    Some(Err(err)) => eprintln!("quote stream warning: {err}"),
                    None => {
                        eprintln!("quote stream ended unexpectedly");
                        break;
                    }
                }
            }
            _ = ticker.tick() => {
                let hub_ts = Utc::now();
                match hub.assemble_and_publish_slice(hub_ts, &config.markets).await {
                    Ok(slice) => {
                        slices += 1;
                        if slices % 60 == 0 {
                            println!(
                                "slices={} hub_ts={} markets={} stale={} partial={}",
                                slices,
                                slice.hub_ts.to_rfc3339(),
                                slice.slice_meta.market_count,
                                slice.slice_meta.stale_count,
                                slice.slice_meta.partial_count
                            );
                        }
                    }
                    Err(err) => eprintln!("slice assembly error: {err}"),
                }
            }
            _ = rest_refresh_ticker.tick() => {
                let now = tokio::time::Instant::now();
                if !should_run_rest_refresh(last_quote_update_at, now, rest_refresh_interval) {
                    continue;
                }

                let mut refreshed_any = false;
                for market_id in &config.markets {
                    match hub.refresh_snapshot(market_id).await {
                        Ok(snapshot) => {
                            refreshed_any = true;
                            rest_refreshes += 1;
                            if rest_refreshes % 60 == 0 {
                                println!(
                                    "rest_refreshes={} market={} partial={} stale={} lag_ms={}",
                                    rest_refreshes,
                                    snapshot.market_id,
                                    snapshot.quality_flags.partial,
                                    snapshot.quality_flags.stale,
                                    snapshot.quality_flags.source_lag_ms
                                );
                            }
                        }
                        Err(err) => {
                            eprintln!("rest refresh warning: market={} err={err}", market_id);
                        }
                    }
                }

                if refreshed_any {
                    last_quote_update_at = now;
                }
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::should_run_rest_refresh;
    use std::time::Duration;

    #[test]
    fn rest_refresh_triggers_after_interval() {
        let start = tokio::time::Instant::now();
        let now = start + Duration::from_millis(1_000);
        assert!(should_run_rest_refresh(
            start,
            now,
            Duration::from_millis(1_000)
        ));
        assert!(should_run_rest_refresh(
            start,
            now,
            Duration::from_millis(500)
        ));
        assert!(!should_run_rest_refresh(
            start,
            start + Duration::from_millis(999),
            Duration::from_millis(1_000)
        ));
    }
}
