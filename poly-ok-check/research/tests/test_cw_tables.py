from __future__ import annotations

import pandas as pd

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

