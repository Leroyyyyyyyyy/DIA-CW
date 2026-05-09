from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from research.evaluation.outcomes import selected_side_outcome
from research.schemas.domain_report import DomainReport, clamp01, normalize_action, safe_float


BASELINE_METHODS = ["market_only", "data_only", "news_only", "data_news"]
EVALUATION_METHODS = [*BASELINE_METHODS, "proposed_agent"]


def expand_with_baselines(reports: Iterable[DomainReport]) -> list[DomainReport]:
    proposed = [replace(report, method="proposed_agent") for report in reports if report.method == "proposed_agent"]
    if not proposed:
        proposed = [replace(report, method="proposed_agent") for report in reports]

    expanded: list[DomainReport] = []
    for method in BASELINE_METHODS:
        expanded.extend(_baseline_report(report, method) for report in proposed)
    expanded.extend(proposed)
    return expanded


def _baseline_report(source: DomainReport, method: str) -> DomainReport:
    if source.metadata.get("policy_blocked") is True:
        metadata = dict(source.metadata)
        metadata.update(
            {
                "baseline_source_method": source.method,
                "baseline_rule": method,
            }
        )
        return replace(source, method=method, action="HOLD", outcome="", pnl=None, metadata=metadata)

    side = _candidate_side(source)
    market_prob = clamp01(source.market_prob)

    if method == "market_only":
        model_prob = market_prob
        action = side if market_prob >= 0.5 else "HOLD"
        data_score = 0.0
        news_score = 0.0
    elif method == "data_only":
        model_prob = clamp01(source.model_prob) if source.domain in {"cs2", "weather"} else 0.5
        action = side if source.domain in {"cs2", "weather"} and model_prob > market_prob else "HOLD"
        data_score = source.data_score if source.domain in {"cs2", "weather"} else 0.0
        news_score = 0.0
    elif method == "news_only":
        has_news_signal = _has_news_signal(source)
        news_side = _news_candidate_side(source)
        model_prob = _news_model_prob(source) if has_news_signal else 0.5
        market_prob = _news_market_prob(source) if has_news_signal else market_prob
        action = news_side if has_news_signal and model_prob > market_prob else "HOLD"
        data_score = 0.0
        news_score = source.news_score if has_news_signal else 0.0
    elif method == "data_news":
        model_prob = clamp01(source.model_prob)
        action = side if model_prob > market_prob else "HOLD"
        data_score = source.data_score
        news_score = source.news_score
    else:
        raise ValueError(f"Unsupported baseline method: {method}")

    metadata = dict(source.metadata)
    metadata.update(
        {
            "baseline_source_method": source.method,
            "baseline_rule": method,
            "candidate_side": side,
        }
    )
    return replace(
        source,
        method=method,
        market_prob=market_prob,
        model_prob=model_prob,
        data_score=data_score,
        news_score=news_score,
        edge=abs(model_prob - market_prob),
        action=action,
        outcome=_outcome_for_action(source, action),
        pnl=None,
        metadata=metadata,
    )


def _candidate_side(report: DomainReport) -> str:
    metadata_side = str(report.metadata.get("candidate_side") or report.metadata.get("side") or "").strip().upper()
    side = normalize_action(metadata_side)
    if side in {"YES", "NO"}:
        return side
    action = normalize_action(report.action)
    if action in {"YES", "NO"}:
        return action
    return "YES"


def _has_news_signal(report: DomainReport) -> bool:
    if report.metadata.get("news_baseline_eligible") is False:
        return False
    return str(report.metadata.get("source", "")).strip().lower() == "acy_news" or safe_float(report.news_score) > 0.0


def _news_candidate_side(report: DomainReport) -> str:
    side = normalize_action(report.metadata.get("news_candidate_side"))
    if side in {"YES", "NO"}:
        return side
    return _candidate_side(report)


def _news_model_prob(report: DomainReport) -> float:
    if "news_model_prob" in report.metadata:
        return clamp01(safe_float(report.metadata.get("news_model_prob"), report.model_prob))
    return clamp01(report.model_prob)


def _news_market_prob(report: DomainReport) -> float:
    if "news_market_prob" in report.metadata:
        return clamp01(safe_float(report.metadata.get("news_market_prob"), report.market_prob))
    return clamp01(report.market_prob)


def _outcome_for_action(source: DomainReport, action: str) -> str:
    side = normalize_action(action)
    if side not in {"YES", "NO"}:
        return ""
    yes_outcome = source.metadata.get("yes_outcome")
    if yes_outcome is not None and str(yes_outcome).strip() != "":
        return selected_side_outcome(side, safe_float(yes_outcome))
    if normalize_action(source.action) == side and str(source.outcome).strip():
        return str(source.outcome).strip().upper()
    return ""
