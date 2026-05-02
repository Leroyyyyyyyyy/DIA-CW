from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class RiskContext:
    equity: float
    cash: float
    current_position_side: Optional[str]
    current_position_size: float
    drawdown: float
    event_tier: str
    allow_new_entry: bool
    reduce_only: bool
