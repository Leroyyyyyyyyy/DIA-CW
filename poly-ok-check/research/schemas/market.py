from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd


@dataclass(slots=True)
class MarketSnapshotFrame:
    timestamp_s: float
    market_id: str
    token_id: str
    best_bid: float
    best_ask: float
    orderbook_mid: float
    spread: float
    depth_usd: float
    bids: list[dict[str, float]]
    asks: list[dict[str, float]]
    source: str
    quality_stale: bool = False
    quality_partial: bool = False
    metadata: dict = field(default_factory=dict)

    @classmethod
    def from_series(cls, row: pd.Series) -> "MarketSnapshotFrame":
        return cls(
            timestamp_s=float(row["timestamp_s"]),
            market_id=str(row.get("market_id") or ""),
            token_id=str(row.get("token_id") or row.get("market_id") or ""),
            best_bid=float(row.get("best_bid") or 0.0),
            best_ask=float(row.get("best_ask") or 0.0),
            orderbook_mid=float(row.get("orderbook_mid") or 0.0),
            spread=float(row.get("spread") or 0.0),
            depth_usd=float(row.get("depth_usd") or 0.0),
            bids=list(row.get("bids") or []),
            asks=list(row.get("asks") or []),
            source=str(row.get("source") or "unknown"),
            quality_stale=bool(row.get("quality_stale", False)),
            quality_partial=bool(row.get("quality_partial", False)),
            metadata=dict(row.get("metadata") or {}),
        )

    def to_dict(self) -> dict:
        return asdict(self)
