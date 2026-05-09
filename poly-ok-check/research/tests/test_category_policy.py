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
        "weather_execution_not_selected",
    }


def test_weather_policy_can_backfill_deduped_candidate_executions(tmp_path) -> None:
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
            edge=0.15,
            news_score=0.2,
            metadata={"raw_metadata": {"event_slug": "event"}},
        ),
        _report(
            domain="weather",
            timestamp="2026-04-25 01:00:04+0000",
            market_id="event-22c",
            action="NO",
            edge=0.14,
            news_score=0.2,
            metadata={"raw_metadata": {"event_slug": "event"}},
        ),
        _report(
            domain="weather",
            timestamp="2026-04-25 02:00:04+0000",
            market_id="event-22c",
            action="NO",
            edge=0.16,
            news_score=0.2,
            metadata={"raw_metadata": {"event_slug": "event"}},
        ),
    ]

    adjusted, diagnostics = apply_category_policy(
        reports,
        policy={
            "enabled": True,
            "weather": {
                "execution_source": "trades_csv",
                "max_trades_per_event": 2,
                "max_trades_per_market_side": 1,
                "candidate_backfill": {
                    "enabled": True,
                    "max_total_trades": 2,
                    "min_edge": 0.12,
                    "min_news_score": 0.01,
                    "min_time_gap_minutes": 60,
                },
            },
        },
        inputs={"weather": {"trades_csv": trades}},
        base_dir=tmp_path,
        config_dir=tmp_path,
    )

    assert [(report.market_id, report.timestamp) for report in adjusted] == [
        ("event-21c", "2026-04-24 17:00:04+0000"),
        ("event-22c", "2026-04-25 02:00:04+0000"),
    ]
    assert adjusted[1].metadata["policy_reason"] == "weather_candidate_backfill"
    assert [row["reason"] for row in diagnostics].count("weather_candidate_backfill") == 1


def test_weather_backfill_enforces_time_gap_per_market_side(tmp_path) -> None:
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
            edge=0.15,
            news_score=0.2,
            metadata={"raw_metadata": {"event_slug": "event"}},
        ),
        _report(
            domain="weather",
            timestamp="2026-04-24 17:30:04+0000",
            market_id="event-21c",
            action="NO",
            edge=0.25,
            news_score=0.2,
            metadata={"raw_metadata": {"event_slug": "event"}},
        ),
        _report(
            domain="weather",
            timestamp="2026-04-24 18:00:04+0000",
            market_id="event-21c",
            action="NO",
            edge=0.2,
            news_score=0.2,
            metadata={"raw_metadata": {"event_slug": "event"}},
        ),
        _report(
            domain="weather",
            timestamp="2026-04-24 19:00:04+0000",
            market_id="event-21c",
            action="NO",
            edge=0.18,
            news_score=0.2,
            metadata={"raw_metadata": {"event_slug": "event"}},
        ),
    ]

    adjusted, _ = apply_category_policy(
        reports,
        policy={
            "enabled": True,
            "weather": {
                "execution_source": "trades_csv",
                "max_trades_per_event": 4,
                "max_trades_per_market_side": 4,
                "candidate_backfill": {
                    "enabled": True,
                    "max_total_trades": 4,
                    "min_edge": 0.12,
                    "min_news_score": 0.01,
                    "min_time_gap_minutes": 60,
                },
            },
        },
        inputs={"weather": {"trades_csv": trades}},
        base_dir=tmp_path,
        config_dir=tmp_path,
    )

    assert [report.timestamp for report in adjusted] == [
        "2026-04-24 17:00:04+0000",
        "2026-04-24 18:00:04+0000",
        "2026-04-24 19:00:04+0000",
    ]


def test_weather_policy_blocks_low_price_and_immediate_above_forecast_no(tmp_path) -> None:
    trades = tmp_path / "backtest_trades.csv"
    trades.write_text(
        "\n".join(
            [
                "timestamp_utc,market_slug,side",
                "2026-04-24 17:00:04+0000,event-21c,NO",
                "2026-04-24 18:00:04+0000,event-22c,NO",
                "2026-04-24 19:00:04+0000,event-19c,YES",
            ]
        ),
        encoding="utf-8",
    )
    common_metadata = {"raw_metadata": {"event_slug": "event", "forecast_max_temp_c": 20.2}}
    reports = [
        _report(
            domain="weather",
            timestamp="2026-04-24 17:00:04+0000",
            market_id="event-21c",
            action="NO",
            edge=0.2,
            news_score=0.2,
            metadata=common_metadata,
        ),
        _report(
            domain="weather",
            timestamp="2026-04-24 18:00:04+0000",
            market_id="event-22c",
            action="NO",
            edge=0.2,
            news_score=0.2,
            metadata=common_metadata,
        ),
        _report(
            domain="weather",
            timestamp="2026-04-24 19:00:04+0000",
            market_id="event-19c",
            action="YES",
            edge=0.2,
            news_score=0.2,
            metadata=common_metadata,
            market_prob=0.03,
        ),
    ]

    adjusted, diagnostics = apply_category_policy(
        reports,
        policy={
            "enabled": True,
            "weather": {
                "execution_source": "trades_csv",
                "max_trades_per_event": 3,
                "max_trades_per_market_side": 3,
                "min_entry_price": 0.1,
                "skip_no_immediate_above_forecast_bin": True,
            },
        },
        inputs={"weather": {"trades_csv": trades}},
        base_dir=tmp_path,
        config_dir=tmp_path,
    )

    assert [report.market_id for report in adjusted] == ["event-22c"]
    assert {row["reason"] for row in diagnostics} == {
        "weather_execution_in_trades",
        "weather_no_immediate_above_forecast_bin",
        "weather_below_min_entry_price",
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


def test_btc_policy_blocks_expired_rolling_news_signal() -> None:
    reports = [
        _report(
            domain="btc",
            timestamp="2026-05-06T18:25:00Z",
            market_id="btc-fresh",
            action="NO",
            edge=0.0025,
            news_score=0.012,
            metadata={
                "raw_metadata": {
                    "market_window": {"as_of": "2026-05-06T18:25:00Z"},
                    "source_signal_generated_at": "2026-05-06T18:23:27.168676Z",
                }
            },
        ),
        _report(
            domain="btc",
            timestamp="2026-05-06T19:25:00Z",
            market_id="btc-expired",
            action="NO",
            edge=0.0025,
            news_score=0.012,
            metadata={
                "raw_metadata": {
                    "market_window": {"as_of": "2026-05-06T19:25:00Z"},
                    "source_signal_generated_at": "2026-05-06T18:23:27.168676Z",
                }
            },
        ),
    ]

    adjusted, diagnostics = apply_category_policy(
        reports,
        policy={
            "enabled": True,
            "btc": {"min_edge": 0.002, "min_news_score": 0.01, "max_signal_age_minutes": 60},
        },
    )

    assert [report.action for report in adjusted] == ["NO", "HOLD"]
    assert adjusted[1].metadata["policy_reason"] == "btc_signal_age_exceeded"
    assert {row["reason"] for row in diagnostics} == {"btc_policy_pass", "btc_signal_age_exceeded"}


def test_cs2_policy_requires_news_alignment_and_allows_same_side_entries() -> None:
    reports = [
        _report(
            domain="cs2",
            timestamp="2026-04-03T08:20:37Z",
            market_id="cs2",
            action="NO",
            edge=0.08,
            metadata={"news_candidate_side": "YES"},
        ),
        _report(
            domain="cs2",
            timestamp="2026-04-03T08:30:39Z",
            market_id="cs2",
            action="YES",
            edge=0.06,
            metadata={"news_candidate_side": "YES"},
        ),
        _report(
            domain="cs2",
            timestamp="2026-04-03T08:38:37Z",
            market_id="cs2",
            action="YES",
            edge=0.055,
            metadata={"news_candidate_side": "YES"},
        ),
        _report(
            domain="cs2",
            timestamp="2026-04-03T09:09:49Z",
            market_id="cs2",
            action="YES",
            edge=0.04,
            metadata={"news_candidate_side": "YES"},
        ),
    ]

    adjusted, diagnostics = apply_category_policy(
        reports,
        policy={
            "enabled": True,
            "cs2": {
                "max_trades_per_market_side": 2,
                "min_edge": 0.05,
                "require_news_alignment": True,
                "switch_buffer": 0.03,
            },
        },
    )

    assert [report.action for report in adjusted] == ["HOLD", "YES", "YES", "HOLD"]
    assert adjusted[0].metadata["policy_reason"] == "cs2_news_side_mismatch"
    assert adjusted[3].metadata["policy_reason"] == "cs2_below_edge_threshold"
    assert {row["reason"] for row in diagnostics} == {
        "cs2_news_side_mismatch",
        "cs2_policy_pass",
        "cs2_below_edge_threshold",
    }


def _report(
    domain: str,
    timestamp: str = "2026-05-01T00:00:00Z",
    market_id: str = "market",
    action: str = "YES",
    edge: float = 0.1,
    news_score: float = 0.0,
    metadata: dict | None = None,
    market_prob: float = 0.5,
) -> DomainReport:
    return DomainReport(
        domain=domain,
        timestamp=timestamp,
        market_id=market_id,
        target=market_id,
        market_prob=market_prob,
        model_prob=market_prob + edge if action == "YES" else market_prob + edge,
        data_score=0.5,
        news_score=news_score,
        edge=edge,
        action=action,
        outcome="WIN",
        metadata=metadata or {"candidate_side": action, "yes_outcome": 1.0},
    )
