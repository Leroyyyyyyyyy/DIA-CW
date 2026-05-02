from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

import pandas as pd

from research.utils.time_utils import safe_float


class OutcomeStore:
    def __init__(self, payouts: Mapping[str, float] | None = None):
        self.payouts = {str(key): _normalize_payout(value) for key, value in (payouts or {}).items()}

    @classmethod
    def from_any(cls, value: "OutcomeStore | Mapping | Path | str | None") -> "OutcomeStore | None":
        if value is None:
            return None
        if isinstance(value, OutcomeStore):
            return value
        if isinstance(value, (str, Path)):
            return cls.from_path(Path(value))
        if isinstance(value, Mapping):
            return cls(_mapping_to_payouts(value))
        raise TypeError(f"Unsupported outcome input: {type(value)!r}")

    @classmethod
    def from_path(cls, path: Path) -> "OutcomeStore":
        if path.suffix.lower() == ".csv":
            frame = pd.read_csv(path)
            return cls(_records_to_payouts(frame.to_dict(orient="records")))
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, list):
            return cls(_records_to_payouts(raw))
        if isinstance(raw, dict):
            return cls(_mapping_to_payouts(raw))
        raise ValueError(f"Unsupported outcome file shape: {path}")

    def get_payout(self, market_id: str, token_id: str, side: str | None = None) -> float | None:
        keys = [token_id, market_id]
        if side:
            keys.insert(0, f"{market_id}:{side.upper()}")
            keys.insert(0, f"{token_id}:{side.upper()}")
        for key in keys:
            if key in self.payouts:
                return self.payouts[key]
        return None


def _mapping_to_payouts(value: Mapping) -> dict[str, float]:
    if "payout" in value and ("token_id" in value or "market_id" in value):
        key = str(value.get("token_id") or value.get("market_id"))
        return {key: _normalize_payout(value["payout"])}
    return {str(key): _normalize_payout(payout) for key, payout in value.items()}


def _records_to_payouts(records: list[dict]) -> dict[str, float]:
    payouts: dict[str, float] = {}
    for record in records:
        key = record.get("token_id") or record.get("market_id")
        if key is None:
            raise ValueError("Outcome row missing token_id or market_id")
        side = record.get("side")
        out_key = f"{key}:{str(side).upper()}" if side else str(key)
        payouts[out_key] = _normalize_payout(record.get("payout"))
    return payouts


def _normalize_payout(value: object) -> float:
    payout = safe_float(value, default=float("nan"))
    if payout not in {0.0, 1.0}:
        raise ValueError(f"Outcome payout must be 0 or 1, got {value!r}")
    return payout
