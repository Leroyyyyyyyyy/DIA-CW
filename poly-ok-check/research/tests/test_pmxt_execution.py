from __future__ import annotations

import pandas as pd

from research.evaluation.cw_tables import write_cw_tables
from research.evaluation.pmxt_execution import apply_pmxt_execution, write_pmxt_execution_diagnostics
from research.schemas.domain_report import DomainReport


def test_pmxt_execution_overlays_pnl_and_metadata(tmp_path) -> None:
    artifact = tmp_path / "pmxt_fills.csv"
    artifact.write_text(
        "\n".join(
            [
                "domain,timestamp,market_id,side,pnl,outcome,fill_price,quantity",
                "cs2,2026-04-03T08:30:39Z,cs2-run2,YES,2.75,WIN,0.42,5",
            ]
        ),
        encoding="utf-8",
    )
    reports = [
        DomainReport(
            domain="cs2",
            timestamp="2026-04-03T08:30:39Z",
            market_id="cs2-run2",
            target="CS2",
            market_prob=0.55,
            model_prob=0.7,
            data_score=0.7,
            news_score=0.2,
            edge=0.15,
            action="YES",
            outcome="WIN",
        )
    ]

    adjusted, diagnostics = apply_pmxt_execution(
        reports,
        pmxt_config={"enabled": True, "artifacts": [{"path": artifact, "format": "csv"}]},
        base_dir=tmp_path,
        config_dir=tmp_path,
    )

    assert adjusted[0].pnl == 2.75
    assert adjusted[0].metadata["pmxt_execution_matched"] is True
    assert adjusted[0].metadata["pmxt_fill_price"] == 0.42
    assert {row["status"] for row in diagnostics} == {"loaded", "matched"}

    paths = write_cw_tables(adjusted, tmp_path / "tables")
    table1 = pd.read_csv(paths["table1"])
    proposed = table1[table1["method"] == "proposed_agent"].iloc[0]
    assert proposed["p_l"] == 2.75


def test_pmxt_execution_missing_optional_artifact_is_noop(tmp_path) -> None:
    reports = [
        DomainReport(
            domain="btc",
            timestamp="2026-05-06T18:25:00Z",
            market_id="btc-1",
            target="BTC",
            market_prob=0.5,
            model_prob=0.5025,
            data_score=0.0,
            news_score=0.012,
            edge=0.0025,
            action="NO",
            outcome="WIN",
        )
    ]

    adjusted, diagnostics = apply_pmxt_execution(
        reports,
        pmxt_config={
            "enabled": True,
            "required": False,
            "artifacts": [{"path": tmp_path / "missing.csv", "format": "csv"}],
        },
        base_dir=tmp_path,
        config_dir=tmp_path,
    )

    assert adjusted == reports
    assert [row["status"] for row in diagnostics] == ["missing", "no_execution_rows"]

    path = write_pmxt_execution_diagnostics(diagnostics, tmp_path / "pmxt_diagnostics.csv")
    assert path.exists()
