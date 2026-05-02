from __future__ import annotations

from research.schemas.data_package import DataPackage
from research.schemas.market_frame import AlignedMarketFrame
from research.schemas.risk_context import RiskContext
from research.strategy.agent_commander import AgentCommander


def make_frame(fair_win_prob: float, edge_net: float, is_stale_snapshot: bool = False, depth_usd: float = 1000.0) -> AlignedMarketFrame:
    package = DataPackage(
        source_ts_s=10.0,
        available_ts_s=40.0,
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
    return AlignedMarketFrame(
        data_package=package,
        market_snapshot_ts_s=39.0,
        market_age_ms=1000.0,
        alignment_gap_ms=1000.0,
        is_stale_snapshot=is_stale_snapshot,
        model_win_prob=fair_win_prob,
        fair_win_prob=fair_win_prob,
        market_implied_prob=0.50,
        orderbook_mid=0.50,
        best_bid=0.49,
        best_ask=0.51,
        depth_usd=depth_usd,
        lp_reward_estimate=0.0,
        fees=0.01,
        slippage_est=0.0,
        latency_penalty=0.0,
        liquidity_penalty=0.0,
        edge_raw=fair_win_prob - 0.50,
        edge_net=edge_net,
    )


def make_risk(current_position_side=None, event_tier: str = "S") -> RiskContext:
    return RiskContext(
        equity=10_000.0,
        cash=10_000.0,
        current_position_side=current_position_side,
        current_position_size=1.0 if current_position_side else 0.0,
        drawdown=0.0,
        event_tier=event_tier,
        allow_new_entry=True,
        reduce_only=False,
    )


def test_hold_with_strong_yes_position() -> None:
    commander = AgentCommander()
    decision = commander.decide(make_frame(0.95, 0.05), make_risk(current_position_side="YES"))
    assert decision["action"] == "HOLD"


def test_exit_when_yes_position_breaks_down() -> None:
    commander = AgentCommander()
    decision = commander.decide(make_frame(0.05, -0.10), make_risk(current_position_side="YES"))
    assert decision["action"] == "EXIT"


def test_skip_stale_snapshot() -> None:
    commander = AgentCommander()
    decision = commander.decide(make_frame(0.70, 0.10, is_stale_snapshot=True), make_risk())
    assert decision["action"] == "SKIP"


def test_skip_negative_net_edge() -> None:
    commander = AgentCommander()
    decision = commander.decide(make_frame(0.70, -0.01), make_risk())
    assert decision["action"] == "SKIP"


def test_skip_non_s_tier() -> None:
    commander = AgentCommander()
    decision = commander.decide(make_frame(0.70, 0.05), make_risk(event_tier="A"))
    assert decision["action"] == "SKIP"

