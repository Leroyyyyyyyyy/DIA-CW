from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.adapters.acy_news_adapter import load_acy_news_reports
from research.adapters.cs2_adapter import load_cs2_reports
from research.adapters.weather_adapter import load_weather_reports
from research.evaluation.baselines import expand_with_baselines
from research.evaluation.cw_tables import write_cw_tables, write_unified_reports
from research.evaluation.news_fusion import fuse_domain_news
from research.schemas.domain_report import DomainReport


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = _load_config(config_path)
    proposed_reports = load_reports(config, base_dir=Path.cwd(), config_dir=config_path.parent)
    reports = expand_with_baselines(proposed_reports)
    out_dir = Path(args.out_dir)
    unified_path = write_unified_reports(reports, out_dir / "unified_domain_reports.csv")
    table_paths = write_cw_tables(
        reports,
        out_dir=out_dir,
        threshold_grid=config.get("threshold_grid", [0.25, 0.5, 0.75, 1.0]),
        operating_threshold=float(config.get("operating_threshold", 0.5)),
    )

    print(f"loaded_reports={len(reports)}")
    print(f"unified_reports={unified_path}")
    for name, path in table_paths.items():
        print(f"{name}={path}")


def load_reports(config: dict[str, Any], base_dir: Path, config_dir: Path) -> list[DomainReport]:
    inputs = config.get("inputs", {})
    reports: list[DomainReport] = []
    news_reports: list[DomainReport] = []

    acy = inputs.get("acy_news", {})
    if acy.get("enabled", False):
        news_reports = load_acy_news_reports(
            signals_csv=_resolve_optional(acy.get("signals_csv"), base_dir, config_dir),
            evidence_jsonl=_resolve_optional(acy.get("evidence_jsonl"), base_dir, config_dir),
            news_inputs=_resolve_news_inputs(list(acy.get("news_inputs", [])), base_dir, config_dir),
            news_output_dirs=[
                _resolve_output_dir(path, base_dir, config_dir) for path in list(acy.get("news_output_dirs", []))
            ],
            domains=list(acy.get("domains", [])) or None,
            market_prob_default=float(acy.get("market_prob_default", 0.5)),
            outcome_csv=_resolve_optional(acy.get("outcome_csv"), base_dir, config_dir),
        )
        standalone_domains = {str(domain).lower() for domain in acy.get("standalone_domains", ["btc"])}
        reports.extend(report for report in news_reports if report.domain.lower() in standalone_domains)

    weather = inputs.get("weather", {})
    if weather.get("enabled", False):
        reports.extend(
            load_weather_reports(
                signals_csv=_resolve_optional(weather.get("signals_csv"), base_dir, config_dir),
                trades_csv=_resolve_optional(weather.get("trades_csv"), base_dir, config_dir),
                signal_table_csv=_resolve_optional(weather.get("signal_table_csv"), base_dir, config_dir),
                actual_outcomes=dict(weather.get("actual_outcomes", {})),
            )
        )

    cs2 = inputs.get("cs2", {})
    if cs2.get("enabled", False):
        reports.extend(
            load_cs2_reports(
                signal_csv=_resolve(cs2["signal_csv"], base_dir, config_dir),
                timeline_csv=_resolve_optional(cs2.get("timeline_csv"), base_dir, config_dir),
                market_id=str(cs2.get("market_id", "cs2")),
                target=str(cs2.get("target", "CS2 match")),
                yes_outcome=cs2.get("yes_outcome"),
                market_prob_default=float(cs2.get("market_prob_default", 0.5)),
            )
        )

    if acy.get("enabled", False) and acy.get("fuse_into_domain_reports", True):
        standalone_domains = {str(domain).lower() for domain in acy.get("standalone_domains", ["btc"])}
        reports = fuse_domain_news(reports, news_reports, standalone_domains=standalone_domains)

    return reports


def _load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{path} is parsed as JSON-compatible YAML. Keep this file valid JSON or install a YAML parser."
        ) from exc


def _resolve(value: str | Path, base_dir: Path, config_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    from_base = base_dir / path
    if from_base.exists():
        return from_base
    return config_dir / path


def _resolve_optional(value: str | Path | None, base_dir: Path, config_dir: Path) -> Path | None:
    if not value:
        return None
    return _resolve(value, base_dir, config_dir)


def _resolve_output_dir(value: str | Path, base_dir: Path, config_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    from_base = base_dir / path
    if from_base.exists():
        return from_base
    from_config = config_dir / path
    if from_config.exists():
        return from_config
    return from_base


def _resolve_news_inputs(news_inputs: list[dict[str, Any]], base_dir: Path, config_dir: Path) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for item in news_inputs:
        copy = dict(item)
        if copy.get("signals_path"):
            copy["signals_path"] = _resolve(copy["signals_path"], base_dir, config_dir)
        if copy.get("signals_csv"):
            copy["signals_csv"] = _resolve(copy["signals_csv"], base_dir, config_dir)
        if copy.get("evidence_path"):
            copy["evidence_path"] = _resolve(copy["evidence_path"], base_dir, config_dir)
        if copy.get("evidence_jsonl"):
            copy["evidence_jsonl"] = _resolve(copy["evidence_jsonl"], base_dir, config_dir)
        resolved.append(copy)
    return resolved


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Polyquant coursework domain outputs into paper tables.")
    parser.add_argument("--config", default="research/config/cw_experiment.yaml")
    parser.add_argument("--out-dir", default="research/runs/cw_final")
    return parser.parse_args()


if __name__ == "__main__":
    main()
