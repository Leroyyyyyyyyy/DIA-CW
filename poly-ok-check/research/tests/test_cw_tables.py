from __future__ import annotations

import pandas as pd

from research.evaluation.baselines import expand_with_baselines
from research.evaluation.cw_tables import write_cw_tables, write_unified_reports
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
