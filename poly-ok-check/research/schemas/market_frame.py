from __future__ import annotations

from dataclasses import dataclass

from research.schemas.data_package import DataPackage


@dataclass(slots=True)
class AlignedMarketFrame:
    data_package: DataPackage
    market_snapshot_ts_s: float
    market_age_ms: float
    alignment_gap_ms: float
    is_stale_snapshot: bool
    model_win_prob: float
    fair_win_prob: float
    market_implied_prob: float
    orderbook_mid: float
    best_bid: float
    best_ask: float
    depth_usd: float
    lp_reward_estimate: float
    fees: float
    slippage_est: float
    latency_penalty: float
    liquidity_penalty: float
    edge_raw: float
    edge_net: float

    def to_flat_dict(self) -> dict:
        data = self.data_package.to_dict()
        flat = {
            "source_ts_s": data["source_ts_s"],
            "available_ts_s": data["available_ts_s"],
            "match_id": data["match_id"],
            "map_name": data["map_name"],
            "round_number": data["round_number"],
            "phase": data["phase"],
            "market_snapshot_ts_s": self.market_snapshot_ts_s,
            "market_age_ms": self.market_age_ms,
            "alignment_gap_ms": self.alignment_gap_ms,
            "is_stale_snapshot": self.is_stale_snapshot,
            "model_win_prob": self.model_win_prob,
            "fair_win_prob": self.fair_win_prob,
            "market_implied_prob": self.market_implied_prob,
            "orderbook_mid": self.orderbook_mid,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "depth_usd": self.depth_usd,
            "lp_reward_estimate": self.lp_reward_estimate,
            "fees": self.fees,
            "slippage_est": self.slippage_est,
            "latency_penalty": self.latency_penalty,
            "liquidity_penalty": self.liquidity_penalty,
            "edge_raw": self.edge_raw,
            "edge_net": self.edge_net,
        }
        flat["scoreboard"] = data["scoreboard"]
        flat["team_states"] = data["team_states"]
        flat["visibility_flags"] = data["visibility_flags"]
        return flat

