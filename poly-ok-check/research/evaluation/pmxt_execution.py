from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from research.schemas.domain_report import DomainReport, normalize_action


PMXT_DIAGNOSTIC_FIELDS = [
    "artifact",
    "status",
    "domain",
    "timestamp",
    "market_id",
    "action",
    "pnl",
    "reason",
]


def apply_pmxt_execution(
    reports: list[DomainReport],
    pmxt_config: dict[str, Any] | None,
    base_dir: Path | None = None,
    config_dir: Path | None = None,
) -> tuple[list[DomainReport], list[dict[str, Any]]]:
    if not pmxt_config or not pmxt_config.get("enabled", False):
        return list(reports), []

    base = base_dir or Path.cwd()
    config_base = config_dir or base
    diagnostics: list[dict[str, Any]] = []
    executions = _load_execution_rows(pmxt_config, base, config_base, diagnostics)

    if not executions:
        if pmxt_config.get("required", False):
            raise FileNotFoundError("PMXT execution is required, but no execution rows were loaded")
        diagnostics.append(_diagnostic(status="no_execution_rows", reason="pmxt_optional_noop"))
        return list(reports), diagnostics

    by_key = _execution_index(executions)
    used: set[int] = set()
    strict = bool(pmxt_config.get("strict_execution_set", False))
    replace_action = bool(pmxt_config.get("replace_action_with_execution", True))

    adjusted: list[DomainReport] = []
    for report in reports:
        if report.method != "proposed_agent":
            adjusted.append(report)
            continue

        match_id = _match_execution(report, by_key, used)
        if match_id is None:
            if strict and normalize_action(report.action) in {"YES", "NO"}:
                adjusted.append(_blocked_report(report))
                diagnostics.append(
                    _diagnostic(
                        status="unmatched_report",
                        domain=report.domain,
                        timestamp=report.timestamp,
                        market_id=report.market_id,
                        action=report.action,
                        reason="pmxt_no_execution_match",
                    )
                )
            else:
                adjusted.append(report)
            continue

        used.add(match_id)
        execution = executions[match_id]
        adjusted.append(_merge_execution(report, execution, replace_action=replace_action))
        diagnostics.append(
            _diagnostic(
                artifact=execution.get("artifact", ""),
                status="matched",
                domain=report.domain,
                timestamp=report.timestamp,
                market_id=report.market_id,
                action=execution.get("action", report.action),
                pnl=execution.get("pnl"),
                reason="pmxt_execution_matched",
            )
        )

    for index, execution in enumerate(executions):
        if index not in used:
            diagnostics.append(
                _diagnostic(
                    artifact=execution.get("artifact", ""),
                    status="unused_execution",
                    domain=execution.get("domain", ""),
                    timestamp=execution.get("timestamp", ""),
                    market_id=execution.get("market_id", ""),
                    action=execution.get("action", ""),
                    pnl=execution.get("pnl"),
                    reason="pmxt_execution_not_matched_to_report",
                )
            )

    return adjusted, diagnostics


def write_pmxt_execution_diagnostics(rows: list[dict[str, Any]], path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=PMXT_DIAGNOSTIC_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in PMXT_DIAGNOSTIC_FIELDS} for row in rows)
    return out


def _load_execution_rows(
    config: dict[str, Any],
    base_dir: Path,
    config_dir: Path,
    diagnostics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact in list(config.get("artifacts", [])):
        paths = _resolve_artifact_paths(artifact, base_dir, config_dir)
        if not paths:
            diagnostics.append(
                _diagnostic(
                    artifact=str(artifact.get("path") or artifact.get("glob") or ""),
                    status="missing",
                    reason="pmxt_artifact_missing",
                )
            )
            continue
        for path in paths:
            loaded = _read_artifact(path, artifact)
            rows.extend(loaded)
            diagnostics.append(
                _diagnostic(
                    artifact=str(path),
                    status="loaded",
                    reason=f"pmxt_rows={len(loaded)}",
                )
            )
    return rows


def _resolve_artifact_paths(artifact: dict[str, Any], base_dir: Path, config_dir: Path) -> list[Path]:
    raw = str(artifact.get("path") or artifact.get("glob") or "").strip()
    if not raw:
        return []
    resolved = _resolve_path(raw, base_dir, config_dir)
    if any(char in str(resolved) for char in "*?[]"):
        parent = resolved.parent
        if not parent.exists():
            return []
        return sorted(path for path in parent.glob(resolved.name) if path.is_file())
    return [resolved] if resolved.exists() else []


def _resolve_path(value: str | Path, base_dir: Path, config_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    from_base = base_dir / path
    if from_base.exists() or any(char in str(from_base) for char in "*?[]"):
        return from_base
    return config_dir / path


def _read_artifact(path: Path, artifact: dict[str, Any]) -> list[dict[str, Any]]:
    fmt = str(artifact.get("format") or path.suffix.lstrip(".")).lower()
    if fmt == "csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [_normalise_execution_row(row, artifact, path) for row in csv.DictReader(handle)]
    if fmt == "jsonl":
        rows = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if text:
                    rows.append(_normalise_execution_row(json.loads(text), artifact, path))
        return rows
    if fmt == "json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            payload = payload.get("fills") or payload.get("trades") or payload.get("executions") or []
        if not isinstance(payload, list):
            raise ValueError(f"{path} must contain a JSON list or an object with fills/trades/executions")
        return [_normalise_execution_row(row, artifact, path) for row in payload if isinstance(row, dict)]
    return []


def _normalise_execution_row(row: dict[str, Any], artifact: dict[str, Any], path: Path) -> dict[str, Any]:
    market_id = _clean(
        row.get("market_id")
        or row.get("market_slug")
        or row.get("instrument_id")
        or row.get("symbol")
        or artifact.get("market_id")
        or artifact.get("market_slug")
    )
    action = normalize_action(
        row.get("action")
        or row.get("side")
        or row.get("position_side")
        or row.get("order_side")
        or row.get("token_side")
    )
    domain = _clean(row.get("domain") or artifact.get("domain") or _infer_domain(market_id))
    timestamp = _clean(
        row.get("timestamp")
        or row.get("timestamp_utc")
        or row.get("time")
        or row.get("filled_at")
        or row.get("created_at")
    )
    pnl = _optional_float(
        row.get("pnl")
        or row.get("p_l")
        or row.get("realized_pnl")
        or row.get("realised_pnl")
        or row.get("profit_loss")
    )
    return {
        "artifact": str(path),
        "domain": domain,
        "timestamp": timestamp,
        "market_id": market_id,
        "action": action,
        "outcome": _clean(row.get("outcome") or row.get("result")),
        "pnl": pnl,
        "fill_price": _optional_float(row.get("fill_price") or row.get("price") or row.get("avg_price")),
        "quantity": _optional_float(row.get("quantity") or row.get("qty") or row.get("size")),
        "raw_execution": dict(row),
    }


def _execution_index(executions: list[dict[str, Any]]) -> dict[tuple[str, ...], list[int]]:
    index: dict[tuple[str, ...], list[int]] = {}
    for row_id, execution in enumerate(executions):
        for key in _execution_keys(execution):
            index.setdefault(key, []).append(row_id)
    return index


def _execution_keys(execution: dict[str, Any]) -> list[tuple[str, ...]]:
    domain = _clean(execution.get("domain")).lower()
    market = _clean(execution.get("market_id"))
    action = normalize_action(execution.get("action"))
    timestamp = _clean(execution.get("timestamp"))
    keys = []
    if domain and market and action and timestamp:
        keys.append((domain, market, action, timestamp))
    if domain and market and action:
        keys.append((domain, market, action))
    if market and action:
        keys.append((market, action))
    if domain and market:
        keys.append((domain, market))
    if market:
        keys.append((market,))
    return keys


def _match_execution(report: DomainReport, index: dict[tuple[str, ...], list[int]], used: set[int]) -> int | None:
    candidates = [
        (report.domain.lower(), report.market_id, normalize_action(report.action), _clean(report.timestamp)),
        (report.domain.lower(), report.market_id, normalize_action(report.action)),
        (report.market_id, normalize_action(report.action)),
        (report.domain.lower(), report.market_id),
        (report.market_id,),
    ]
    for key in candidates:
        for row_id in index.get(key, []):
            if row_id not in used:
                return row_id
    return None


def _merge_execution(report: DomainReport, execution: dict[str, Any], replace_action: bool) -> DomainReport:
    metadata = dict(report.metadata)
    metadata.update(
        {
            "pmxt_execution_matched": True,
            "pmxt_artifact": execution.get("artifact", ""),
            "pmxt_fill_price": execution.get("fill_price"),
            "pmxt_quantity": execution.get("quantity"),
            "pmxt_raw_execution": execution.get("raw_execution", {}),
        }
    )
    action = normalize_action(execution.get("action")) if replace_action else normalize_action(report.action)
    if action not in {"YES", "NO", "FLAT", "HOLD"}:
        action = normalize_action(report.action)
    return replace(
        report,
        action=action,
        outcome=_clean(execution.get("outcome")) or report.outcome,
        pnl=execution.get("pnl") if execution.get("pnl") is not None else report.pnl,
        metadata=metadata,
    )


def _blocked_report(report: DomainReport) -> DomainReport:
    metadata = dict(report.metadata)
    metadata.update({"pmxt_execution_matched": False, "pmxt_reason": "pmxt_no_execution_match"})
    return replace(report, action="HOLD", outcome="", pnl=None, metadata=metadata)


def _diagnostic(
    artifact: str = "",
    status: str = "",
    domain: str = "",
    timestamp: str = "",
    market_id: str = "",
    action: Any = "",
    pnl: Any = "",
    reason: str = "",
) -> dict[str, Any]:
    return {
        "artifact": artifact,
        "status": status,
        "domain": domain,
        "timestamp": timestamp,
        "market_id": market_id,
        "action": normalize_action(action),
        "pnl": "" if pnl is None else pnl,
        "reason": reason,
    }


def _infer_domain(market_id: str) -> str:
    text = market_id.lower()
    if text.startswith("btc") or "bitcoin" in text:
        return "btc"
    if text.startswith("cs2") or "counter-strike" in text:
        return "cs2"
    if "temperature" in text or "weather" in text:
        return "weather"
    return ""


def _optional_float(value: Any) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clean(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if not text or text.lower() in {"nan", "none"} else text
