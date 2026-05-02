use std::collections::{BTreeMap, BTreeSet};

use async_trait::async_trait;
use chrono::{DateTime, Utc};
use tokio::sync::RwLock;

use crate::agent::{AgentConfig, AgentError, MarketTradingAgent};
use crate::contracts::{
    AgentHealth, HubSlice, MarketSnapshot, NewsEvent, OpportunityCandidate, OpportunityDirection,
    PortfolioPosition, PortfolioView, PositionCheck,
};
use crate::data_hub::MarketDataHub;

#[async_trait]
trait UniverseScanner: Send + Sync {
    async fn scan(
        &self,
        _hub: &dyn MarketDataHub,
        portfolio: &PortfolioView,
        _now: DateTime<Utc>,
    ) -> Result<Vec<String>, AgentError>;
}

#[async_trait]
trait StrategyRunner: Send + Sync {
    async fn run(
        &self,
        context: &StrategyContext,
        _portfolio: &PortfolioView,
        _now: DateTime<Utc>,
    ) -> Result<Vec<StrategySignal>, AgentError>;
}

trait OpportunityScorer: Send + Sync {
    fn score(
        &self,
        agent_id: &str,
        signals: Vec<StrategySignal>,
        now: DateTime<Utc>,
    ) -> Vec<OpportunityCandidate>;
}

#[async_trait]
trait PositionMonitor: Send + Sync {
    async fn monitor(
        &self,
        hub: &dyn MarketDataHub,
        portfolio: &PortfolioView,
        now: DateTime<Utc>,
    ) -> Result<Vec<PositionCheck>, AgentError>;
}

#[derive(Debug, Clone)]
struct StrategySignal {
    market_id: String,
    direction: OpportunityDirection,
    confidence: f64,
    expected_edge: f64,
    time_horizon_secs: u64,
    risk_hints: BTreeMap<String, f64>,
}

#[derive(Debug, Clone)]
struct StrategyContext {
    snapshot: MarketSnapshot,
    recent_slices: Vec<HubSlice>,
    recent_news: Vec<NewsEvent>,
}

#[derive(Default)]
struct WatchlistUniverseScanner {
    watchlist: Vec<String>,
}

#[async_trait]
impl UniverseScanner for WatchlistUniverseScanner {
    async fn scan(
        &self,
        _hub: &dyn MarketDataHub,
        portfolio: &PortfolioView,
        _now: DateTime<Utc>,
    ) -> Result<Vec<String>, AgentError> {
        let mut universe = BTreeSet::new();
        for market_id in &self.watchlist {
            if is_polymarket_market_id(market_id) {
                universe.insert(market_id.clone());
            }
        }
        for position in &portfolio.active_positions {
            if is_polymarket_market_id(&position.market_id) {
                universe.insert(position.market_id.clone());
            }
        }
        Ok(universe.into_iter().collect())
    }
}

struct MidpointDislocationRunner;

#[async_trait]
impl StrategyRunner for MidpointDislocationRunner {
    async fn run(
        &self,
        context: &StrategyContext,
        _portfolio: &PortfolioView,
        _now: DateTime<Utc>,
    ) -> Result<Vec<StrategySignal>, AgentError> {
        let snapshot = &context.snapshot;
        let midpoint = match snapshot.book_ticker.midpoint {
            Some(midpoint) => midpoint,
            None => return Ok(Vec::new()),
        };
        let dislocation = 0.5 - midpoint;
        let edge = dislocation.abs();
        if edge < 0.002 {
            return Ok(Vec::new());
        }

        let direction = if dislocation > 0.0 {
            OpportunityDirection::LongYes
        } else {
            OpportunityDirection::LongNo
        };
        let spread = snapshot.book_ticker.spread.unwrap_or(0.02).max(0.0);
        let trend = midpoint_trend(&context.recent_slices, &snapshot.market_id).unwrap_or(0.0);
        let catalyst = news_catalyst_score(&context.recent_news);
        let trend_alignment = if direction_matches_trend(&direction, trend) {
            0.12
        } else {
            -0.08
        };
        let confidence = clamp01((1.0 - spread * 8.0).max(0.2) + trend_alignment + catalyst * 0.15);
        let size_hint = top_size(snapshot).max(1.0).min(5_000.0);

        let mut risk_hints = BTreeMap::new();
        risk_hints.insert("max_notional_usd".to_string(), size_hint * 0.6);
        risk_hints.insert("stop_loss_pct".to_string(), 0.03);
        risk_hints.insert("midpoint_trend".to_string(), trend);
        risk_hints.insert("news_catalyst".to_string(), catalyst);
        risk_hints.insert("news_count".to_string(), context.recent_news.len() as f64);

        Ok(vec![StrategySignal {
            market_id: snapshot.market_id.clone(),
            direction,
            confidence,
            expected_edge: edge,
            time_horizon_secs: 1_800,
            risk_hints,
        }])
    }
}

struct OrderbookImbalanceRunner;

#[async_trait]
impl StrategyRunner for OrderbookImbalanceRunner {
    async fn run(
        &self,
        context: &StrategyContext,
        _portfolio: &PortfolioView,
        _now: DateTime<Utc>,
    ) -> Result<Vec<StrategySignal>, AgentError> {
        let snapshot = &context.snapshot;
        let bid_size = snapshot
            .book_ticker
            .bids
            .first()
            .map(|x| x.size)
            .unwrap_or(0.0)
            .max(0.0);
        let ask_size = snapshot
            .book_ticker
            .asks
            .first()
            .map(|x| x.size)
            .unwrap_or(0.0)
            .max(0.0);
        let denom = bid_size + ask_size;
        if denom <= f64::EPSILON {
            return Ok(Vec::new());
        }

        let imbalance = (bid_size - ask_size) / denom;
        let abs_imbalance = imbalance.abs();
        if abs_imbalance < 0.08 {
            return Ok(Vec::new());
        }

        let direction = if imbalance > 0.0 {
            OpportunityDirection::LongYes
        } else {
            OpportunityDirection::LongNo
        };
        let spread = snapshot.book_ticker.spread.unwrap_or(0.02).max(0.0);
        let history_depth = historical_depth(&context.recent_slices, &snapshot.market_id);
        let edge = (abs_imbalance * spread.max(0.01) * (1.0 + history_depth * 0.15)).min(0.20);
        let confidence = clamp01((abs_imbalance * 1.4).max(0.25) + history_depth * 0.05);

        let mut risk_hints = BTreeMap::new();
        risk_hints.insert("imbalance".to_string(), imbalance);
        risk_hints.insert("max_notional_usd".to_string(), denom.min(4_000.0) * 0.4);
        risk_hints.insert("history_points".to_string(), history_depth);

        Ok(vec![StrategySignal {
            market_id: snapshot.market_id.clone(),
            direction,
            confidence,
            expected_edge: edge,
            time_horizon_secs: 900,
            risk_hints,
        }])
    }
}

struct SliceMomentumRunner;

#[async_trait]
impl StrategyRunner for SliceMomentumRunner {
    async fn run(
        &self,
        context: &StrategyContext,
        _portfolio: &PortfolioView,
        _now: DateTime<Utc>,
    ) -> Result<Vec<StrategySignal>, AgentError> {
        let snapshot = &context.snapshot;
        let trend = match midpoint_trend(&context.recent_slices, &snapshot.market_id) {
            Some(trend) => trend,
            None => return Ok(Vec::new()),
        };
        let abs_trend = trend.abs();
        if abs_trend < 0.01 {
            return Ok(Vec::new());
        }

        let direction = if trend > 0.0 {
            OpportunityDirection::LongYes
        } else {
            OpportunityDirection::LongNo
        };
        let carry_forward_ratio = carry_forward_ratio(&context.recent_slices, &snapshot.market_id);
        let news_catalyst = news_catalyst_score(&context.recent_news);

        let mut risk_hints = BTreeMap::new();
        risk_hints.insert("carry_forward_ratio".to_string(), carry_forward_ratio);
        risk_hints.insert("news_catalyst".to_string(), news_catalyst);
        risk_hints.insert("trend_strength".to_string(), abs_trend);

        Ok(vec![StrategySignal {
            market_id: snapshot.market_id.clone(),
            direction,
            confidence: clamp01(
                abs_trend * 6.0 + news_catalyst * 0.10 - carry_forward_ratio * 0.25,
            ),
            expected_edge: (abs_trend * (1.0 - carry_forward_ratio).max(0.2)).min(0.25),
            time_horizon_secs: 1_200,
            risk_hints,
        }])
    }
}

#[derive(Debug)]
struct WeightedOpportunityScorer {
    min_edge: f64,
    max_candidates: usize,
}

struct SignalAggregate {
    direction: OpportunityDirection,
    expected_edge_sum: f64,
    confidence_sum: f64,
    horizon_sum: u64,
    count: u64,
    risk_hints: BTreeMap<String, f64>,
}

impl Default for SignalAggregate {
    fn default() -> Self {
        Self {
            direction: OpportunityDirection::Flat,
            expected_edge_sum: 0.0,
            confidence_sum: 0.0,
            horizon_sum: 0,
            count: 0,
            risk_hints: BTreeMap::new(),
        }
    }
}

impl OpportunityScorer for WeightedOpportunityScorer {
    fn score(
        &self,
        agent_id: &str,
        signals: Vec<StrategySignal>,
        now: DateTime<Utc>,
    ) -> Vec<OpportunityCandidate> {
        let mut grouped: BTreeMap<(String, &'static str), SignalAggregate> = BTreeMap::new();
        for signal in signals {
            let key = (signal.market_id.clone(), direction_key(&signal.direction));
            let entry = grouped.entry(key).or_insert_with(|| SignalAggregate {
                direction: signal.direction.clone(),
                ..SignalAggregate::default()
            });
            entry.expected_edge_sum += signal.expected_edge;
            entry.confidence_sum += signal.confidence;
            entry.horizon_sum += signal.time_horizon_secs;
            entry.count += 1;
            merge_risk_hints(&mut entry.risk_hints, signal.risk_hints);
        }

        let mut best_by_market: BTreeMap<String, (f64, OpportunityCandidate)> = BTreeMap::new();
        for ((market_id, _), aggregate) in grouped {
            if aggregate.count == 0 {
                continue;
            }
            let count = aggregate.count as f64;
            let expected_edge = aggregate.expected_edge_sum / count;
            if expected_edge < self.min_edge {
                continue;
            }
            let confidence = clamp01(aggregate.confidence_sum / count);
            let score = expected_edge * confidence;
            let trace_id = format!("{agent_id}-{market_id}-{}", now.timestamp_millis());
            let candidate = OpportunityCandidate {
                agent_id: agent_id.to_string(),
                market_id: market_id.clone(),
                direction: aggregate.direction,
                confidence,
                expected_edge,
                time_horizon_secs: (aggregate.horizon_sum / aggregate.count).max(60),
                risk_hints: aggregate.risk_hints,
                trace_id,
            };

            match best_by_market.get(&market_id) {
                Some((best_score, _)) if *best_score >= score => {}
                _ => {
                    best_by_market.insert(market_id, (score, candidate));
                }
            }
        }

        let mut ranked: Vec<(f64, OpportunityCandidate)> = best_by_market.into_values().collect();
        ranked.sort_by(|a, b| b.0.total_cmp(&a.0));
        ranked
            .into_iter()
            .take(self.max_candidates)
            .map(|(_, candidate)| candidate)
            .collect()
    }
}

#[derive(Debug, Clone)]
struct DefaultPositionMonitor {
    stop_loss_pct: f64,
    take_profit_pct: f64,
}

#[async_trait]
impl PositionMonitor for DefaultPositionMonitor {
    async fn monitor(
        &self,
        hub: &dyn MarketDataHub,
        portfolio: &PortfolioView,
        now: DateTime<Utc>,
    ) -> Result<Vec<PositionCheck>, AgentError> {
        let mut checks = Vec::with_capacity(portfolio.active_positions.len());
        for position in &portfolio.active_positions {
            let snapshot = hub.get_snapshot(&position.market_id).await.map_err(|e| {
                AgentError::Data(format!(
                    "failed to load snapshot for {}: {e}",
                    position.market_id
                ))
            })?;
            checks.push(build_position_check(position, &snapshot, self, now));
        }
        Ok(checks)
    }
}

pub struct PolymarketAgent {
    id: String,
    config: AgentConfig,
    universe_scanner: Box<dyn UniverseScanner>,
    strategy_runners: Vec<Box<dyn StrategyRunner>>,
    opportunity_scorer: Box<dyn OpportunityScorer>,
    position_monitor: Box<dyn PositionMonitor>,
    health: RwLock<AgentHealth>,
}

impl PolymarketAgent {
    pub fn new(id: impl Into<String>, config: AgentConfig) -> Self {
        let max_candidates = config.max_candidates.max(1);
        let min_edge = config.min_edge.max(0.0);
        let watchlist = config.watchlist.clone();

        Self {
            id: id.into(),
            config,
            universe_scanner: Box::<WatchlistUniverseScanner>::new(WatchlistUniverseScanner {
                watchlist,
            }),
            strategy_runners: vec![
                Box::<MidpointDislocationRunner>::new(MidpointDislocationRunner),
                Box::<OrderbookImbalanceRunner>::new(OrderbookImbalanceRunner),
                Box::<SliceMomentumRunner>::new(SliceMomentumRunner),
            ],
            opportunity_scorer: Box::<WeightedOpportunityScorer>::new(WeightedOpportunityScorer {
                min_edge,
                max_candidates,
            }),
            position_monitor: Box::<DefaultPositionMonitor>::new(DefaultPositionMonitor {
                stop_loss_pct: 0.03,
                take_profit_pct: 0.05,
            }),
            health: RwLock::new(AgentHealth {
                status: "starting".to_string(),
                lag_ms: 0,
                last_error: None,
                observed_at: Utc::now(),
            }),
        }
    }

    async fn record_success(&self, lag_ms: i64) {
        let mut health = self.health.write().await;
        health.status = "ok".to_string();
        health.lag_ms = lag_ms.max(0);
        health.last_error = None;
        health.observed_at = Utc::now();
    }

    async fn record_error(&self, err: impl Into<String>) {
        let mut health = self.health.write().await;
        health.status = "degraded".to_string();
        health.last_error = Some(err.into());
        health.observed_at = Utc::now();
    }
}

#[async_trait]
impl MarketTradingAgent for PolymarketAgent {
    fn id(&self) -> &str {
        &self.id
    }

    fn config(&self) -> &AgentConfig {
        &self.config
    }

    async fn propose_opportunities(
        &self,
        hub: &dyn MarketDataHub,
        portfolio: &PortfolioView,
        now: DateTime<Utc>,
    ) -> Result<Vec<OpportunityCandidate>, AgentError> {
        let run: Result<(Vec<OpportunityCandidate>, i64), AgentError> = async {
            let universe = self.universe_scanner.scan(hub, portfolio, now).await?;
            if universe.is_empty() {
                return Ok((Vec::new(), 0));
            }

            let mut signals = Vec::new();
            let mut max_lag_ms = 0;
            for market_id in universe {
                let context = load_strategy_context(hub, &market_id, now).await?;
                max_lag_ms = max_lag_ms.max(context.snapshot.quality_flags.source_lag_ms);
                for runner in &self.strategy_runners {
                    let mut output = runner.run(&context, portfolio, now).await?;
                    signals.append(&mut output);
                }
            }

            let candidates = self.opportunity_scorer.score(&self.id, signals, now);
            Ok((candidates, max_lag_ms))
        }
        .await;

        match run {
            Ok((candidates, lag_ms)) => {
                self.record_success(lag_ms).await;
                Ok(candidates)
            }
            Err(err) => {
                self.record_error(err.to_string()).await;
                Err(err)
            }
        }
    }

    async fn monitor_positions(
        &self,
        hub: &dyn MarketDataHub,
        portfolio: &PortfolioView,
        now: DateTime<Utc>,
    ) -> Result<Vec<PositionCheck>, AgentError> {
        match self.position_monitor.monitor(hub, portfolio, now).await {
            Ok(checks) => {
                self.record_success(0).await;
                Ok(checks)
            }
            Err(err) => {
                self.record_error(err.to_string()).await;
                Err(err)
            }
        }
    }

    async fn health(&self) -> AgentHealth {
        self.health.read().await.clone()
    }
}

fn build_position_check(
    position: &PortfolioPosition,
    snapshot: &MarketSnapshot,
    monitor: &DefaultPositionMonitor,
    now: DateTime<Utc>,
) -> PositionCheck {
    let mark_price = snapshot
        .book_ticker
        .midpoint
        .or(snapshot.book_ticker.last_trade)
        .unwrap_or(position.entry_price)
        .clamp(0.0, 1.0);
    let pnl_pct = estimate_pnl_pct(&position.side, position.entry_price, mark_price);

    let status = if snapshot.quality_flags.stale {
        "data-stale"
    } else if pnl_pct <= -monitor.stop_loss_pct {
        "cut-loss"
    } else if pnl_pct >= monitor.take_profit_pct {
        "take-profit"
    } else {
        "hold"
    };

    PositionCheck {
        market_id: position.market_id.clone(),
        status: status.to_string(),
        detail: format!(
            "mark={mark_price:.4} entry={:.4} pnl_pct={pnl_pct:.4} partial={} lag_ms={}",
            position.entry_price,
            snapshot.quality_flags.partial,
            snapshot.quality_flags.source_lag_ms
        ),
        as_of: now,
    }
}

fn estimate_pnl_pct(side: &OpportunityDirection, entry_price: f64, mark_price: f64) -> f64 {
    match side {
        OpportunityDirection::LongYes => {
            if entry_price <= 0.0 {
                0.0
            } else {
                (mark_price - entry_price) / entry_price
            }
        }
        OpportunityDirection::LongNo => {
            let entry_no = (1.0 - entry_price).max(0.0001);
            let mark_no = (1.0 - mark_price).max(0.0);
            (mark_no - entry_no) / entry_no
        }
        OpportunityDirection::Flat => 0.0,
    }
}

fn merge_risk_hints(base: &mut BTreeMap<String, f64>, updates: BTreeMap<String, f64>) {
    for (k, v) in updates {
        match base.get(&k) {
            Some(existing) if existing.abs() >= v.abs() => {}
            _ => {
                base.insert(k, v);
            }
        }
    }
}

fn top_size(snapshot: &MarketSnapshot) -> f64 {
    let bid = snapshot
        .book_ticker
        .bids
        .first()
        .map(|x| x.size)
        .unwrap_or(0.0);
    let ask = snapshot
        .book_ticker
        .asks
        .first()
        .map(|x| x.size)
        .unwrap_or(0.0);
    bid.max(ask)
}

async fn load_strategy_context(
    hub: &dyn MarketDataHub,
    market_id: &str,
    now: DateTime<Utc>,
) -> Result<StrategyContext, AgentError> {
    let snapshot = hub
        .get_snapshot(market_id)
        .await
        .map_err(|e| AgentError::Data(format!("snapshot fetch failed for {market_id}: {e}")))?;
    let recent_slices = hub
        .list_slices_range(now - chrono::Duration::minutes(15), now, 128)
        .await
        .unwrap_or_default();
    let recent_news = hub
        .get_news(market_id, now - chrono::Duration::hours(8), 16)
        .await
        .unwrap_or_default();

    Ok(StrategyContext {
        snapshot,
        recent_slices,
        recent_news,
    })
}

fn midpoint_trend(slices: &[HubSlice], market_id: &str) -> Option<f64> {
    let mut first = None;
    let mut last = None;
    for slice in slices {
        let snapshot = slice.markets.get(market_id)?;
        let midpoint = snapshot
            .book_ticker
            .midpoint
            .or(snapshot.book_ticker.last_trade)?;
        if first.is_none() {
            first = Some(midpoint);
        }
        last = Some(midpoint);
    }
    match (first, last) {
        (Some(start), Some(end)) => Some(end - start),
        _ => None,
    }
}

fn carry_forward_ratio(slices: &[HubSlice], market_id: &str) -> f64 {
    let mut total = 0.0;
    let mut carried = 0.0;
    for slice in slices {
        if let Some(snapshot) = slice.markets.get(market_id) {
            total += 1.0;
            if snapshot.carried_forward {
                carried += 1.0;
            }
        }
    }
    if total <= f64::EPSILON {
        0.0
    } else {
        carried / total
    }
}

fn historical_depth(slices: &[HubSlice], market_id: &str) -> f64 {
    slices
        .iter()
        .filter(|slice| slice.markets.contains_key(market_id))
        .count() as f64
}

fn news_catalyst_score(news: &[NewsEvent]) -> f64 {
    if news.is_empty() {
        return 0.0;
    }

    let mut score = 0.0;
    for event in news {
        let headline = event.headline.to_ascii_lowercase();
        if headline.contains("breaking") || headline.contains("urgent") {
            score += 0.45;
        }
        if headline.contains("fed")
            || headline.contains("rates")
            || headline.contains("inflation")
            || headline.contains("cpi")
            || headline.contains("bitcoin")
            || headline.contains("crypto")
            || headline.contains("trump")
            || headline.contains("election")
        {
            score += 0.25;
        }
    }
    (score / news.len() as f64).clamp(0.0, 1.0)
}

fn direction_matches_trend(direction: &OpportunityDirection, trend: f64) -> bool {
    match direction {
        OpportunityDirection::LongYes => trend >= 0.0,
        OpportunityDirection::LongNo => trend <= 0.0,
        OpportunityDirection::Flat => true,
    }
}

fn is_polymarket_market_id(market_id: &str) -> bool {
    !market_id.is_empty() && market_id.bytes().all(|b| b.is_ascii_digit())
}

fn direction_key(direction: &OpportunityDirection) -> &'static str {
    match direction {
        OpportunityDirection::LongYes => "long_yes",
        OpportunityDirection::LongNo => "long_no",
        OpportunityDirection::Flat => "flat",
    }
}

fn clamp01(value: f64) -> f64 {
    value.clamp(0.0, 1.0)
}
