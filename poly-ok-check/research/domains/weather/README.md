# Weather domain integration point

The source module was developed outside this repository. For the final
submission, this folder documents the integration point and the expected weather
signal/backtest outputs.

The domain should provide weather signal/backtest outputs and let
`research.adapters.weather_adapter` convert them into `DomainReport` rows.

Weather-specific backtest files remain supporting evidence; final paper metrics
are produced by the shared evaluation layer.

