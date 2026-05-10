from __future__ import annotations

import json

import pandas as pd

from research.evaluation.baselines import expand_with_baselines
from research.evaluation.cw_tables import write_cw_tables, write_unified_reports
from research.evaluation.news_fusion import fuse_domain_news
from research.schemas.domain_report import DomainReport


def test_write_cw_tables_outputs_paper_csvs(tmp_path) -> None:
    reports = [
        DomainReport(
            domain="cs2",
            timestamp="2026-04-03T08:10:00Z",
            market_id="cs2",
            target="CS2",
            market_prob=0.55,
            model_prob=0.7,
            data_score=0.7,
            news_score=0.0,
            edge=0.15,
            action="YES",
            outcome="WIN",
        ),
        DomainReport(
            domain="weather",
            timestamp="2026-04-30T00:00:00Z",
            market_id="weather",
            target="Weather",
            market_prob=0.6,
            model_prob=0.75,
            data_score=0.75,
            news_score=0.0,
            edge=0.15,
            action="NO",
            outcome="LOSE",
            pnl=-1.0,
        ),
    ]

    write_unified_reports(reports, tmp_path / "unified.csv")
    paths = write_cw_tables(reports, tmp_path)

    assert (tmp_path / "unified.csv").exists()
    assert paths["table1"].exists()
    assert paths["placeholders"].exists()
    table1 = pd.read_csv(paths["table1"])
    proposed = table1[table1["method"] == "proposed_agent"].iloc[0]
    assert proposed["signals"] == 2
    assert proposed["coverage"] == 1.0
    assert "return_per_signal" in table1.columns
    table4 = pd.read_csv(paths["table4"])
    assert "score" in table4.columns
    placeholders = paths["placeholders"].read_text(encoding="utf-8")
    assert "proposed_return_per_signal" in placeholders
    assert "domain_switches" in placeholders


def test_baseline_expansion_fills_table1_methods(tmp_path) -> None:
    reports = [
        DomainReport(
            domain="cs2",
            timestamp="2026-04-03T08:10:00Z",
            market_id="cs2",
            target="CS2",
            market_prob=0.55,
            model_prob=0.7,
            data_score=0.7,
            news_score=0.0,
            edge=0.15,
            action="YES",
            outcome="WIN",
            metadata={"candidate_side": "YES", "yes_outcome": 1.0},
        ),
        DomainReport(
            domain="weather",
            timestamp="2026-04-30T00:00:00Z",
            market_id="weather",
            target="Weather",
            market_prob=0.6,
            model_prob=0.75,
            data_score=0.75,
            news_score=0.0,
            edge=0.15,
            action="NO",
            outcome="LOSE",
            metadata={"candidate_side": "NO", "yes_outcome": 1.0},
        ),
        DomainReport(
            domain="btc",
            timestamp="2026-05-06T18:23:27Z",
            market_id="btc_5m_up_down",
            target="BTC",
            market_prob=0.5,
            model_prob=0.54,
            data_score=0.0,
            news_score=0.2,
            edge=0.04,
            action="NO",
            outcome="WIN",
            metadata={"candidate_side": "NO", "yes_outcome": 0.0},
        ),
    ]

    expanded = expand_with_baselines(reports)
    paths = write_cw_tables(expanded, tmp_path)

    table1 = pd.read_csv(paths["table1"])
    assert set(table1["method"]) == {"market_only", "data_only", "news_only", "data_news", "proposed_agent"}
    baseline_metrics = table1[table1["method"].isin({"market_only", "data_only", "news_only", "data_news"})]
    assert not baseline_metrics[["hit_rate", "brier"]].isna().any().any()


def test_news_only_baseline_accepts_acy_news_for_all_domains(tmp_path) -> None:
    reports = [
        DomainReport(
            domain=domain,
            timestamp="2026-05-01T00:00:00Z",
            market_id=f"{domain}-market",
            target=f"{domain} news",
            market_prob=0.5,
            model_prob=0.6,
            data_score=0.0,
            news_score=0.25,
            edge=0.1,
            action="YES",
            outcome="WIN",
            metadata={"source": "acy_news", "candidate_side": "YES", "yes_outcome": 1.0},
        )
        for domain in ["btc", "cs2", "weather"]
    ]

    expanded = expand_with_baselines(reports)
    paths = write_cw_tables(expanded, tmp_path)
    table1 = pd.read_csv(paths["table1"])

    news_only = table1[table1["method"] == "news_only"].iloc[0]
    assert news_only["signals"] == 3


def test_news_fusion_attaches_acy_news_without_duplicating_domain_rows() -> None:
    base = [
        DomainReport(
            domain="cs2",
            timestamp="2026-04-03T08:10:00Z",
            market_id="cs2-match",
            target="CS2",
            market_prob=0.55,
            model_prob=0.7,
            data_score=0.7,
            news_score=0.0,
            edge=0.15,
            action="YES",
            outcome="WIN",
            metadata={"source": "poly-ok-check", "candidate_side": "YES", "yes_outcome": 1.0},
        )
    ]
    news = [
        DomainReport(
            domain="cs2",
            timestamp="2026-05-05T12:11:50Z",
            market_id="cs2-news",
            target="Rune Eaters vs Omega",
            market_prob=0.5,
            model_prob=0.56,
            data_score=0.0,
            news_score=0.23,
            edge=0.06,
            action="YES",
            evidence_ref="ev_cs2_001",
            metadata={"source": "acy_news", "candidate_side": "YES"},
        )
    ]

    fused = fuse_domain_news(base, news, standalone_domains={"btc"})

    assert len(fused) == 1
    assert fused[0].news_score == 0.23
    assert fused[0].metadata["news_connected"] is True
    assert fused[0].metadata["news_source"] == "acy_news"
    assert fused[0].metadata["news_signal_market_id"] == "cs2-news"
    assert fused[0].metadata["news_baseline_eligible"] is False


def test_write_cw_tables_exports_action_trace_and_counts(tmp_path) -> None:
    reports = [
        DomainReport(
            domain="cs2",
            timestamp="2026-05-01T00:00:00Z",
            market_id="cs2-hold",
            target="CS2 hold",
            market_prob=0.5,
            model_prob=0.5,
            data_score=0.1,
            news_score=0.0,
            edge=0.0,
            action="HOLD",
            outcome="",
        ),
        _scored_report("cs2", "2026-05-01T00:01:00Z", "cs2-enter", 0.5),
        _scored_report("cs2", "2026-05-01T00:02:00Z", "cs2-maintain", 0.5),
        _scored_report("btc", "2026-05-01T00:03:00Z", "btc-switch", 0.8),
        _scored_report("weather", "2026-05-01T00:04:00Z", "weather-exit", 0.0),
    ]

    paths = write_cw_tables(reports, tmp_path, operating_threshold=2.0)

    trace = pd.read_csv(paths["action_trace"])
    counts = json.loads(paths["action_counts"].read_text(encoding="utf-8"))

    assert list(trace["action_type"]) == ["hold", "enter", "maintain", "switch", "exit"]
    assert counts["hold"] == 1
    assert counts["enter"] == 1
    assert counts["maintain"] == 1
    assert counts["switch"] == 1
    assert counts["exit"] == 1
    assert set(
        [
            "timestamp",
            "cs2_score",
            "btc_score",
            "weather_score",
            "selected_domain",
            "previous_domain",
            "action_type",
            "reason",
        ]
    ).issubset(trace.columns)

    placeholders = paths["placeholders"].read_text(encoding="utf-8")
    assert "- domain_switches: 1" in placeholders
    assert "- exits: 1" in placeholders


def test_score_calibration_handles_zero_only_components(tmp_path) -> None:
    reports = [
        DomainReport(
            domain="btc",
            timestamp="2026-05-01T00:00:00Z",
            market_id="btc-zero",
            target="BTC zero score",
            market_prob=0.5,
            model_prob=0.5,
            data_score=0.0,
            news_score=0.0,
            edge=0.0,
            action="YES",
            outcome="WIN",
            metadata={"candidate_side": "YES", "yes_outcome": 1.0},
        )
    ]

    paths = write_cw_tables(reports, tmp_path)
    diagnostics = pd.read_csv(paths["calibration"])
    btc_data = diagnostics[(diagnostics["domain"] == "btc") & (diagnostics["component"] == "data_score")].iloc[0]
    btc_news = diagnostics[(diagnostics["domain"] == "btc") & (diagnostics["component"] == "news_score")].iloc[0]
    btc_edge = diagnostics[(diagnostics["domain"] == "btc") & (diagnostics["component"] == "edge")].iloc[0]

    assert btc_data["p95_scale"] == 0.0
    assert btc_news["p95_scale"] == 0.0
    assert btc_edge["p95_scale"] == 0.0
    assert btc_data["positive_count"] == 0


def _scored_report(domain: str, timestamp: str, market_id: str, value: float) -> DomainReport:
    return DomainReport(
        domain=domain,
        timestamp=timestamp,
        market_id=market_id,
        target=market_id,
        market_prob=0.4,
        model_prob=0.8,
        data_score=value,
        news_score=value,
        edge=value,
        action="YES",
        outcome="WIN",
        metadata={"candidate_side": "YES", "yes_outcome": 1.0},
    )
