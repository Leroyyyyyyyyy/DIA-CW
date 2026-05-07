from __future__ import annotations

import re
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
    signals_csv: Path | str,
    evidence_jsonl: Path | str | None = None,
    domains: list[str] | None = None,
    market_prob_default: float = 0.5,
    method: str = "proposed_agent",
    outcome_by_domain: dict[str, Any] | None = None,
    outcome_csv: Path | str | None = None,
) -> list[DomainReport]:
    path = Path(signals_csv)
    frame = pd.read_csv(path)
    requested = {domain.lower() for domain in domains} if domains else None
    outcomes = outcome_by_domain or {}
    yes_outcomes = load_yes_outcomes_csv(outcome_csv)
    reports: list[DomainReport] = []

    for _, row in frame.iterrows():
        domain = str(row.get("domain", "")).strip().lower()
        if requested is not None and domain not in requested:
            continue

        metadata = parse_json_cell(row.get("metadata"), default={})
        outcome_scores = parse_json_cell(row.get("outcome_scores"), default={})
        direction_score = safe_float(row.get("direction_score"))
        probability_delta = abs(safe_float(row.get("probability_delta")))
        relevance = clamp01(safe_float(row.get("relevance")))
        confidence = clamp01(safe_float(row.get("confidence")))

        yes_model_prob = _model_probability(domain, direction_score, probability_delta, outcome_scores)
        yes_market_prob = clamp01(safe_float(metadata.get("market_prob"), market_prob_default))
        data_score = clamp01(safe_float(metadata.get("data_score"), 0.0))
        news_score = clamp01(safe_float(metadata.get("news_score"), relevance * confidence))
        action = infer_action(yes_model_prob, yes_market_prob)
        candidate_side = action if action in {"YES", "NO"} else ("YES" if yes_model_prob >= yes_market_prob else "NO")
        model_prob = 1.0 - yes_model_prob if candidate_side == "NO" else yes_model_prob
        market_prob = 1.0 - yes_market_prob if candidate_side == "NO" else yes_market_prob
        market_id = str(metadata.get("market_id") or _stable_id(domain, str(row.get("target", ""))))
        timestamp = _timestamp_from_metadata(metadata, str(row.get("generated_at", "")))
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
                target=str(row.get("target", "")),
                market_prob=market_prob,
                model_prob=model_prob,
                data_score=data_score,
                news_score=news_score,
                edge=abs(model_prob - market_prob),
                action=action,
                outcome=outcome,
                evidence_ref=_evidence_ref(row.get("top_evidence"), evidence_jsonl),
                metadata={
                    "source": "acy_news",
                    "signals_csv": str(path),
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
    domain: str,
    direction_score: float,
    probability_delta: float,
    outcome_scores: dict[str, Any],
) -> float:
    if domain == "weather" and outcome_scores:
        return clamp01(max(safe_float(value) for value in outcome_scores.values()))
    if probability_delta > 0.0:
        return clamp01(0.5 + (probability_delta if direction_score >= 0.0 else -probability_delta))
    return clamp01(0.5 + direction_score * 0.25)


def _timestamp_from_metadata(metadata: dict[str, Any], generated_at: str) -> str:
    time_window = metadata.get("time_window") or metadata.get("news_window") or {}
    return str(time_window.get("as_of") or generated_at)


def _stable_id(domain: str, target: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", target.lower()).strip("-")
    return f"{domain}:{slug or 'unknown'}"


def _evidence_ref(top_evidence: Any, evidence_jsonl: Path | str | None) -> str:
    parsed = parse_json_cell(top_evidence, default=[])
    if parsed:
        first = parsed[0]
        if isinstance(first, dict):
            title = first.get("title") or first.get("source")
            if title:
                return str(title)
    return "" if evidence_jsonl is None else str(evidence_jsonl)
