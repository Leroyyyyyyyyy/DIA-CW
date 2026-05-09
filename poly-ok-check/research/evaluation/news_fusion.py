from __future__ import annotations

from dataclasses import replace

from research.schemas.domain_report import DomainReport, safe_float


def fuse_domain_news(
    reports: list[DomainReport],
    news_reports: list[DomainReport],
    standalone_domains: set[str] | None = None,
) -> list[DomainReport]:
    standalone = {domain.lower() for domain in standalone_domains or set()}
    news_by_domain = _best_news_by_domain(news_reports)
    fused: list[DomainReport] = []

    for report in reports:
        metadata = dict(report.metadata)
        source = str(metadata.get("source", "")).strip().lower()
        if source == "acy_news":
            metadata.setdefault("news_connected", True)
            metadata.setdefault("news_source", "acy_news")
            fused.append(replace(report, metadata=metadata))
            continue

        domain = report.domain.lower()
        news = news_by_domain.get(domain)
        if news is None or domain in standalone:
            fused.append(report)
            continue

        news_metadata = dict(news.metadata)
        metadata.update(
            {
                "news_connected": True,
                "news_source": "acy_news",
                "news_signal_market_id": news.market_id,
                "news_signal_timestamp": news.timestamp,
                "news_evidence_ref": news.evidence_ref,
                "news_model_prob": news.model_prob,
                "news_market_prob": news.market_prob,
                "news_action": news.action,
                "news_candidate_side": news_metadata.get("candidate_side", news.action),
                "news_score_applied": news.news_score,
                "news_baseline_eligible": False,
            }
        )
        fused.append(
            replace(
                report,
                news_score=max(report.news_score, news.news_score),
                metadata=metadata,
            )
        )

    return fused


def _best_news_by_domain(news_reports: list[DomainReport]) -> dict[str, DomainReport]:
    best: dict[str, DomainReport] = {}
    for report in news_reports:
        domain = report.domain.lower()
        current = best.get(domain)
        if current is None or _news_rank(report) > _news_rank(current):
            best[domain] = report
    return best


def _news_rank(report: DomainReport) -> tuple[float, float]:
    return (safe_float(report.news_score), safe_float(report.edge))
