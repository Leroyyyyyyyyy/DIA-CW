from __future__ import annotations

from research.evaluation.baselines import expand_with_baselines
from research.evaluation.category_policy import apply_category_policy
from research.schemas.domain_report import DomainReport


def test_weather_policy_keeps_only_trades_csv_executions(tmp_path) -> None:
    trades = tmp_path / "backtest_trades.csv"
    trades.write_text(
        "\n".join(
            [
                "timestamp_utc,market_slug,side",
                "2026-04-24 17:00:04+0000,event-21c,NO",
            ]
        ),
        encoding="utf-8",
    )
    reports = [
        _report(
            domain="weather",
            timestamp="2026-04-24 17:00:04+0000",
            market_id="event-21c",
            action="NO",
            metadata={"raw_metadata": {"event_slug": "event"}},
        ),
        _report(
            domain="weather",
            timestamp="2026-04-24 17:00:04+0000",
            market_id="event-22c",
            action="NO",
            metadata={"raw_metadata": {"event_slug": "event"}},
        ),
    ]

    adjusted, diagnostics = apply_category_policy(
        reports,
        policy={
            "enabled": True,
            "weather": {
                "execution_source": "trades_csv",
                "max_trades_per_event": 3,
                "max_trades_per_market_side": 1,
            },
        },
        inputs={"weather": {"trades_csv": trades}},
        base_dir=tmp_path,
        config_dir=tmp_path,
    )

    assert [report.market_id for report in adjusted] == ["event-21c"]
    assert adjusted[0].metadata["policy_reason"] == "weather_execution_in_trades"
    assert {row["reason"] for row in diagnostics} == {
        "weather_execution_in_trades",
        "weather_execution_not_in_trades",
    }


def test_btc_and_cs2_policy_rules_block_weak_or_repeated_entries() -> None:
    reports = [
        _report(domain="btc", market_id="btc-1", action="NO", edge=0.0025, news_score=0.012),
        _report(domain="btc", market_id="btc-2", action="NO", edge=0.001, news_score=0.012),
        _report(domain="cs2", timestamp="2026-04-03T08:20:37Z", market_id="cs2", action="NO", edge=0.05),
        _report(domain="cs2", timestamp="2026-04-03T08:30:39Z", market_id="cs2", action="YES", edge=0.06),
        _report(domain="cs2", timestamp="2026-04-03T08:40:39Z", market_id="cs2", action="YES", edge=0.09),
        _report(domain="cs2", timestamp="2026-04-03T08:50:39Z", market_id="cs2", action="YES", edge=0.10),
    ]

    adjusted, _ = apply_category_policy(
        reports,
        policy={
            "enabled": True,
            "btc": {"min_edge": 0.002, "min_news_score": 0.01, "max_trades_per_market": 1},
            "cs2": {"max_trades_per_market_side": 1, "switch_buffer": 0.03},
        },
    )

    assert [report.action for report in adjusted] == ["NO", "HOLD", "NO", "HOLD", "YES", "HOLD"]
    assert adjusted[1].metadata["policy_reason"] == "btc_below_edge_threshold"
    assert adjusted[3].metadata["policy_reason"] == "cs2_switch_buffer_not_met"
    assert adjusted[5].metadata["policy_reason"] == "cs2_position_already_open"

    expanded = expand_with_baselines(adjusted)
    blocked_btc = [report for report in expanded if report.market_id == "btc-2"]
    assert {report.action for report in blocked_btc} == {"HOLD"}


def _report(
    domain: str,
    timestamp: str = "2026-05-01T00:00:00Z",
    market_id: str = "market",
    action: str = "YES",
    edge: float = 0.1,
    news_score: float = 0.0,
    metadata: dict | None = None,
) -> DomainReport:
    return DomainReport(
        domain=domain,
        timestamp=timestamp,
        market_id=market_id,
        target=market_id,
        market_prob=0.5,
        model_prob=0.5 + edge if action == "YES" else 0.5 - edge,
        data_score=0.5,
        news_score=news_score,
        edge=edge,
        action=action,
        outcome="WIN",
        metadata=metadata or {"candidate_side": action, "yes_outcome": 1.0},
    )
