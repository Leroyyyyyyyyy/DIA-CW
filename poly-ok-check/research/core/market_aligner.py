from __future__ import annotations

import pandas as pd

from research.schemas.data_package import DataPackage
from research.utils.time_utils import clip_probability, safe_float, seconds_to_millis


TIMESTAMP_COL = "timestamp_s"
BEST_BID_COL = "best_bid"
BEST_ASK_COL = "best_ask"
ORDERBOOK_MID_COL = "orderbook_mid"
DEPTH_USD_COL = "depth_usd"
LP_REWARD_COL = "lp_reward_estimate"


class MarketAligner:
    def __init__(self, stale_threshold_ms: float = 15_000.0):
        self.stale_threshold_ms = stale_threshold_ms

    def align_one(self, data_package: DataPackage, market_df: pd.DataFrame) -> dict:
        required = {TIMESTAMP_COL, BEST_BID_COL, BEST_ASK_COL}
        missing = sorted(required - set(market_df.columns))
        if missing:
            raise ValueError(f"market_df missing columns: {missing}")

        eligible = market_df[market_df[TIMESTAMP_COL] <= data_package.available_ts_s]
        if eligible.empty:
            return {
                "market_snapshot_ts_s": float("nan"),
                "market_age_ms": float("inf"),
                "alignment_gap_ms": float("inf"),
                "is_stale_snapshot": True,
                "market_implied_prob": 0.5,
                "orderbook_mid": 0.5,
                "best_bid": 0.0,
                "best_ask": 0.0,
                "depth_usd": 0.0,
                "lp_reward_estimate": 0.0,
            }

        snapshot = eligible.sort_values(TIMESTAMP_COL).iloc[-1]
        snapshot_ts = safe_float(snapshot.get(TIMESTAMP_COL))
        age_ms = seconds_to_millis(data_package.available_ts_s - snapshot_ts)
        best_bid = clip_probability(safe_float(snapshot.get(BEST_BID_COL), default=0.0)) if safe_float(snapshot.get(BEST_BID_COL), default=-1.0) > 0 else 0.0
        best_ask = clip_probability(safe_float(snapshot.get(BEST_ASK_COL), default=0.0)) if safe_float(snapshot.get(BEST_ASK_COL), default=-1.0) > 0 else 0.0
        mid_value = safe_float(snapshot.get(ORDERBOOK_MID_COL), default=float("nan"))
        if mid_value > 0:
            implied = clip_probability(mid_value)
            orderbook_mid = implied
        elif best_bid > 0 and best_ask > 0:
            orderbook_mid = clip_probability((best_bid + best_ask) / 2.0)
            implied = orderbook_mid
        else:
            orderbook_mid = 0.5
            implied = 0.5

        return {
            "market_snapshot_ts_s": snapshot_ts,
            "market_age_ms": age_ms,
            "alignment_gap_ms": age_ms,
            "is_stale_snapshot": age_ms > self.stale_threshold_ms,
            "market_implied_prob": implied,
            "orderbook_mid": orderbook_mid,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "depth_usd": max(safe_float(snapshot.get(DEPTH_USD_COL), default=0.0), 0.0),
            "lp_reward_estimate": max(safe_float(snapshot.get(LP_REWARD_COL), default=0.0), 0.0),
        }

