# Session Handoff: DIA-CW Evaluation Work

Last updated: 2026-05-09

This file is the first thing to read when resuming the work in a new session.
Main repository mirror:

```text
D:\Polyquant\github_upload
remote: https://github.com/Leroyyyyyyyyy/DIA-CW.git
latest completed evaluation commit before this handoff:
9a18e87 Fuse DIA news into all evaluation domains
```

Local implementation workspace used during development:

```text
D:\Polyquant\poly-ok-check
```

## Current State

The evaluation pipeline is reproducible and the latest `cw_final` output exists.
The current `cw_final` is still candidate-level/fixed-stake evaluation, not yet
category-policy adjusted.

Current verification from `github_upload\poly-ok-check`:

```text
python -m pytest research\tests -q
58 passed

python -m research.run.run_cw_experiment --config research\config\cw_experiment.yaml --out-dir research\runs\cw_final
loaded_reports=3025
```

Current Table I proposed-agent values:

```text
signals=140
coverage=0.2314
hit_rate=0.4
brier=0.315939
p_l=-49.759052
```

Current Table II proposed-agent values:

```text
cs2:     signals=10,  hit_rate=0.5,    brier=0.16036,  p_l=-0.784279
btc:     signals=24,  hit_rate=0.4583, brier=0.250215, p_l=-2.0
weather: signals=106, hit_rate=0.3774, brier=0.345498, p_l=-46.974772
```

## What Has Been Done

1. Made evaluation self-contained enough for paper tables:
   - Current source of paper numbers is `research/runs/cw_final/`.
   - The runner is `research/run/run_cw_experiment.py`.
   - The config is `research/config/cw_experiment.yaml`.

2. Added BTC rolling multi-market evaluation:
   - BTC is no longer a single `btc_5m_up_down` row.
   - It now has 24 rolling 5-minute markets.
   - Signal snapshot:
     `research/data/external/dia_btc/signals_multi_market.csv`
   - Outcome snapshot:
     `research/data/external/outcomes/btc_5m_outcome_multi_market.csv`
   - Generator:
     `research/run/build_btc_multi_market_signals.py`
   - Details are documented in:
     `docs/btc_multi_market_update.md`.

3. Connected DIA news to all three domains:
   - BTC remains standalone `acy_news` rows.
   - CS2 keeps its CS2 timeline/data rows, with DIA CS2 news fused into each row.
   - Weather keeps its Weather rows, with DIA Weather news fused into each row.
   - Fusion module:
     `research/evaluation/news_fusion.py`
   - News snapshots:
     `research/data/external/dia_cs2/`
     `research/data/external/dia_weather/`
   - Current `unified_domain_reports.csv` has:

```text
btc:     news_connected=24/24,   news_score>0=24/24
cs2:     news_connected=19/19,   news_score>0=19/19
weather: news_connected=562/562, news_score>0=562/562
```

4. Pushed the latest completed work:
   - `5c49dd9 Add BTC rolling multi-market evaluation`
   - `9a18e87 Fuse DIA news into all evaluation domains`

## Root Cause Of Low PnL

The low PnL is not mainly caused by BTC or missing news.
The main issue is Weather evaluation granularity.

Weather has:

```text
research/data/external/weather/signals.csv             562 candidate rows
research/data/external/weather/backtest_trades.csv       3 executed trades
```

Current `cw_final` reads `signals.csv`, so it treats candidate rows as executed
fixed-stake trades. This creates repeated exposure:

```text
Weather 21c NO: 52 acted rows, all LOSE, PnL=-52
Weather 19c YES: 13 acted rows, all LOSE, PnL=-13
```

This explains almost all of the overall `p_l=-49.759052`.

Important: Weather should be evaluated at execution/trade level for Table I-II
PnL, not by counting every candidate signal row as a separate executed trade.

## Next Plan: Category Policy Adjustment

The next implementation should add category-specific policy before baseline
expansion and table writing.

Chosen user decisions:

```text
policy-adjusted outputs should overwrite research/runs/cw_final/
Weather should use trades_csv execution level
```

Recommended implementation:

1. Add `research/evaluation/category_policy.py`.

2. Update `research/run/run_cw_experiment.py` flow to:

```text
load_reports
-> fuse_domain_news
-> apply_category_policy
-> expand_with_baselines
-> write_unified_reports / write_cw_tables
```

3. Update `research/config/cw_experiment.yaml` with a `policy` block:

```json
"policy": {
  "enabled": true,
  "btc": {
    "market_type": "rolling_binary",
    "min_edge": 0.002,
    "min_news_score": 0.01,
    "max_trades_per_market": 1
  },
  "cs2": {
    "market_type": "single_match_binary",
    "max_trades_per_market_side": 1,
    "switch_buffer": 0.03
  },
  "weather": {
    "market_type": "categorical_weather",
    "execution_source": "trades_csv",
    "max_trades_per_event": 3,
    "max_trades_per_market_side": 1
  }
}
```

4. Weather policy behavior:
   - Use `research/data/external/weather/backtest_trades.csv` as acted rows.
   - Keep candidate tables only as provenance/diagnostics.
   - Expected Weather acted signals after policy: 3.
   - Expected overall PnL should move away from about `-49` because repeated
     candidate exposure is removed.

5. BTC policy behavior:
   - Keep 24 rolling BTC markets.
   - Do not set `min_edge` above `0.0025` unless intentionally accepting zero
     BTC signals, because current BTC edge is only `0.0025`.

6. CS2 policy behavior:
   - Same `market_id + side` should only be entered once.
   - Opposite-side switch should require `new_edge >= current_edge + 0.03`.

7. Add diagnostics:
   - Write `research/runs/cw_final/policy_diagnostics.csv`.
   - Include original action, policy action, and reason, such as:
     `weather_execution_not_in_trades`,
     `cs2_position_already_open`,
     `btc_below_news_threshold`.

## Acceptance Checks For Next Session

After implementing category policy, run:

```powershell
cd D:\Polyquant\poly-ok-check
$env:PYTHONPATH="."
python -m pytest research\tests -q
python -m research.run.run_cw_experiment --config research\config\cw_experiment.yaml --out-dir research\runs\cw_final
```

Required checks:

```text
Weather Table II signals should be 3.
BTC Table II signals should remain 24 under the default policy.
CS2 should no longer count repeated same-side entries as independent trades.
unified_domain_reports.csv should still show all three domains with news_connected=true.
Table I/II PnL should no longer be dominated by repeated Weather candidate rows.
```

Then sync the same changed files to:

```text
D:\Polyquant\github_upload\poly-ok-check
```

Run the same tests there, commit, and push to:

```text
https://github.com/Leroyyyyyyyyy/DIA-CW.git
```

## Do Not Redo Unless Needed

- Do not re-fetch BTC outcomes unless changing BTC decision windows.
- Do not remove DIA CS2/Weather news snapshots; they are now part of the
  reproducible input set.
- Do not claim PMXT execution-level PnL is connected here. This remains unified
  fixed-stake evaluation with category policy.
- Do not treat `domains=["btc","cs2","weather"]` alone as evidence of news
  integration; verify `news_connected=true` and `news_score>0` in
  `unified_domain_reports.csv`.
