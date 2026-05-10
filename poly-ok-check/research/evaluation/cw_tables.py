"""Coursework table generation utilities.

This module generates aggregate CSV tables and placeholder values used by the
coursework paper. It belongs to the research/evaluation pipeline and is not part
of the live trading runtime.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

import pandas as pd

from research.evaluation.baselines import EVALUATION_METHODS
from research.schemas.domain_report import COMMON_REPORT_FIELDS, DomainReport, reports_to_rows, safe_float


DEFAULT_METHODS = EVALUATION_METHODS


def write_unified_reports(reports: list[DomainReport], path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_REPORT_FIELDS)
        writer.writeheader()
        writer.writerows(reports_to_rows(reports))
    return out


def write_cw_tables(
    reports: list[DomainReport],
    out_dir: Path | str,
    threshold_grid: Iterable[float] = (0.25, 0.50, 0.75, 1.00),
    operating_threshold: float = 0.50,
) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(reports_to_rows(reports))

    paths = {
        "table1": out / "table1_overall.csv",
        "table2": out / "table2_by_domain.csv",
        "table3": out / "table3_threshold.csv",
        "table4": out / "table4_examples.csv",
        "placeholders": out / "paper_placeholders.md",
    }

    _table1(frame).to_csv(paths["table1"], index=False)
    _table2(frame).to_csv(paths["table2"], index=False)
    _table3(frame, threshold_grid).to_csv(paths["table3"], index=False)
    _table4(frame).to_csv(paths["table4"], index=False)
    paths["placeholders"].write_text(_placeholder_markdown(frame, operating_threshold), encoding="utf-8")
    return paths


def _table1(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for method in DEFAULT_METHODS:
        subset = frame[frame.get("method", "") == method] if not frame.empty else frame
        metric = _metrics(subset)
        rows.append({"method": method, **metric})
    observed = sorted(set(frame.get("method", [])) - set(DEFAULT_METHODS)) if not frame.empty else []
    for method in observed:
        rows.append({"method": method, **_metrics(frame[frame["method"] == method])})
    return pd.DataFrame(rows)


def _table2(frame: pd.DataFrame) -> pd.DataFrame:
    proposed = frame[frame.get("method", "") == "proposed_agent"] if not frame.empty else frame
    total_signals = max(int(_metrics(proposed)["signals"]), 1)
    rows = []
    for domain in ["cs2", "btc", "weather"]:
        subset = proposed[proposed.get("domain", "") == domain] if not proposed.empty else proposed
        metric = _metrics(subset)
        rows.append({"domain": domain, **metric, "share": round(metric["signals"] / total_signals, 4)})
    return pd.DataFrame(rows)


def _table3(frame: pd.DataFrame, threshold_grid: Iterable[float]) -> pd.DataFrame:
    proposed = frame[frame.get("method", "") == "proposed_agent"] if not frame.empty else frame
    rows = []
    for threshold in threshold_grid:
        subset = proposed[proposed.apply(lambda row: _opportunity_score(row) >= threshold, axis=1)] if not proposed.empty else proposed
        metric = _metrics(subset, total_count=len(proposed))
        rows.append({"threshold": threshold, **metric})
    return pd.DataFrame(rows)


def _table4(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["case", "domain", "market_id", "market_prob", "model_prob", "edge", "action", "outcome"])
    proposed = frame[frame.get("method", "") == "proposed_agent"].copy()
    proposed = proposed[proposed.apply(_acted, axis=1)]
    rows = []
    for domain in ["cs2", "btc", "weather"]:
        subset = proposed[proposed["domain"] == domain]
        if not subset.empty:
            row = subset.sort_values("edge", ascending=False).iloc[0]
            rows.append(_example_row(f"{domain}_representative", row))
    switch = _switch_or_exit_case(proposed)
    if switch is not None:
        rows.append(_example_row("switch_or_exit_case", switch))
    return pd.DataFrame(rows)


def _metrics(frame: pd.DataFrame, total_count: int | None = None) -> dict:
    total = len(frame) if total_count is None else total_count
    if frame.empty:
        return {"hit_rate": None, "brier": None, "p_l": 0.0, "signals": 0, "coverage": 0.0}
    acted = frame[frame.apply(_acted, axis=1)]
    signals = len(acted)
    known = acted.apply(_selected_result, axis=1)
    known_mask = known.notna()
    hit_rate = float(known[known_mask].mean()) if known_mask.any() else None
    briers = acted.apply(_brier, axis=1).dropna()
    pnl = acted.apply(_pnl, axis=1).sum() if not acted.empty else 0.0
    return {
        "hit_rate": None if hit_rate is None else round(hit_rate, 4),
        "brier": None if briers.empty else round(float(briers.mean()), 6),
        "p_l": round(float(pnl), 6),
        "signals": int(signals),
        "coverage": 0.0 if total == 0 else round(signals / total, 4),
    }


def _acted(row: pd.Series) -> bool:
    return str(row.get("action", "")).upper() in {"YES", "NO"}


def _selected_result(row: pd.Series) -> float | None:
    outcome = str(row.get("outcome", "")).strip().upper()
    if outcome == "WIN":
        return 1.0
    if outcome == "LOSE":
        return 0.0
    if outcome in {"1", "1.0", "TRUE", "YES"}:
        return 1.0
    if outcome in {"0", "0.0", "FALSE", "NO"}:
        return 0.0
    return None


def _brier(row: pd.Series) -> float | None:
    result = _selected_result(row)
    if result is None:
        return None
    model_prob = safe_float(row.get("model_prob"), 0.5)
    return (model_prob - result) ** 2


def _pnl(row: pd.Series) -> float:
    provided = _optional_float(row.get("pnl"))
    if provided is not None:
        return provided
    result = _selected_result(row)
    if result is None:
        return 0.0
    entry = max(min(safe_float(row.get("market_prob"), 0.5), 0.999), 0.001)
    return (1.0 / entry - 1.0) if result >= 0.5 else -1.0


def _opportunity_score(row: pd.Series) -> float:
    return safe_float(row.get("data_score")) + safe_float(row.get("news_score")) + safe_float(row.get("edge"))


def _example_row(case: str, row: pd.Series) -> dict:
    return {
        "case": case,
        "domain": row.get("domain", ""),
        "market_id": row.get("market_id", ""),
        "market_prob": row.get("market_prob", ""),
        "model_prob": row.get("model_prob", ""),
        "edge": row.get("edge", ""),
        "action": row.get("action", ""),
        "outcome": row.get("outcome", ""),
    }


def _switch_or_exit_case(frame: pd.DataFrame) -> pd.Series | None:
    if frame.empty or "timestamp" not in frame:
        return None
    ordered = frame.sort_values("timestamp")
    previous_domain = None
    for _, row in ordered.iterrows():
        domain = row.get("domain")
        if previous_domain is not None and domain != previous_domain:
            return row
        previous_domain = domain
    return None


def _placeholder_markdown(frame: pd.DataFrame, operating_threshold: float) -> str:
    proposed = frame[frame.get("method", "") == "proposed_agent"] if not frame.empty else frame
    overall = _metrics(proposed)
    switches = _count_switches(proposed)
    exits = _count_exits(proposed)
    table1 = _table1(frame)
    table2 = _table2(frame)
    table3 = _table3(frame, [0.25, 0.50, 0.75, 1.00])
    table4 = _table4(frame)
    lines = [
        "# Paper placeholders",
        "",
        "Use the CSV tables in this directory as the source of truth.",
        "",
        "## Overall proposed values",
        "",
        f"- proposed_selected: {overall['signals']}",
        f"- available_decision_windows: {len(proposed)}",
        f"- proposed_coverage_pct: {overall['coverage'] * 100:.2f}",
        f"- proposed_hit_rate_pct: {_pct(overall['hit_rate'])}",
        f"- proposed_brier: {_value(overall['brier'])}",
        f"- proposed_p_l: {_value(overall['p_l'])}",
        f"- domain_switches: {switches}",
        f"- exits: {exits}",
        f"- operating_threshold: {operating_threshold}",
        "",
        "## Table I overall by method",
        "",
    ]
    lines.extend(_metric_bullets(table1, "method"))
    lines.extend(["", "## Table II proposed by domain", ""])
    lines.extend(_metric_bullets(table2, "domain", include_share=True))
    lines.extend(["", "## Table III threshold sensitivity", ""])
    lines.extend(_metric_bullets(table3, "threshold"))
    lines.extend(["", "## Table IV example rows", ""])
    for _, row in table4.iterrows():
        lines.append(
            "- "
            f"{row.get('case')}: domain={row.get('domain')}, action={row.get('action')}, "
            f"market_prob={_value(row.get('market_prob'))}, model_prob={_value(row.get('model_prob'))}, "
            f"edge={_value(row.get('edge'))}, outcome={row.get('outcome')}"
        )
    lines.append("")
    return "\n".join(lines)


def _count_switches(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    acted = frame[frame.apply(_acted, axis=1)].sort_values("timestamp")
    last = None
    count = 0
    for domain in acted.get("domain", []):
        if last is not None and domain != last:
            count += 1
        last = domain
    return count


def _count_exits(frame: pd.DataFrame) -> int:
    if frame.empty:
        return 0
    return int((frame.get("action", pd.Series(dtype=str)).astype(str).str.upper() == "FLAT").sum())


def _metric_bullets(frame: pd.DataFrame, label_col: str, include_share: bool = False) -> list[str]:
    lines: list[str] = []
    for _, row in frame.iterrows():
        parts = [
            f"{label_col}={row.get(label_col)}",
            f"signals={int(safe_float(row.get('signals'), 0.0))}",
            f"coverage_pct={_pct(row.get('coverage'))}",
            f"hit_rate_pct={_pct(row.get('hit_rate'))}",
            f"brier={_value(row.get('brier'))}",
            f"p_l={_value(row.get('p_l'))}",
        ]
        if include_share:
            parts.append(f"share_pct={_pct(row.get('share'))}")
        lines.append("- " + ", ".join(parts))
    return lines


def _pct(value: object) -> str:
    numeric = _optional_float(value)
    return "" if numeric is None else f"{numeric * 100:.2f}"


def _value(value: object) -> str:
    numeric = _optional_float(value)
    if numeric is None:
        return ""
    return f"{numeric:.6f}".rstrip("0").rstrip(".")


def _optional_float(value: object) -> float | None:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None
