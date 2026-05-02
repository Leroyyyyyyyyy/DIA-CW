# Polyquant 代码责任分配

## Dld

负责代码：
- `D:\Polyquant\backtestreadme.md`
- `D:\Polyquant\vendor\prediction-market-backtesting\scripts\polymarket_find_markets.py`
- `D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\replays.json`
- `D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\weather_backtest.py`
- `research/backtest/`
- `research/adapters/cs2_adapter.py`
- `research/evaluation/`
- `research/run/run_cw_experiment.py`
- `research/config/cw_experiment.yaml`
- `research/domains/cs2/`

负责结果：
- CS2 signal/report。
- 按 `D:\Polyquant\backtestreadme.md` 跑 PMXT / Nautilus 主回测。
- 主回测的 PMXT replay、PnL、fills、summary、HTML report。
- 统一 evaluation 输出。
- Table I、Table III。
- Table II 的生成和 CS2 行检查。
- Table IV 的统一整理，以及 CS2 / switch / exit 样例。

## `acy_news(1)` 负责人

负责代码：
- `D:\Polyquant\acy_news(1)\dia\polymarket_signal_agent\`
- `D:\Polyquant\acy_news(1)\dia\outputs...\`

负责结果：
- news hub。
- BTC/news signal。
- evidence log。
- Table II 中 news/BTC 行的检查。
- Table IV 中 news/BTC 代表信号。

必须稳定交付：
```text
signals.csv
signals.jsonl
evidence.jsonl
```

说明：`acy_news(1)` 的 `backtest` 不作为最终 PnL backtest，只作为 historical signal collection。

## `Weather` 负责人

负责代码：
- `D:\Polyquant\Weather\Weather\`
- `D:\Polyquant\Weather\Weather\data\processed\`

负责结果：
- weather forecast model。
- weather market signal。
- weather-specific backtest evidence。
- Table II 中 weather 行的检查。
- Table IV 中 weather 代表信号。

必须稳定交付：
```text
backtest_signal_table.csv
backtest_trades.csv
backtest_summary.csv
```

说明：Weather 可以保留自己的 backtest/evidence，但最终论文 Table I-III 的统一数字仍从 Dld 的 evaluation 输出。

## 组长 / 论文负责人

负责内容：
- Prism / LaTeX 主文档。
- 作者信息、学号、邮箱。
- 最终 PDF。
- 根据 `research/runs/cw_final/paper_placeholders.md` 和 Table I-IV CSV 填论文 `[P]`。
- 确认每个人在 VIII. AUTHOR CONTRIBUTIONS 中认领自己的贡献。
