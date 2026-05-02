# Polyquant final repository structure

This document defines the target shape for the coursework repository and keeps it
aligned with `main.pdf`.

## Decision

The paper describes a reactive cross-domain Polymarket agent, not three
independent backtest systems. The repository is therefore split into two layers:

- `vendor/prediction-market-backtesting` is the PMXT / Nautilus replay and
  execution layer. It owns market discovery, `replays.json`, historical L2 data
  loading, fills, PnL, and HTML reports.
- `poly-ok-check` is the final integration and evaluation layer. It owns the
  common `DomainReport` schema, adapters, paper Table I-IV aggregation, and
  reproducible experiment runner.

The sibling folders `acy_news(1)` and `Weather` are not copied wholesale into
the final repository at this stage. They are treated as domain signal producers:

- `acy_news(1)` owns news evidence collection and Bitcoin/news signal generation.
- `Weather` owns weather forecast modelling and weather signal generation.
- Dld owns the PMXT backtest workflow, CS2 integration, and final paper result
  aggregation.

## Target layout

```text
poly-ok-check/
├─ src/                         # Rust Market Data Hub and runtime contracts
├─ tests/                       # Rust contract/runtime tests
├─ research/
│  ├─ adapters/                 # Convert each domain output to DomainReport
│  ├─ backtest/                 # Lightweight research support, not the PMXT execution source
│  ├─ config/                   # Final experiment config
│  ├─ domains/
│  │  ├─ cs2/                   # Dld-owned CS2 domain notes/code
│  │  ├─ news/                  # Integration point for acy_news(1)
│  │  └─ weather/               # Integration point for Weather
│  ├─ evaluation/               # Paper Table I-IV aggregation
│  ├─ run/                      # Reproducible command entrypoints
│  └─ schemas/                  # Shared Python data contracts
└─ docs/
   ├─ repo_structure.md
   ├─ responsibilities.md
   └─ paper_fill_plan.md
```

PMXT execution files:

```text
vendor/prediction-market-backtesting/
├─ scripts/polymarket_find_markets.py
├─ backtests/private/replays.json
├─ backtests/private/weather_backtest.py
├─ strategies/
└─ output/                       # local generated reports, not committed
```

## Paper alignment

The repository maps to the paper as follows:

- Section III System Design: three domain modules, shared `DomainReport`, and
  reactive selector.
- Section IV Implementation: PMXT replay layer plus reproducible CSV/JSONL
  outputs.
- Section V Methodology: market-only, data-only, news-only, data-plus-news, and
  proposed-agent conditions.
- Section VI Results: `table1_overall.csv`, `table2_by_domain.csv`,
  `table3_threshold.csv`, `table4_examples.csv`.
- Section VII Discussion: `paper_placeholders.md` supplies highest/lowest/strongest
  domain statements.

## Merge rule

Do not make three independent backtest systems compete in the final submission.
Each domain may keep its own research scripts, but final paper metrics must pass
through the common `DomainReport` format and the shared evaluation layer.

For execution-level PnL, use the PMXT / Nautilus workflow described in
`D:\Polyquant\backtestreadme.md`.

## Main command

The final aggregation entrypoint is:

```powershell
cd D:\Polyquant\poly-ok-check
$env:PYTHONPATH="D:\Polyquant\poly-ok-check"
python -m research.run.run_cw_experiment `
  --config research\config\cw_experiment.yaml `
  --out-dir research\runs\cw_final
```
