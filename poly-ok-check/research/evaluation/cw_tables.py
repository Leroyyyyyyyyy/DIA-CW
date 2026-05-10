"""Coursework table generation utilities.

This module generates aggregate CSV tables and placeholder values used by the
coursework paper. It belongs to the research/evaluation pipeline and is not part
of the live trading runtime.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path
from typing import Iterable

import pandas as pd

from research.evaluation.baselines import EVALUATION_METHODS
from research.schemas.domain_report import COMMON_REPORT_FIELDS, DomainReport, reports_to_rows, safe_float


DEFAULT_METHODS = EVALUATION_METHODS
DOMAINS = ("cs2", "btc", "weather")
SCORE_COMPONENTS = ("data_score", "news_score", "edge")
ACTION_TRACE_FIELDS = [
    "timestamp",
    "cs2_score",
    "btc_score",
    "weather_score",
    "selected_domain",
    "previous_domain",
    "action_type",
    "reason",
    "selected_market_id",
    "selected_action",
    "selected_score",
]


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
    raw_frame = pd.DataFrame(reports_to_rows(reports))
    thresholds = list(threshold_grid)
    calibration, calibration_diagnostics = _score_calibration(raw_frame)
    frame = _with_opportunity_scores(raw_frame, calibration)
    trace = _action_trace(frame, operating_threshold)
    trace_counts = _trace_counts(trace)

    paths = {
        "table1": out / "table1_overall.csv",
        "table2": out / "table2_by_domain.csv",
        "table3": out / "table3_threshold.csv",
        "table4": out / "table4_examples.csv",
        "calibration": out / "score_calibration_diagnostics.csv",
        "action_trace": out / "action_trace.csv",
        "action_counts": out / "action_counts.json",
        "placeholders": out / "paper_placeholders.md",
    }

    _table1(frame, operating_threshold).to_csv(paths["table1"], index=False)
    _table2(frame, operating_threshold).to_csv(paths["table2"], index=False)
    _table3(frame, thresholds).to_csv(paths["table3"], index=False)
    _table4(frame, operating_threshold, trace).to_csv(paths["table4"], index=False)
    calibration_diagnostics.to_csv(paths["calibration"], index=False)
    trace.to_csv(paths["action_trace"], index=False)
    paths["action_counts"].write_text(json.dumps(trace_counts, indent=2, sort_keys=True), encoding="utf-8")
    paths["placeholders"].write_text(
        _placeholder_markdown(frame, operating_threshold, trace_counts, thresholds),
        encoding="utf-8",
    )
    return paths


def _table1(frame: pd.DataFrame, operating_threshold: float) -> pd.DataFrame:
    rows = []
    for method in DEFAULT_METHODS:
        subset = _method_frame(frame, method)
        if method == "proposed_agent":
            metric = _metrics(_thresholded_proposed_frame(subset, operating_threshold))
        else:
            metric = _metrics(subset)
        rows.append({"method": method, **metric})
    observed = sorted(set(frame.get("method", [])) - set(DEFAULT_METHODS)) if not frame.empty else []
    for method in observed:
        rows.append({"method": method, **_metrics(_method_frame(frame, method))})
    return pd.DataFrame(rows)


def _table2(frame: pd.DataFrame, operating_threshold: float) -> pd.DataFrame:
    proposed = _method_frame(frame, "proposed_agent")
    thresholded = _thresholded_proposed_frame(proposed, operating_threshold)
    total_signals = max(int(_metrics(thresholded)["signals"]), 1)
    rows = []
    for domain in DOMAINS:
        subset = _domain_frame(thresholded, domain) if not thresholded.empty else thresholded
        metric = _metrics(subset)
        rows.append({"domain": domain, **metric, "share": round(metric["signals"] / total_signals, 4)})
    return pd.DataFrame(rows)


def _table3(frame: pd.DataFrame, threshold_grid: Iterable[float]) -> pd.DataFrame:
    proposed = _method_frame(frame, "proposed_agent")
    rows = []
    for threshold in threshold_grid:
        thresholded = _thresholded_proposed_frame(proposed, threshold)
        metric = _metrics(thresholded, total_count=len(proposed))
        rows.append({"threshold": threshold, **metric})
    return pd.DataFrame(rows)


def _table4(frame: pd.DataFrame, operating_threshold: float, trace: pd.DataFrame) -> pd.DataFrame:
    columns = ["case", "domain", "market_id", "market_prob", "model_prob", "edge", "score", "action", "outcome"]
    if frame.empty:
        return pd.DataFrame(columns=columns)
    proposed = _thresholded_proposed_frame(_method_frame(frame, "proposed_agent"), operating_threshold)
    acted = proposed[proposed.apply(_acted, axis=1)].copy()
    rows = []
    for domain in DOMAINS:
        subset = _domain_frame(acted, domain)
        if not subset.empty:
            row = subset.sort_values(["score", "edge"], ascending=False).iloc[0]
            rows.append(_example_row(f"{domain}_representative", row))
    switch = _switch_or_exit_case(acted, trace)
    if switch is not None:
        rows.append(_example_row("switch_or_exit_case", switch))
    return pd.DataFrame(rows, columns=columns)


def _metrics(frame: pd.DataFrame, total_count: int | None = None) -> dict:
    total = len(frame) if total_count is None else total_count
    if frame.empty:
        return {
            "hit_rate": None,
            "brier": None,
            "p_l": 0.0,
            "signals": 0,
            "coverage": 0.0,
            "return_per_signal": 0.0,
        }
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
        "return_per_signal": 0.0 if signals == 0 else round(float(pnl) / signals, 6),
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


def _score_calibration(frame: pd.DataFrame) -> tuple[dict[tuple[str, str], float], pd.DataFrame]:
    proposed = _method_frame(frame, "proposed_agent")
    observed = {_clean_text(value).lower() for value in proposed.get("domain", []) if _clean_text(value)}
    domains = sorted(observed | set(DOMAINS)) if not proposed.empty else list(DOMAINS)
    calibration: dict[tuple[str, str], float] = {}
    diagnostics = []
    for domain in domains:
        domain_frame = _domain_frame(proposed, domain) if not proposed.empty else proposed
        for component in SCORE_COMPONENTS:
            values = [safe_float(value) for value in domain_frame.get(component, [])]
            positives = [value for value in values if value > 0.0]
            scale = _positive_p95(positives)
            calibration[(domain, component)] = scale
            diagnostics.append(
                {
                    "domain": domain,
                    "component": component,
                    "p95_scale": scale,
                    "min": min(values) if values else 0.0,
                    "max": max(values) if values else 0.0,
                    "positive_count": len(positives),
                }
            )
    return calibration, pd.DataFrame(diagnostics)


def _with_opportunity_scores(frame: pd.DataFrame, calibration: dict[tuple[str, str], float]) -> pd.DataFrame:
    copy = frame.copy()
    if copy.empty:
        copy["score"] = []
        return copy
    copy["score"] = copy.apply(lambda row: round(_opportunity_score(row, calibration), 12), axis=1)
    return copy


def _opportunity_score(row: pd.Series, calibration: dict[tuple[str, str], float] | None = None) -> float:
    if calibration is None:
        provided = _optional_float(row.get("score"))
        if provided is not None:
            return provided
        return sum(safe_float(row.get(component)) for component in SCORE_COMPONENTS)
    domain = str(row.get("domain", "")).strip().lower()
    return sum(_calibrated_component(row, domain, component, calibration) for component in SCORE_COMPONENTS)


def _calibrated_component(
    row: pd.Series,
    domain: str,
    component: str,
    calibration: dict[tuple[str, str], float],
) -> float:
    scale = calibration.get((domain, component), 0.0)
    if scale <= 0.0:
        return 0.0
    return _clamp01(safe_float(row.get(component)) / scale)


def _positive_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * 0.95) - 1))
    return float(ordered[index])


def _thresholded_proposed_frame(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    copy = frame.copy()
    if copy.empty:
        return copy
    if "score" not in copy:
        copy["score"] = copy.apply(_opportunity_score, axis=1)
    low_score = copy["score"].astype(float) < float(threshold)
    if low_score.any():
        copy.loc[low_score, "action"] = "HOLD"
        copy.loc[low_score, "outcome"] = ""
        copy.loc[low_score, "pnl"] = None
    return copy


def _action_trace(frame: pd.DataFrame, operating_threshold: float) -> pd.DataFrame:
    proposed = _method_frame(frame, "proposed_agent")
    if proposed.empty:
        return pd.DataFrame(columns=ACTION_TRACE_FIELDS)

    rows = []
    previous_domain = ""
    timestamps = sorted(_clean_text(value) for value in proposed.get("timestamp", []) if _clean_text(value))
    for timestamp in dict.fromkeys(timestamps):
        current = proposed[proposed["timestamp"].astype(str) == timestamp].copy()
        scores = {
            domain: _best_domain_score(_domain_frame(current, domain))
            for domain in DOMAINS
        }
        candidate = _best_acted_candidate(current)
        selected = None
        if candidate is not None and safe_float(candidate.get("score")) >= operating_threshold:
            selected = candidate

        prior = previous_domain
        if selected is None:
            action_type = "exit" if previous_domain else "hold"
            reason = _no_selection_reason(current, candidate, operating_threshold)
            selected_domain = ""
            previous_domain = ""
            selected_market_id = ""
            selected_action = ""
            selected_score = ""
        else:
            selected_domain = str(selected.get("domain", "")).strip().lower()
            selected_market_id = _clean_text(selected.get("market_id"))
            selected_action = _clean_text(selected.get("action")).upper()
            selected_score = safe_float(selected.get("score"))
            if not previous_domain:
                action_type = "enter"
                reason = "selected_domain_above_threshold"
            elif previous_domain == selected_domain:
                action_type = "maintain"
                reason = "selected_domain_remains_best"
            else:
                action_type = "switch"
                reason = "selected_domain_changed"
            previous_domain = selected_domain

        rows.append(
            {
                "timestamp": timestamp,
                "cs2_score": _blank_or_value(scores["cs2"]),
                "btc_score": _blank_or_value(scores["btc"]),
                "weather_score": _blank_or_value(scores["weather"]),
                "selected_domain": selected_domain,
                "previous_domain": prior,
                "action_type": action_type,
                "reason": reason,
                "selected_market_id": selected_market_id,
                "selected_action": selected_action,
                "selected_score": _blank_or_value(selected_score),
            }
        )
    return pd.DataFrame(rows, columns=ACTION_TRACE_FIELDS)


def _trace_counts(trace: pd.DataFrame) -> dict[str, int]:
    counts = Counter(trace.get("action_type", []))
    return {
        "hold": int(counts.get("hold", 0)),
        "enter": int(counts.get("enter", 0)),
        "maintain": int(counts.get("maintain", 0)),
        "switch": int(counts.get("switch", 0)),
        "exit": int(counts.get("exit", 0)),
        "rows": int(len(trace)),
    }


def _best_domain_score(frame: pd.DataFrame) -> float | None:
    if frame.empty or "score" not in frame:
        return None
    scores = [safe_float(value) for value in frame["score"]]
    return max(scores) if scores else None


def _best_acted_candidate(frame: pd.DataFrame) -> pd.Series | None:
    if frame.empty:
        return None
    acted = frame[frame.apply(_acted, axis=1)].copy()
    if acted.empty:
        return None
    return acted.sort_values(["score", "edge"], ascending=False).iloc[0]


def _no_selection_reason(current: pd.DataFrame, candidate: pd.Series | None, threshold: float) -> str:
    if current.empty:
        return "no_domain_report"
    if candidate is None:
        return "no_acted_candidate"
    return "below_operating_threshold" if safe_float(candidate.get("score")) < threshold else "no_selected_domain"


def _example_row(case: str, row: pd.Series) -> dict:
    return {
        "case": case,
        "domain": row.get("domain", ""),
        "market_id": row.get("market_id", ""),
        "market_prob": row.get("market_prob", ""),
        "model_prob": row.get("model_prob", ""),
        "edge": row.get("edge", ""),
        "score": row.get("score", ""),
        "action": row.get("action", ""),
        "outcome": row.get("outcome", ""),
    }


def _switch_or_exit_case(frame: pd.DataFrame, trace: pd.DataFrame) -> pd.Series | None:
    if frame.empty or trace.empty:
        return None
    candidates = trace[trace.get("action_type", "").isin(["switch", "exit"])]
    for _, trace_row in candidates.iterrows():
        market_id = _clean_text(trace_row.get("selected_market_id"))
        if not market_id:
            continue
        matches = frame[
            (frame["timestamp"].astype(str) == str(trace_row.get("timestamp")))
            & (frame["market_id"].astype(str) == market_id)
        ]
        if not matches.empty:
            return matches.iloc[0]
    return None


def _placeholder_markdown(
    frame: pd.DataFrame,
    operating_threshold: float,
    trace_counts: dict[str, int],
    threshold_grid: Iterable[float],
) -> str:
    proposed = _method_frame(frame, "proposed_agent")
    thresholded = _thresholded_proposed_frame(proposed, operating_threshold)
    overall = _metrics(thresholded)
    table1 = _table1(frame, operating_threshold)
    table2 = _table2(frame, operating_threshold)
    table3 = _table3(frame, threshold_grid)
    trace = _action_trace(frame, operating_threshold)
    table4 = _table4(frame, operating_threshold, trace)
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
        f"- proposed_return_per_signal: {_value(overall['return_per_signal'])}",
        f"- domain_switches: {trace_counts.get('switch', 0)}",
        f"- exits: {trace_counts.get('exit', 0)}",
        f"- trace_rows: {trace_counts.get('rows', 0)}",
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
            f"edge={_value(row.get('edge'))}, score={_value(row.get('score'))}, outcome={row.get('outcome')}"
        )
    lines.append("")
    return "\n".join(lines)


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
            f"return_per_signal={_value(row.get('return_per_signal'))}",
        ]
        if include_share:
            parts.append(f"share_pct={_pct(row.get('share'))}")
        lines.append("- " + ", ".join(parts))
    return lines


def _method_frame(frame: pd.DataFrame, method: str) -> pd.DataFrame:
    if frame.empty or "method" not in frame:
        return frame.copy()
    return frame[frame["method"] == method].copy()


def _domain_frame(frame: pd.DataFrame, domain: str) -> pd.DataFrame:
    if frame.empty or "domain" not in frame:
        return frame.copy()
    return frame[frame["domain"].astype(str).str.lower() == domain].copy()


def _pct(value: object) -> str:
    numeric = _optional_float(value)
    return "" if numeric is None else f"{numeric * 100:.2f}"


def _value(value: object) -> str:
    numeric = _optional_float(value)
    if numeric is None:
        return ""
    return f"{numeric:.6f}".rstrip("0").rstrip(".")


def _blank_or_value(value: object) -> str:
    numeric = _optional_float(value)
    if numeric is None:
        return ""
    return _value(numeric)


def _optional_float(value: object) -> float | None:
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none"} else text
