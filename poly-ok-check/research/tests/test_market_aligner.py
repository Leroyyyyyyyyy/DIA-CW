from __future__ import annotations

import pandas as pd

from research.core.market_aligner import MarketAligner
from research.schemas.data_package import DataPackage


def make_package(available_ts_s: float) -> DataPackage:
    return DataPackage(
        source_ts_s=available_ts_s - 30,
        available_ts_s=available_ts_s,
        match_id="m1",
        map_name="nuke",
        round_number=2,
        phase="live",
        scoreboard={"team_a_rounds": 1, "team_b_rounds": 0},
        team_states={"team_a": {"economy": 7000, "loss_bonus": 1400, "alive": 4}, "team_b": {"economy": 2200, "loss_bonus": 1900, "alive": 2}},
        player_states={},
        event_slice=[],
        visibility_flags={"player_states": "missing", "team_states": "ok", "economy_estimated": False},
    )


def test_aligns_without_looking_forward() -> None:
    aligner = MarketAligner()
    market_df = pd.DataFrame(
        [
            {"timestamp_s": 39.0, "best_bid": 0.48, "best_ask": 0.52, "orderbook_mid": 0.50, "depth_usd": 1000.0, "lp_reward_estimate": 0.0},
            {"timestamp_s": 41.0, "best_bid": 0.60, "best_ask": 0.64, "orderbook_mid": 0.62, "depth_usd": 1000.0, "lp_reward_estimate": 0.0},
        ]
    )
    result = aligner.align_one(make_package(40.0), market_df)
    assert result["market_snapshot_ts_s"] == 39.0


def test_populates_market_fields() -> None:
    aligner = MarketAligner()
    market_df = pd.DataFrame(
        [{"timestamp_s": 40.0, "best_bid": 0.48, "best_ask": 0.52, "orderbook_mid": 0.50, "depth_usd": 900.0, "lp_reward_estimate": 0.01}]
    )
    result = aligner.align_one(make_package(40.0), market_df)
    assert result["market_implied_prob"] == 0.5
    assert result["best_bid"] > 0
    assert result["depth_usd"] == 900.0


def test_marks_missing_snapshot_as_stale() -> None:
    aligner = MarketAligner()
    market_df = pd.DataFrame(columns=["timestamp_s", "best_bid", "best_ask", "orderbook_mid", "depth_usd", "lp_reward_estimate"])
    result = aligner.align_one(make_package(40.0), market_df)
    assert result["is_stale_snapshot"] is True


def test_marks_old_snapshot_as_stale() -> None:
    aligner = MarketAligner(stale_threshold_ms=1000.0)
    market_df = pd.DataFrame(
        [{"timestamp_s": 35.0, "best_bid": 0.48, "best_ask": 0.52, "orderbook_mid": 0.50, "depth_usd": 900.0, "lp_reward_estimate": 0.01}]
    )
    result = aligner.align_one(make_package(40.0), market_df)
    assert result["is_stale_snapshot"] is True

