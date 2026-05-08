from __future__ import annotations

import re
import warnings
from pathlib import Path
from typing import Any

import pandas as pd

from research.schemas.domain_report import (
    DomainReport,
    clamp01,
    infer_action,
    parse_json_cell,
    safe_float,
)
from research.evaluation.outcomes import load_yes_outcomes_csv, selected_side_outcome


def load_acy_news_reports(
    signals_csv: Path | str | None = None,
    evidence_jsonl: Path | str | None = None,
    news_inputs: list[dict[str, Any]] | None = None,
    news_output_dirs: list[Path | str] | None = None,
    domains: list[str] | None = None,
    market_prob_default: float = 0.5,
    method: str = "proposed_agent",
    outcome_by_domain: dict[str, Any] | None = None,
    outcome_csv: Path | str | None = None,
) -> list[DomainReport]:
    primary_sources = [
        *_sources_from_news_inputs(news_inputs),
        *_sources_from_output_dirs(news_output_dirs),
    ]
    legacy_source = (
        _NewsSource(Path(signals_csv), Path(evidence_jsonl) if evidence_jsonl else None, None)
        if signals_csv
        else None
    )
    requested = {domain.lower() for domain in domains} if domains else None
    outcomes = outcome_by_domain or {}
    yes_outcomes = load_yes_outcomes_csv(outcome_csv)
    reports: list[DomainReport] = []

    sources = primary_sources or ([legacy_source] if legacy_source else [])
    reports.extend(
        _load_sources(
            sources,
            requested=requested,
            outcomes=outcomes,
            yes_outcomes=yes_outcomes,
            market_prob_default=market_prob_default,
            method=method,
        )
    )
    if not reports and primary_sources and legacy_source:
        reports.extend(
            _load_sources(
                [legacy_source],
                requested=requested,
                outcomes=outcomes,
                yes_outcomes=yes_outcomes,
                market_prob_default=market_prob_default,
                method=method,
            )
        )
    return reports


class _NewsSource:
    def __init__(self, signals_csv: Path, evidence_jsonl: Path | None, domain: str | None) -> None:
        self.signals_csv = signals_csv
        self.evidence_jsonl = evidence_jsonl
        self.domain = domain


def _sources_from_news_inputs(news_inputs: list[dict[str, Any]] | None) -> list[_NewsSource]:
    sources: list[_NewsSource] = []
    for item in news_inputs or []:
        signals_path = item.get("signals_path") or item.get("signals_csv")
        if not signals_path:
            warnings.warn(f"Skipping acy_news input without signals_path: {item}", stacklevel=2)
            continue
        evidence_path = item.get("evidence_path") or item.get("evidence_jsonl")
        sources.append(
            _NewsSource(
                Path(signals_path),
                Path(evidence_path) if evidence_path else None,
                _clean_text(item.get("domain")) or None,
            )
        )
    return sources


def _sources_from_output_dirs(news_output_dirs: list[Path | str] | None) -> list[_NewsSource]:
    sources: list[_NewsSource] = []
    for directory in news_output_dirs or []:
        output_dir = Path(directory)
        sources.append(
            _NewsSource(
                output_dir / "signals.csv",
                output_dir / "evidence.jsonl",
                _domain_from_folder(output_dir),
            )
        )
    return sources


def _load_sources(
    sources: list[_NewsSource | None],
    requested: set[str] | None,
    outcomes: dict[str, Any],
    yes_outcomes: dict[str, float],
    market_prob_default: float,
    method: str,
) -> list[DomainReport]:
    reports: list[DomainReport] = []
    for source in sources:
        if source is None:
            continue
        if not source.signals_csv.exists():
            warnings.warn(f"Skipping missing acy_news signals file: {source.signals_csv}", stacklevel=2)
            continue
        reports.extend(
            _reports_from_signals_csv(
                source,
                requested=requested,
                outcomes=outcomes,
                yes_outcomes=yes_outcomes,
                market_prob_default=market_prob_default,
                method=method,
            )
        )
    return reports


def _reports_from_signals_csv(
    source: _NewsSource,
    requested: set[str] | None,
    outcomes: dict[str, Any],
    yes_outcomes: dict[str, float],
    market_prob_default: float,
    method: str,
) -> list[DomainReport]:
    path = source.signals_csv
    frame = pd.read_csv(path)
    reports: list[DomainReport] = []

    for _, row in frame.iterrows():
        domain = (_clean_text(row.get("domain")) or source.domain or _domain_from_folder(path.parent)).lower()
        if requested is not None and domain not in requested:
            continue

        metadata = parse_json_cell(row.get("metadata"), default={})
        outcome_scores = parse_json_cell(row.get("outcome_scores"), default={})
        direction_score = safe_float(row.get("direction_score"))
        probability_delta = abs(safe_float(row.get("probability_delta")))
        relevance = clamp01(safe_float(row.get("relevance")))
        confidence = clamp01(safe_float(row.get("confidence")))

        has_direct_market_prob = _has_value(row.get("market_prob"))
        has_direct_model_prob = _has_value(row.get("model_prob"))
        yes_market_prob = clamp01(
            safe_float(row.get("market_prob"), safe_float(metadata.get("market_prob"), market_prob_default))
        )
        yes_model_prob = _model_probability(
            row=row,
            domain=domain,
            market_prob=yes_market_prob,
            direction_score=direction_score,
            probability_delta=probability_delta,
            outcome_scores=outcome_scores,
        )
        data_score = clamp01(safe_float(row.get("data_score"), safe_float(metadata.get("data_score"), 0.0)))
        news_score = clamp01(
            safe_float(row.get("news_score"), safe_float(metadata.get("news_score"), relevance * confidence))
        )
        action = _action_from_row(row, yes_model_prob, yes_market_prob, direction_score, probability_delta)
        candidate_side = action if action in {"YES", "NO"} else ("YES" if yes_model_prob >= yes_market_prob else "NO")
        if has_direct_market_prob and has_direct_model_prob:
            market_prob = yes_market_prob
            model_prob = yes_model_prob
        else:
            model_prob = 1.0 - yes_model_prob if candidate_side == "NO" else yes_model_prob
            market_prob = 1.0 - yes_market_prob if candidate_side == "NO" else yes_market_prob
        market_id = _clean_text(row.get("market_id")) or _clean_text(metadata.get("market_id")) or _stable_id(
            domain, _clean_text(row.get("target"))
        )
        timestamp = _timestamp_from_row(row, metadata)
        yes_outcome = yes_outcomes.get(market_id, yes_outcomes.get(domain))
        outcome = selected_side_outcome(action, yes_outcome)
        if not outcome:
            outcome = str(outcomes.get(market_id, outcomes.get(domain, "")))

        reports.append(
            DomainReport(
                method=method,
                domain=domain,
                timestamp=timestamp,
                market_id=market_id,
                target=_clean_text(row.get("target")),
                market_prob=market_prob,
                model_prob=model_prob,
                data_score=data_score,
                news_score=news_score,
                edge=abs(model_prob - market_prob),
                action=action,
                outcome=outcome,
                evidence_ref=_evidence_ref(row.get("evidence_ref"), row.get("top_evidence"), source.evidence_jsonl),
                metadata={
                    "source": "acy_news",
                    "signals_csv": str(path),
                    "evidence_jsonl": "" if source.evidence_jsonl is None else str(source.evidence_jsonl),
                    "candidate_side": candidate_side,
                    "yes_model_prob": yes_model_prob,
                    "yes_market_prob": yes_market_prob,
                    "yes_outcome": yes_outcome,
                    "direction_score": direction_score,
                    "probability_delta": probability_delta,
                    "confidence": confidence,
                    "relevance": relevance,
                    "raw_metadata": metadata,
                },
            )
        )
    return reports


def _model_probability(
    row: pd.Series,
    domain: str,
    market_prob: float,
    direction_score: float,
    probability_delta: float,
    outcome_scores: dict[str, Any],
) -> float:
    if _has_value(row.get("model_prob")):
        return clamp01(safe_float(row.get("model_prob"), market_prob))
    if domain == "weather" and outcome_scores:
        return clamp01(max(safe_float(value) for value in outcome_scores.values()))
    if probability_delta > 0.0:
        return clamp01(market_prob + (probability_delta if direction_score >= 0.0 else -probability_delta))
    return clamp01(market_prob + direction_score * 0.25)


def _action_from_row(
    row: pd.Series,
    model_prob: float,
    market_prob: float,
    direction_score: float,
    probability_delta: float,
) -> str:
    raw_action = _clean_text(row.get("action"))
    if raw_action:
        normalized = infer_action(model_prob, market_prob) if raw_action.upper() == "AUTO" else raw_action.upper()
        if normalized in {"BUY_YES", "LONG_YES", "ENTER_YES"}:
            return "YES"
        if normalized in {"BUY_NO", "LONG_NO", "ENTER_NO"}:
            return "NO"
        if normalized in {"NO_TRADE", "HOLD", "EXIT", "FLAT", "SELL", "CLOSE"}:
            return "HOLD" if normalized != "FLAT" else "FLAT"
        if normalized in {"YES", "NO", "HOLD", "FLAT"}:
            return normalized
    if probability_delta >= 0.03:
        if direction_score > 0.0:
            return "YES"
        if direction_score < 0.0:
            return "NO"
    if _has_value(row.get("model_prob")) and _has_value(row.get("market_prob")):
        return infer_action(model_prob, market_prob)
    return "HOLD"


def _timestamp_from_row(row: pd.Series, metadata: dict[str, Any]) -> str:
    timestamp = _clean_text(row.get("timestamp")) or _clean_text(row.get("generated_at"))
    if timestamp:
        return timestamp
    return _timestamp_from_metadata(metadata, "")


def _timestamp_from_metadata(metadata: dict[str, Any], generated_at: str) -> str:
    time_window = metadata.get("time_window") or metadata.get("news_window") or {}
    return str(time_window.get("as_of") or generated_at)


def _stable_id(domain: str, target: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")
    return f"{domain}:{slug or 'unknown'}"


def _evidence_ref(evidence_ref: Any, top_evidence: Any, evidence_jsonl: Path | str | None) -> str:
    explicit = _clean_text(evidence_ref)
    if explicit:
        return explicit
    parsed = parse_json_cell(top_evidence, default=[])
    if parsed:
        first = parsed[0]
        if isinstance(first, dict):
            for key in ("evidence_ref", "ref", "id", "evidence_id", "title", "source"):
                value = _clean_text(first.get(key))
                if value:
                    return value
        else:
            value = _clean_text(first)
            if value:
                return value
    return "" if evidence_jsonl is None else str(evidence_jsonl)


def _domain_from_folder(path: Path) -> str:
    name = path.name.lower()
    match = re.match(r"outputs_(?P<domain>.+?)_window$", name)
    if match:
        return match.group("domain")
    if name in {"btc", "cs2", "weather"}:
        return name
    for domain in ("btc", "cs2", "weather"):
        if domain in name:
            return domain
    return ""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if not text or text.lower() in {"nan", "none"} else text


def _has_value(value: Any) -> bool:
    return bool(_clean_text(value))
