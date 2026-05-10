from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from research.evaluation.outcomes import selected_side_outcome
from research.schemas.domain_report import DomainReport, clamp01, normalize_action, safe_float


BASELINE_METHODS = ["market_only", "data_only", "news_only", "data_news"]
EVALUATION_METHODS = [*BASELINE_METHODS, "proposed_agent"]
DEFAULT_DATA_ONLY_MIN_EDGE = 0.02
DEFAULT_DATA_ONLY_MIN_SCORE = 0.01


def expand_with_baselines(
    reports: Iterable[DomainReport],
    baseline_reports: Iterable[DomainReport] | None = None,
    baseline_config: dict | None = None,
) -> list[DomainReport]:
    proposed = [replace(report, method="proposed_agent") for report in reports if report.method == "proposed_agent"]
    if not proposed:
        proposed = [replace(report, method="proposed_agent") for report in reports]
    baseline_source = list(baseline_reports) if baseline_reports is not None else proposed

    expanded: list[DomainReport] = []
    for method in BASELINE_METHODS:
        expanded.extend(_baseline_report(report, method, baseline_config or {}) for report in baseline_source)
    expanded.extend(proposed)
    return expanded


def _baseline_report(source: DomainReport, method: str, baseline_config: dict | None = None) -> DomainReport:
    config = baseline_config or {}
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
        data_cfg = dict(config.get("data_only", {}))
        min_edge = float(data_cfg.get("min_edge", DEFAULT_DATA_ONLY_MIN_EDGE) or 0.0)
        min_data_score = float(data_cfg.get("min_data_score", DEFAULT_DATA_ONLY_MIN_SCORE) or 0.0)
        market_prob_yes, model_prob_yes = _data_only_yes_probabilities(source)
        data_score = source.data_score
        news_score = 0.0
        action = _data_only_action(source, model_prob_yes, market_prob_yes, min_data_score, min_edge)
        if action == "NO":
            market_prob = 1.0 - market_prob_yes
            model_prob = 1.0 - model_prob_yes
        else:
            market_prob = market_prob_yes
            model_prob = model_prob_yes
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
            "baseline_independent": method == "data_only",
            "baseline_probability_space": "yes" if method == "data_only" else "selected_side",
            "baseline_market_prob_yes": market_prob_yes if method == "data_only" else "",
            "baseline_model_prob_yes": model_prob_yes if method == "data_only" else "",
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


def _data_only_action(
    report: DomainReport,
    model_prob_yes: float,
    market_prob_yes: float,
    min_data_score: float,
    min_edge: float,
) -> str:
    if safe_float(report.data_score) < min_data_score:
        return "HOLD"
    diff = model_prob_yes - market_prob_yes
    if abs(diff) < min_edge:
        return "HOLD"
    return "YES" if diff > 0.0 else "NO"


def _data_only_yes_probabilities(report: DomainReport) -> tuple[float, float]:
    metadata = report.metadata or {}
    fair_prob_yes = _metadata_float(metadata, "fair_prob_yes")
    orderbook_mid_yes = _metadata_float(metadata, "orderbook_mid_yes")
    if fair_prob_yes is not None and orderbook_mid_yes is not None:
        return clamp01(orderbook_mid_yes), clamp01(fair_prob_yes)

    raw_metadata = metadata.get("raw_metadata")
    if isinstance(raw_metadata, dict):
        yes_price = _metadata_float(raw_metadata, "yes_price")
        yes_edge = _metadata_float(raw_metadata, "yes_edge")
        if yes_price is not None and yes_edge is not None:
            return clamp01(yes_price), clamp01(yes_price + yes_edge)

    side = normalize_action(metadata.get("candidate_side") or report.action)
    if side == "NO":
        return 1.0 - clamp01(report.market_prob), 1.0 - clamp01(report.model_prob)
    return clamp01(report.market_prob), clamp01(report.model_prob)


def _metadata_float(metadata: dict, key: str) -> float | None:
    if key not in metadata:
        return None
    value = metadata.get(key)
    if value is None or str(value).strip() == "":
        return None
    return safe_float(value)


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
    return ""
