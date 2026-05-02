from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


COMMON_REPORT_FIELDS = [
    "method",
    "domain",
    "timestamp",
    "market_id",
    "target",
    "market_prob",
    "model_prob",
    "data_score",
    "news_score",
    "edge",
    "action",
    "outcome",
    "evidence_ref",
    "pnl",
    "metadata",
]


@dataclass(slots=True)
class DomainReport:
    domain: str
    timestamp: str
    market_id: str
    target: str
    market_prob: float
    model_prob: float
    data_score: float
    news_score: float
    edge: float
    action: str
    outcome: str = ""
    evidence_ref: str = ""
    method: str = "proposed_agent"
    pnl: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["metadata"] = json.dumps(self.metadata, ensure_ascii=False, sort_keys=True)
        row["pnl"] = "" if self.pnl is None else self.pnl
        return {field: row.get(field, "") for field in COMMON_REPORT_FIELDS}


def reports_to_rows(reports: list[DomainReport]) -> list[dict[str, Any]]:
    return [report.to_row() for report in reports]


def parse_json_cell(value: Any, default: Any = None) -> Any:
    if default is None:
        default = {}
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none"}:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def normalize_action(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"BUY_YES", "LONG_YES", "YES", "ENTER_YES"}:
        return "YES"
    if text in {"BUY_NO", "LONG_NO", "NO", "ENTER_NO"}:
        return "NO"
    if text in {"EXIT", "FLAT", "SELL", "CLOSE"}:
        return "FLAT"
    if text in {"NO_TRADE", "HOLD", ""}:
        return "HOLD"
    return text


def infer_action(model_prob: float, market_prob: float, threshold: float = 0.0) -> str:
    diff = model_prob - market_prob
    if abs(diff) <= threshold:
        return "HOLD"
    return "YES" if diff > 0.0 else "NO"

