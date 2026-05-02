# Weather domain integration point

The source module is currently kept outside this repository at:

```text
D:\Polyquant\Weather
```

For the final merge, this domain should provide weather signal/backtest outputs
and let `research.adapters.weather_adapter` convert them into `DomainReport`
rows.

Weather-specific backtest files remain supporting evidence; final paper metrics
are produced by the shared evaluation layer.

