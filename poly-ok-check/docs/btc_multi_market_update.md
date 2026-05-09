# BTC Multi-Market Evaluation Update

## Summary

The BTC evaluation no longer uses a single synthetic market only. It now uses
24 reproducible rolling 5-minute BTC up/down markets generated from the DIA BTC
news stance snapshot.

This is still the unified coursework evaluation layer, not a PMXT execution
backtest and not a live Polymarket BTC market universe.

## What Changed

- Added a BTC rolling-window signal generator:
  `research/run/build_btc_multi_market_signals.py`
- Added the generated BTC signal snapshot:
  `research/data/external/dia_btc/signals_multi_market.csv`
- Added the generated BTC outcome snapshot:
  `research/data/external/outcomes/btc_5m_outcome_multi_market.csv`
- Updated `research/config/cw_experiment.yaml` to read the multi-market BTC
  signal and outcome snapshots.
- Regenerated `research/runs/cw_final/` tables and placeholders.
- Added tests for BTC multi-market signal expansion and multi-market outcome
  generation.

## BTC Market Definition

The new BTC markets are rolling 5-minute up/down windows:

```text
start: 2026-05-06T18:25:00Z
count: 24
step_minutes: 5
horizon_minutes: 5
market_id format: btc_5m_up_down_YYYYMMDDTHHMMSSZ
```

Each generated row keeps provenance metadata:

```text
source_signal_market_id=btc_5m_up_down
source_signal_as_of=2026-05-06T18:23:27.168676Z
rule=rolling 5-minute BTC up/down windows from one DIA news stance
```

The BTC outcome rule is unchanged:

```text
YES wins if end_price > start_price over the 5-minute window.
Otherwise NO wins.
```

The current outcome snapshot has 24 rows and was fetched from Binance
`BTCUSDT` 1-minute klines.

## Current cw_final Results

After regeneration, `research/runs/cw_final/table2_by_domain.csv` reports:

```text
BTC signals: 24
BTC unique markets: 24
BTC hit_rate: 0.4583
BTC brier: 0.250215
BTC p_l: -2.0
BTC share: 0.1714
```

Overall proposed-agent values in `paper_placeholders.md`:

```text
proposed_selected: 140
available_decision_windows: 605
proposed_coverage_pct: 23.14
proposed_hit_rate_pct: 40.00
proposed_brier: 0.315939
proposed_p_l: -49.759052
```

Table III still has empty hit rate and Brier for thresholds `0.75` and `1.0`
because those thresholds select zero signals. This is expected and is not a
missing-data issue.

## Reproduction Commands

From `poly-ok-check`:

```powershell
$env:PYTHONPATH="."
python -m research.run.build_btc_multi_market_signals `
  --source research\data\external\dia_btc\signals.csv `
  --out research\data\external\dia_btc\signals_multi_market.csv `
  --start 2026-05-06T18:25:00Z `
  --count 24 `
  --step-minutes 5 `
  --horizon-minutes 5

python -m research.run.fetch_btc_5m_outcomes `
  --signals-csv research\data\external\dia_btc\signals_multi_market.csv `
  --out research\data\external\outcomes\btc_5m_outcome_multi_market.csv `
  --horizon-minutes 5

python -m research.run.run_cw_experiment `
  --config research\config\cw_experiment.yaml `
  --out-dir research\runs\cw_final

python -m pytest research\tests -q
```

Latest verification:

```text
loaded_reports=3025
57 passed
```
