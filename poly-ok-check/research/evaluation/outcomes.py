from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

from research.schemas.domain_report import normalize_action, safe_float


def selected_side_outcome(action: Any, yes_outcome: Any) -> str:
    side = normalize_action(action)
    if side not in {"YES", "NO"} or yes_outcome is None:
        return ""
    yes_won = safe_float(yes_outcome) >= 0.5
    selected_won = yes_won if side == "YES" else not yes_won
    return "WIN" if selected_won else "LOSE"


def load_yes_outcomes_csv(path: Path | str | None) -> dict[str, float]:
    if path is None:
        return {}
    outcome_path = Path(path)
    if not outcome_path.exists():
        raise FileNotFoundError(f"Configured outcome CSV does not exist: {outcome_path}")

    outcomes: dict[str, float] = {}
    with outcome_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            market_id = str(row.get("market_id") or "").strip()
            if not market_id:
                continue
            yes_value = _yes_outcome_from_row(row)
            if yes_value is not None:
                outcomes[market_id] = yes_value
    return outcomes


def weather_yes_outcome(market_label: Any, actual_label: Any) -> float | None:
    actual = normalize_weather_label(actual_label)
    market = normalize_weather_label(market_label)
    if not actual or not market:
        return None
    return 1.0 if market == actual else 0.0


def normalize_weather_label(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text or text == "nan":
        return ""
    text = (
        text.replace("掳", "°")
        .replace("℃", "°c")
        .replace("degrees", "°")
        .replace("degree", "°")
        .replace("deg", "°")
    )
    text = re.sub(r"\s+", "", text)
    text = text.replace("°c", "").replace("°", "").replace("c", "")
    return re.sub(r"[^a-z0-9.+-]+", "", text)


def _yes_outcome_from_row(row: dict[str, Any]) -> float | None:
    raw = str(row.get("yes_outcome") or "").strip()
    if raw:
        return 1.0 if safe_float(raw) >= 0.5 else 0.0
    winning_side = str(row.get("winning_side") or "").strip().upper()
    if winning_side == "YES":
        return 1.0
    if winning_side == "NO":
        return 0.0
    return None
