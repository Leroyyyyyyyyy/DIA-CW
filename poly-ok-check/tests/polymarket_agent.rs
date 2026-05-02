use std::pin::Pin;
use std::sync::Arc;

use async_trait::async_trait;
use chrono::{Duration, Utc};
use futures::Stream;
use poly_ok_check::agent::{AgentConfig, MarketTradingAgent};
use poly_ok_check::contracts::{
    BookTicker, FxQuote, HubSlice, HubSliceMeta, MarketSession, MarketSessionState, MarketSnapshot,
    NewsEvent, OpportunityDirection, OrderLevel, PortfolioPosition, PortfolioView, QualityFlags,
};
use poly_ok_check::data_hub::{DataHubError, MarketDataHub, SnapshotStream};
use poly_ok_check::polymarket_agent::PolymarketAgent;

struct StubHub {
    snapshot: MarketSnapshot,
    slices: Vec<HubSlice>,
    news: Vec<NewsEvent>,
}

impl StubHub {
    fn new(market_id: &str, midpoint: f64, lag_ms: i64, stale: bool) -> Self {
        let now = Utc::now();
        let snapshot = MarketSnapshot {
            as_of: now - Duration::milliseconds(lag_ms.max(0)),
            market_id: market_id.to_string(),
            book_ticker: BookTicker {
                bids: vec![OrderLevel {
                    price: (midpoint - 0.01).max(0.0),
                    size: 300.0,
                }],
                asks: vec![OrderLevel {
                    price: (midpoint + 0.01).min(1.0),
                    size: 150.0,
                }],
                best_bid: Some((midpoint - 0.01).max(0.0)),
                best_ask: Some((midpoint + 0.01).min(1.0)),
                midpoint: Some(midpoint),
                spread: Some(0.02),
                last_trade: Some(midpoint),
            },
            fx_context: vec![FxQuote {
                pair: "USD/CNY".to_string(),
                rate: 7.2,
                as_of: now,
                provider: "stub".to_string(),
            }],
            session_state: MarketSession {
                market_id: market_id.to_string(),
                state: MarketSessionState::Open,
                timezone: "UTC".to_string(),
                opens_at: None,
                closes_at: None,
                note: Some("Polymarket 24x7".to_string()),
            },
            news_refs: vec!["n1".to_string()],
            quality_flags: QualityFlags {
                stale,
                partial: false,
                source_lag_ms: lag_ms,
            },
            carried_forward: false,
        };
        let slices = vec![
            make_slice(market_id, now - Duration::minutes(10), 0.40, false),
            make_slice(market_id, now - Duration::minutes(5), 0.46, false),
            make_slice(market_id, now - Duration::minutes(1), midpoint, false),
        ];
        let news = vec![NewsEvent {
            event_id: "n1".to_string(),
            market_id: market_id.to_string(),
            headline: "Breaking macro crypto update".to_string(),
            source: "stub".to_string(),
            url: None,
            published_at: now - Duration::minutes(30),
            tags: vec!["rss".to_string()],
        }];
        Self {
            snapshot,
            slices,
            news,
        }
    }
}

#[async_trait]
impl MarketDataHub for StubHub {
    async fn get_snapshot(&self, market_id: &str) -> Result<MarketSnapshot, DataHubError> {
        if market_id != self.snapshot.market_id {
            return Err(DataHubError::NotFound(format!(
                "missing market {market_id}"
            )));
        }
        Ok(self.snapshot.clone())
    }

    async fn get_fx(&self, _base_ccy: &str) -> Result<Vec<FxQuote>, DataHubError> {
        Ok(self.snapshot.fx_context.clone())
    }

    async fn get_session(
        &self,
        _market_id: &str,
        _ts: chrono::DateTime<Utc>,
    ) -> Result<MarketSession, DataHubError> {
        Ok(self.snapshot.session_state.clone())
    }

    async fn get_news(
        &self,
        _market_id: &str,
        _since: chrono::DateTime<Utc>,
        _limit: usize,
    ) -> Result<Vec<NewsEvent>, DataHubError> {
        Ok(self.news.clone())
    }

    async fn subscribe_snapshots(&self, _market_id: &str) -> Result<SnapshotStream, DataHubError> {
        let stream: Pin<Box<dyn Stream<Item = MarketSnapshot> + Send>> =
            Box::pin(futures::stream::empty());
        Ok(stream)
    }

    async fn get_slice(&self, hub_ts: chrono::DateTime<Utc>) -> Result<HubSlice, DataHubError> {
        let mut snapshot = self.snapshot.clone();
        snapshot.carried_forward = snapshot.as_of < hub_ts;
        Ok(HubSlice {
            hub_ts,
            ingestion_ts: Utc::now(),
            markets: std::collections::BTreeMap::from([(snapshot.market_id.clone(), snapshot)]),
            slice_meta: HubSliceMeta {
                market_count: 1,
                stale_count: 0,
                partial_count: 0,
            },
        })
    }

    async fn list_slices_range(
        &self,
        _from_ts: chrono::DateTime<Utc>,
        _to_ts: chrono::DateTime<Utc>,
        _limit: usize,
    ) -> Result<Vec<HubSlice>, DataHubError> {
        Ok(self.slices.clone())
    }

    async fn get_market_at_time(
        &self,
        market_id: &str,
        _hub_ts: chrono::DateTime<Utc>,
    ) -> Result<MarketSnapshot, DataHubError> {
        self.get_snapshot(market_id).await
    }
}

#[tokio::test]
async fn polymarket_agent_proposes_candidates_via_unified_interface() {
    let market_id = "51939490109676186832507970701169130490548061087912630009168726706475001411420";
    let hub = StubHub::new(market_id, 0.44, 150, false);

    let agent = PolymarketAgent::new(
        "poly-agent",
        AgentConfig {
            watchlist: vec![market_id.to_string()],
            min_edge: 0.005,
            max_candidates: 2,
        },
    );

    let opportunities = agent
        .propose_opportunities(&hub, &PortfolioView::default(), Utc::now())
        .await
        .expect("propose should succeed");

    assert!(!opportunities.is_empty(), "expected at least one candidate");
    assert!(
        opportunities.len() <= 2,
        "must respect max_candidates in unified interface"
    );

    let candidate = &opportunities[0];
    assert_eq!(candidate.agent_id, "poly-agent");
    assert_eq!(candidate.market_id, market_id);
    assert!(candidate.expected_edge >= 0.005);
    assert!((0.0..=1.0).contains(&candidate.confidence));
    assert!(
        matches!(
            candidate.direction,
            OpportunityDirection::LongYes | OpportunityDirection::LongNo
        ),
        "direction should be actionable for polymarket binary markets"
    );
}

#[tokio::test]
async fn polymarket_agent_monitors_positions_via_unified_interface() {
    let market_id = "51939490109676186832507970701169130490548061087912630009168726706475001411420";
    let hub = StubHub::new(market_id, 0.62, 120, false);
    let now = Utc::now();

    let portfolio = PortfolioView {
        cash_usd: 1_000.0,
        active_positions: vec![PortfolioPosition {
            market_id: market_id.to_string(),
            side: OpportunityDirection::LongYes,
            notional_usd: 100.0,
            entry_price: 0.52,
            opened_at: now - Duration::minutes(10),
        }],
        max_active_opportunities: 4,
    };

    let agent = PolymarketAgent::new("poly-agent", AgentConfig::default());
    let checks = agent
        .monitor_positions(&hub, &portfolio, now)
        .await
        .expect("monitor should succeed");
    assert_eq!(checks.len(), 1);
    assert_eq!(checks[0].market_id, market_id);
    assert!(
        checks[0].status == "take-profit" || checks[0].status == "hold",
        "status should be produced through unified monitor interface"
    );
    assert!(
        checks[0].detail.contains("pnl_pct"),
        "monitor output should contain risk detail"
    );
}

#[tokio::test]
async fn invalid_polymarket_ids_are_filtered_from_universe() {
    let market_id = "51939490109676186832507970701169130490548061087912630009168726706475001411420";
    let hub = StubHub::new(market_id, 0.44, 150, false);
    let agent = PolymarketAgent::new(
        "poly-agent",
        AgentConfig {
            watchlist: vec!["not-a-token-id".to_string()],
            min_edge: 0.001,
            max_candidates: 3,
        },
    );

    let opportunities = agent
        .propose_opportunities(&hub, &PortfolioView::default(), Utc::now())
        .await
        .expect("propose should not fail when watchlist contains invalid id");
    assert!(opportunities.is_empty(), "invalid ids should be ignored");

    let health = agent.health().await;
    assert_eq!(health.status, "ok");
}

#[tokio::test]
async fn missing_snapshot_updates_health_to_degraded() {
    let market_id = "51939490109676186832507970701169130490548061087912630009168726706475001411420";
    let hub = Arc::new(StubHub::new(market_id, 0.44, 150, false));
    let agent = PolymarketAgent::new(
        "poly-agent",
        AgentConfig {
            watchlist: vec!["123".to_string()],
            min_edge: 0.001,
            max_candidates: 3,
        },
    );

    let result = agent
        .propose_opportunities(hub.as_ref(), &PortfolioView::default(), Utc::now())
        .await;
    assert!(
        result.is_err(),
        "missing snapshot should bubble up as error"
    );

    let health = agent.health().await;
    assert_eq!(health.status, "degraded");
    assert!(health.last_error.is_some());
}

#[tokio::test]
async fn polymarket_agent_uses_news_and_slice_history_in_risk_hints() {
    let market_id = "51939490109676186832507970701169130490548061087912630009168726706475001411420";
    let hub = StubHub::new(market_id, 0.48, 120, false);
    let agent = PolymarketAgent::new(
        "poly-agent",
        AgentConfig {
            watchlist: vec![market_id.to_string()],
            min_edge: 0.001,
            max_candidates: 5,
        },
    );

    let opportunities = agent
        .propose_opportunities(&hub, &PortfolioView::default(), Utc::now())
        .await
        .expect("propose should succeed");

    assert!(!opportunities.is_empty());
    let combined_hints: Vec<_> = opportunities
        .iter()
        .flat_map(|candidate| candidate.risk_hints.keys().cloned())
        .collect();
    assert!(combined_hints.iter().any(|key| key == "news_count"));
    assert!(combined_hints.iter().any(|key| key == "history_points"));
}

fn make_slice(
    market_id: &str,
    hub_ts: chrono::DateTime<Utc>,
    midpoint: f64,
    carried: bool,
) -> HubSlice {
    let snapshot = MarketSnapshot {
        as_of: hub_ts,
        market_id: market_id.to_string(),
        book_ticker: BookTicker {
            bids: vec![OrderLevel {
                price: (midpoint - 0.01).max(0.0),
                size: 250.0,
            }],
            asks: vec![OrderLevel {
                price: (midpoint + 0.01).min(1.0),
                size: 180.0,
            }],
            best_bid: Some((midpoint - 0.01).max(0.0)),
            best_ask: Some((midpoint + 0.01).min(1.0)),
            midpoint: Some(midpoint),
            spread: Some(0.02),
            last_trade: Some(midpoint),
        },
        fx_context: vec![],
        session_state: MarketSession {
            market_id: market_id.to_string(),
            state: MarketSessionState::Open,
            timezone: "UTC".to_string(),
            opens_at: None,
            closes_at: None,
            note: Some("stub".to_string()),
        },
        news_refs: vec!["n1".to_string()],
        quality_flags: QualityFlags {
            stale: false,
            partial: false,
            source_lag_ms: 100,
        },
        carried_forward: carried,
    };
    HubSlice {
        hub_ts,
        ingestion_ts: hub_ts,
        markets: std::collections::BTreeMap::from([(market_id.to_string(), snapshot)]),
        slice_meta: HubSliceMeta {
            market_count: 1,
            stale_count: 0,
            partial_count: 0,
        },
    }
}
