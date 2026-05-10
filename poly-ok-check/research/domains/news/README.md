# News domain integration point

The source module was developed outside this repository. For the final
submission, this folder documents the integration point and the expected
signal/evidence outputs.

For the final merge, this domain should provide signal/evidence files and let
`research.adapters.acy_news_adapter` convert them into `DomainReport` rows.

The adapter supports multi-domain news output directories:

```text
outputs_btc_window/signals.csv
outputs_btc_window/evidence.jsonl
outputs_cs2_window/signals.csv
outputs_cs2_window/evidence.jsonl
outputs_weather_window/signals.csv
outputs_weather_window/evidence.jsonl
```

When these folders are configured through `news_output_dirs`, available rows are
loaded as BTC, CS2, and Weather news signals. Missing folders are skipped with a
warning, and the legacy single `signals_csv`/`evidence_jsonl` BTC path remains a
fallback for old experiment configs.

This domain is not the primary backtest system.
