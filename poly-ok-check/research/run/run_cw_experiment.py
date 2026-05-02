from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from research.adapters.acy_news_adapter import load_acy_news_reports
from research.adapters.cs2_adapter import load_cs2_reports
from research.adapters.weather_adapter import load_weather_reports
from research.evaluation.cw_tables import write_cw_tables, write_unified_reports
from research.schemas.domain_report import DomainReport


def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    config = _load_config(config_path)
    reports = load_reports(config, base_dir=Path.cwd(), config_dir=config_path.parent)
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

    acy = inputs.get("acy_news", {})
    if acy.get("enabled", False):
        reports.extend(
            load_acy_news_reports(
                signals_csv=_resolve(acy["signals_csv"], base_dir, config_dir),
                evidence_jsonl=_resolve_optional(acy.get("evidence_jsonl"), base_dir, config_dir),
                domains=list(acy.get("domains", [])) or None,
                market_prob_default=float(acy.get("market_prob_default", 0.5)),
            )
        )

    weather = inputs.get("weather", {})
    if weather.get("enabled", False):
        reports.extend(
            load_weather_reports(
                trades_csv=_resolve_optional(weather.get("trades_csv"), base_dir, config_dir),
                signal_table_csv=_resolve_optional(weather.get("signal_table_csv"), base_dir, config_dir),
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Aggregate Polyquant coursework domain outputs into paper tables.")
    parser.add_argument("--config", default="research/config/cw_experiment.yaml")
    parser.add_argument("--out-dir", default="research/runs/cw_final")
    return parser.parse_args()


if __name__ == "__main__":
    main()

