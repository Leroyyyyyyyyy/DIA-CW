# Polyquant final repository structure

This document defines the target merge shape for the coursework repository.

## Decision

`poly-ok-check` is the final integration repository. The existing backtest stack in
`research/backtest` remains the primary backtest system because it supports market
replay, order and fill simulation, portfolio state, fees, slippage, PnL, and run
summaries.

The sibling folders `acy_news(1)` and `Weather` are treated as domain modules:

- `acy_news(1)` owns news evidence collection and signal generation.
- `Weather` owns weather forecast modelling and weather-specific signal logic.
- `poly-ok-check` owns final integration, common adapters, main backtest, and paper
  result aggregation.

## Target layout

```text
poly-ok-check/
├─ src/                         # Rust Market Data Hub and runtime contracts
├─ tests/                       # Rust contract/runtime tests
├─ research/
│  ├─ adapters/                 # Convert each domain output to DomainReport
│  ├─ backtest/                 # Primary backtest system
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

## Merge rule

Do not make three independent backtest systems compete in the final submission.
Each domain may keep its own research scripts, but final paper metrics must pass
through the common `DomainReport` format and the shared evaluation layer.

## Main command

The final aggregation entrypoint is:

```powershell
cd D:\Polyquant\poly-ok-check
$env:PYTHONPATH="D:\Polyquant\poly-ok-check"
python -m research.run.run_cw_experiment `
  --config research\config\cw_experiment.yaml `
  --out-dir research\runs\cw_final
```

