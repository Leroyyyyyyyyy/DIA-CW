# Multi-Domain News Integration Update

## Summary

The `acy_news` adapter already supported multi-domain inputs, but `cw_final`
previously only passed BTC news into the experiment config. This update makes
news integration explicit for all three domains in the generated evaluation.

## Current Integration Contract

- BTC remains a standalone news-driven domain using the rolling 5-minute BTC
  signal snapshot.
- CS2 keeps its existing timeline/data rows, with DIA CS2 news fused into each
  CS2 report as metadata and `news_score`.
- Weather keeps its existing Weather forecast/backtest rows, with DIA Weather
  news fused into each Weather report as metadata and `news_score`.

The fusion does not create extra CS2/Weather news-only rows without outcomes.
Instead, it attaches news evidence to the existing domain reports so the final
tables remain outcome-complete.

## Snapshot Inputs

```text
research/data/external/dia_btc/signals_multi_market.csv
research/data/external/dia_btc/evidence.jsonl
research/data/external/dia_cs2/signals.csv
research/data/external/dia_cs2/evidence.jsonl
research/data/external/dia_weather/signals.csv
research/data/external/dia_weather/evidence.jsonl
```

## Verification

The regenerated `research/runs/cw_final/unified_domain_reports.csv` now has:

```text
btc:     news_connected=24/24,   news_score>0=24/24
cs2:     news_connected=19/19,   news_score>0=19/19
weather: news_connected=562/562, news_score>0=562/562
```

Latest checks:

```text
loaded_reports=3025
58 passed
```

## Notes

The proposed-agent actions and PnL are intentionally not changed by this fusion
step. It proves news is available to every market category and affects
opportunity scoring through `news_score`, while avoiding duplicate CS2/Weather
rows with missing outcomes.
