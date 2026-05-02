from __future__ import annotations

from research.schemas.market_frame import AlignedMarketFrame
from research.schemas.risk_context import RiskContext


def is_s_tier_event(risk: RiskContext) -> bool:
    return risk.event_tier.upper() == "S"


def should_skip_for_depth(frame: AlignedMarketFrame, min_depth_usd: float) -> bool:
    return frame.depth_usd < min_depth_usd


def should_force_exit(frame: AlignedMarketFrame, risk: RiskContext) -> bool:
    side = (risk.current_position_side or "").upper()
    if side == "YES" and frame.fair_win_prob <= 0.10:
        return True
    if side == "NO" and frame.fair_win_prob >= 0.90:
        return True
    return False


def should_hold_trend(frame: AlignedMarketFrame, risk: RiskContext) -> bool:
    side = (risk.current_position_side or "").upper()
    if side == "YES" and frame.fair_win_prob >= 0.90:
        return True
    if side == "NO" and frame.fair_win_prob <= 0.10:
        return True
    return False

