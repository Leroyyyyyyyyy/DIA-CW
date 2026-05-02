from __future__ import annotations

from research.schemas.execution import TargetPosition
from research.schemas.market_frame import AlignedMarketFrame
from research.schemas.risk_context import RiskContext
from research.strategy.rules import is_s_tier_event, should_force_exit, should_hold_trend, should_skip_for_depth


class AgentCommander:
    def __init__(
        self,
        entry_threshold: float = 0.03,
        min_depth_usd: float = 500.0,
        default_notional_usd: float = 100.0,
    ):
        self.entry_threshold = entry_threshold
        self.min_depth_usd = min_depth_usd
        self.default_notional_usd = default_notional_usd

    def decide(self, frame: AlignedMarketFrame, risk: RiskContext) -> dict:
        if frame.is_stale_snapshot:
            return {"action": "SKIP", "reason": "stale_snapshot"}
        if should_skip_for_depth(frame, self.min_depth_usd):
            return {"action": "SKIP", "reason": "low_depth"}
        if not risk.allow_new_entry and risk.current_position_side is None:
            return {"action": "SKIP", "reason": "risk_blocks_entry"}

        if should_force_exit(frame, risk):
            return {"action": "EXIT", "reason": "forced_exit_probability"}
        if should_hold_trend(frame, risk):
            return {"action": "HOLD", "reason": "trend_hold_probability"}

        if risk.reduce_only:
            return {"action": "SKIP", "reason": "reduce_only"}
        if risk.current_position_side is not None:
            return {"action": "SKIP", "reason": "position_open_no_signal"}
        if not is_s_tier_event(risk):
            return {"action": "SKIP", "reason": "non_s_tier_event"}
        if frame.edge_net <= self.entry_threshold:
            return {"action": "SKIP", "reason": "edge_below_threshold"}

        action = "ENTER_YES" if frame.fair_win_prob >= 0.5 else "ENTER_NO"
        return {"action": action, "reason": "positive_executable_edge"}

    def target_position(
        self,
        frame: AlignedMarketFrame,
        risk: RiskContext,
        market_id: str,
        token_id: str,
        decision: dict | None = None,
    ) -> TargetPosition | None:
        decision = decision or self.decide(frame, risk)
        action = decision["action"]
        reason = decision.get("reason", "")
        if action == "ENTER_YES":
            return TargetPosition(market_id=market_id, token_id=token_id, side="YES", target_notional_usd=self.default_notional_usd, reason=reason)
        if action == "ENTER_NO":
            return TargetPosition(market_id=market_id, token_id=token_id, side="NO", target_notional_usd=self.default_notional_usd, reason=reason)
        if action == "EXIT":
            return TargetPosition(market_id=market_id, token_id=token_id, side="FLAT", target_notional_usd=0.0, reason=reason)
        return None
