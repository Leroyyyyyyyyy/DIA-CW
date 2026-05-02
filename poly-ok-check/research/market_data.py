from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import pandas as pd

from research.utils.time_utils import safe_float


CANONICAL_COLUMNS = [
    "timestamp_s",
    "market_id",
    "token_id",
    "best_bid",
    "best_ask",
    "orderbook_mid",
    "spread",
    "depth_usd",
    "bids",
    "asks",
    "source",
    "quality_stale",
    "quality_partial",
    "metadata",
]


def parse_order_levels(value: object, side: str) -> list[dict[str, float]]:
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []

    levels: list[dict[str, float]] = []
    raw_levels = value if isinstance(value, list) else []
    for raw in raw_levels:
        price: float
        size: float
        if isinstance(raw, str):
            if "@" not in raw:
                continue
            raw_price, raw_size = raw.split("@", 1)
            price = safe_float(raw_price, default=-1.0)
            size = safe_float(raw_size, default=-1.0)
        elif isinstance(raw, dict):
            price = safe_float(raw.get("price"), default=-1.0)
            size = safe_float(raw.get("size"), default=-1.0)
        else:
            continue
        if price <= 0.0 or size <= 0.0:
            continue
        levels.append({"price": float(price), "size": float(size)})

    reverse = side.lower() == "bid"
    return sorted(levels, key=lambda item: item["price"], reverse=reverse)


def normalize_market_frames(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=CANONICAL_COLUMNS)

    rows: list[dict] = []
    for _, raw in df.iterrows():
        row = raw.to_dict()
        timestamp_s = _coerce_timestamp_s(row)
        bids = parse_order_levels(row.get("bids"), side="bid")
        asks = parse_order_levels(row.get("asks"), side="ask")

        best_bid = _best_bid(row, bids)
        best_ask = _best_ask(row, asks)
        midpoint = safe_float(row.get("orderbook_mid", row.get("midpoint")), default=0.0)
        if midpoint <= 0.0 and best_bid > 0.0 and best_ask > 0.0:
            midpoint = (best_bid + best_ask) / 2.0

        spread = safe_float(row.get("spread"), default=0.0)
        if spread <= 0.0 and best_bid > 0.0 and best_ask > 0.0:
            spread = max(best_ask - best_bid, 0.0)

        depth_usd = safe_float(row.get("depth_usd"), default=-1.0)
        if depth_usd < 0.0:
            depth_usd = _depth_usd(bids) + _depth_usd(asks)

        market_id = _string_or_none(row.get("market_id")) or _string_or_none(row.get("market")) or _string_or_none(row.get("asset_id"))
        token_id = _string_or_none(row.get("token_id")) or _string_or_none(row.get("asset_id")) or market_id

        rows.append(
            {
                "timestamp_s": timestamp_s,
                "market_id": market_id or "",
                "token_id": token_id or "",
                "best_bid": best_bid,
                "best_ask": best_ask,
                "orderbook_mid": midpoint,
                "spread": spread,
                "depth_usd": max(depth_usd, 0.0),
                "bids": bids,
                "asks": asks,
                "source": _string_or_none(row.get("source")) or "unknown",
                "quality_stale": bool(row.get("quality_stale", False)),
                "quality_partial": bool(row.get("quality_partial", False)),
                "metadata": row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
            }
        )

    out = pd.DataFrame(rows, columns=CANONICAL_COLUMNS)
    out = out[pd.notna(out["timestamp_s"])].copy()
    out["quality_stale"] = out["quality_stale"].astype(object)
    out["quality_partial"] = out["quality_partial"].astype(object)
    return out.sort_values("timestamp_s").reset_index(drop=True)


def load_hub_archive_market_frames(paths: list[Path], market_id: str | None = None) -> pd.DataFrame:
    rows: list[dict] = []
    for path in paths:
        for record in _read_jsonl_records(Path(path)):
            hub_ts = record.get("hub_ts")
            timestamp_s = _parse_iso_timestamp_s(hub_ts)
            markets = record.get("markets") or {}
            for snapshot_id, snapshot in markets.items():
                snapshot_market_id = str(snapshot.get("market_id") or snapshot_id)
                if market_id is not None and snapshot_market_id != market_id:
                    continue
                book = snapshot.get("book_ticker") or {}
                quality = snapshot.get("quality_flags") or {}
                rows.append(
                    {
                        "timestamp_s": timestamp_s,
                        "market_id": snapshot_market_id,
                        "token_id": snapshot_market_id,
                        "best_bid": book.get("best_bid"),
                        "best_ask": book.get("best_ask"),
                        "orderbook_mid": book.get("midpoint"),
                        "spread": book.get("spread"),
                        "bids": book.get("bids") or [],
                        "asks": book.get("asks") or [],
                        "source": "hub_archive",
                        "quality_stale": bool(quality.get("stale", False)),
                        "quality_partial": bool(quality.get("partial", False)),
                    }
                )
    return normalize_market_frames(pd.DataFrame(rows))


def load_ws_dump_market_frames(paths: list[Path], token_id: str | None = None) -> pd.DataFrame:
    rows: list[dict] = []
    for path in paths:
        for record in _read_jsonl_records(Path(path)):
            record_type = record.get("type")
            if record_type in {"startup", "bootstrap_error"}:
                continue
            asset_id = _string_or_none(record.get("asset_id"))
            if asset_id is None:
                continue
            if token_id is not None and asset_id != token_id:
                continue
            rows.append(
                {
                    "timestamp_s": _coerce_timestamp_s(record),
                    "market_id": _string_or_none(record.get("market")) or asset_id,
                    "token_id": asset_id,
                    "bids": record.get("bids") or [],
                    "asks": record.get("asks") or [],
                    "source": "ws_dump",
                    "quality_stale": False,
                    "quality_partial": False,
                }
            )
    return normalize_market_frames(pd.DataFrame(rows))


def _read_jsonl_records(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _coerce_timestamp_s(row: dict) -> float:
    if "timestamp_s" in row:
        return safe_float(row.get("timestamp_s"), default=float("nan"))
    if "received_ms" in row:
        return safe_float(row.get("received_ms"), default=float("nan")) / 1000.0
    if "exchange_ts" in row:
        raw = safe_float(row.get("exchange_ts"), default=float("nan"))
        return raw / 1000.0 if raw > 10_000_000_000 else raw
    if "hub_ts" in row:
        return _parse_iso_timestamp_s(row.get("hub_ts"))
    return float("nan")


def _parse_iso_timestamp_s(value: object) -> float:
    if value is None:
        return float("nan")
    return float(pd.Timestamp(str(value)).timestamp())


def _best_bid(row: dict, bids: list[dict[str, float]]) -> float:
    value = safe_float(row.get("best_bid"), default=0.0)
    if value > 0.0:
        return value
    return bids[0]["price"] if bids else 0.0


def _best_ask(row: dict, asks: list[dict[str, float]]) -> float:
    value = safe_float(row.get("best_ask"), default=0.0)
    if value > 0.0:
        return value
    return asks[0]["price"] if asks else 0.0


def _depth_usd(levels: list[dict[str, float]]) -> float:
    return float(sum(level["price"] * level["size"] for level in levels))


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value)
    return text if text else None
