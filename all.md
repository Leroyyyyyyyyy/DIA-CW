# DIA-CW / Polyquant 当前交接状态

> 切换对话或恢复工作时先读本文件。每次路径、数据、结果、GitHub 状态变化后都要更新。

## 1. 总判断

- 最终集成仓库：`D:\Polyquant\poly-ok-check`
- GitHub 上传目录：`D:\Polyquant\github_upload`
- GitHub remote：`https://github.com/Leroyyyyyyyyy/DIA-CW.git`
- 论文 PDF：`D:\Polyquant\main.pdf`
- 论文 `[P]`：共 123 个，集中在 page 6-8，主要是 Table I-IV 和 Discussion。

核心原则：
- 不把 `dia` / `Weather(2)` 整包 merge 进主仓库。
- `dia` 和 `Weather(2)` 只作为 domain signal/evidence module。
- `poly-ok-check` 负责统一 schema、adapter、evaluation、Table I-IV。
- PMXT / Nautilus 负责真正盘口 replay、fills、PnL；当前 `cw_final` 是统一 evaluation 层结果。
- 最终论文数值必须由统一 evaluation 生成，不能手工拼三套系统。

## 2. 论文框架对齐

论文主线：

```text
CS2 / BTC-news / Weather
-> DomainReport
-> opportunity score
-> reactive selector
-> unified evaluation
-> Table I-IV + paper placeholders
```

统一字段：

```text
method,domain,timestamp,market_id,target,market_prob,model_prob,
data_score,news_score,edge,action,outcome,evidence_ref,pnl,metadata
```

论文表格对应输出：

```text
Table I   -> research\runs\cw_final\table1_overall.csv
Table II  -> research\runs\cw_final\table2_by_domain.csv
Table III -> research\runs\cw_final\table3_threshold.csv
Table IV  -> research\runs\cw_final\table4_examples.csv
[P]       -> research\runs\cw_final\paper_placeholders.md
```

## 3. 当前关键路径

主 evaluation：

```text
D:\Polyquant\poly-ok-check\research\config\cw_experiment.yaml
D:\Polyquant\poly-ok-check\research\run\run_cw_experiment.py
D:\Polyquant\poly-ok-check\research\adapters\
D:\Polyquant\poly-ok-check\research\evaluation\cw_tables.py
D:\Polyquant\poly-ok-check\research\schemas\domain_report.py
```

PMXT / Nautilus 回测参考：

```text
D:\Polyquant\backtestreadme.md
D:\Polyquant\vendor\prediction-market-backtesting
D:\Polyquant\vendor\prediction-market-backtesting\scripts\polymarket_find_markets.py
D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\replays.json
D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\weather_backtest.py
D:\Polyquant\vendor\prediction-market-backtesting\strategies\ema_crossover.py
```

运行统一 evaluation：

```powershell
cd D:\Polyquant\poly-ok-check
$env:PYTHONPATH="D:\Polyquant\poly-ok-check"
python -m research.run.run_cw_experiment `
  --config D:\Polyquant\poly-ok-check\research\config\cw_experiment.yaml `
  --out-dir D:\Polyquant\poly-ok-check\research\runs\cw_final
```

## 4. dia / BTC-news 状态

路径：

```text
D:\Polyquant\dia\dia
```

当前已接入文件：

```text
D:\Polyquant\dia\dia\outputs_btc_window\signals.csv
D:\Polyquant\dia\dia\outputs_btc_window\signals.jsonl
D:\Polyquant\dia\dia\outputs_btc_window\evidence.jsonl
```

当前状态：
- 已运行非 sample live pipeline：`python -m dia.run_news_pipeline --domain btc`
- 输出：1 个 BTC signal，15 条 evidence。
- evidence 来源已变成真实 RSS，例如 `coindesk` / `cointelegraph`，不再是 `SampleCoinDesk` / `example.com`。
- unified evaluation 已能读入 BTC，并生成 `domain=btc` 的 `DomainReport`。
- 当前 BTC 仍缺 resolved outcome，所以 BTC 的 hit rate / Brier / PnL 还不能最终定稿。

最近 BTC 接入检查：

```text
btc_reports = 1
action = NO
model_prob = 0.4975
market_prob = 0.5
evidence_ref = Eric Trump takes shot at JPMorgan rethinking bitcoin after 'crapping' on asset
```

注意：
- 如果论文需要固定历史窗口，不能只依赖 live RSS；需要 dia 负责人提供可复现的历史 BTC/news 输出，或把 RSS 快照一起保存。
- 之前 sample 已备份在 `outputs_btc_window_sample_backup`。

## 5. Weather(2) 状态

路径：

```text
D:\Polyquant\Weather(2)\Weather
```

当前已接入文件：

```text
D:\Polyquant\Weather(2)\Weather\data\processed\signals.csv
D:\Polyquant\Weather(2)\Weather\data\processed\evidence.jsonl
D:\Polyquant\Weather(2)\Weather\data\processed\backtest_signal_table.csv
D:\Polyquant\Weather(2)\Weather\data\processed\backtest_trades.csv
D:\Polyquant\Weather(2)\Weather\data\processed\backtest_summary.csv
```

当前状态：
- `signals.csv`：562 rows，作为 Weather 主 decision windows。
- `backtest_trades.csv`：3 trades，只作为成交 / PnL 补充，不能单独算 coverage。
- `weather_adapter.py` 已优先读取 `signals_csv`，再 fallback 到 `signal_table_csv` / `trades_csv`。
- Weather action 已规范化：`enter -> YES/NO`，`hold -> HOLD`。

最近 Weather 接入检查：

```text
weather_reports = 562
weather_actions = NO: 92, HOLD: 456, YES: 14
weather_known_outcomes = 3
weather_methods = proposed_agent
```

## 6. 当前已完成改动

已完成：
- `cw_experiment.yaml` 已指向新版 `dia` 和 `Weather(2)` 路径。
- `weather_adapter.py` 已支持并优先读取 Weather 统一 `signals.csv`。
- `run_cw_experiment.py` 已向 Weather adapter 传入 `signals_csv`。
- `research/tests/test_domain_adapters.py` 已覆盖 Weather 优先读取 signals 的逻辑。
- 已重新运行 `compileall`，无语法错误。
- 已重新运行统一 evaluation，输出目录：`D:\Polyquant\poly-ok-check\research\runs\cw_final`

当前 `cw_experiment.yaml` 指向：

```text
D:/Polyquant/dia/dia/outputs_btc_window/signals.csv
D:/Polyquant/dia/dia/outputs_btc_window/evidence.jsonl
D:/Polyquant/Weather(2)/Weather/data/processed/signals.csv
D:/Polyquant/Weather(2)/Weather/data/processed/evidence.jsonl
D:/Polyquant/Weather(2)/Weather/data/processed/backtest_signal_table.csv
D:/Polyquant/Weather(2)/Weather/data/processed/backtest_trades.csv
D:/Polyquant/Weather(2)/Weather/data/processed/backtest_summary.csv
```

当前 evaluation 输出：

```text
loaded_reports = 582
domains = weather: 562, cs2: 19, btc: 1
proposed_selected = 117
available_decision_windows = 582
proposed_coverage_pct = 20.10
proposed_hit_rate_pct = 46.15
proposed_brier = 0.178711
proposed_p_l = -2.391522
domain_switches = 2
exits = 9
```

重要：这些仍不是最终论文数值，因为 BTC outcome 和完整 baseline 还没补齐。

## 7. 仍未完成

必须继续做：

1. 补 resolved outcomes：
   - BTC selected signal outcome。
   - CS2 selected signals outcome。
   - Weather selected signals outcome 已有 3 个，但覆盖还不足。

2. 补完整 baseline：
   - `market_only`
   - `data_only`
   - `news_only`
   - `data_news`
   - `proposed_agent`

3. 重新跑 evaluation，检查：
   - Table I 五个 method 都有真实值。
   - Table II 三个 domain 都有可解释结果。
   - Table III 有 threshold / coverage / PnL tradeoff。
   - Table IV 有 CS2、BTC、Weather、switch/exit examples。

4. 再用 `paper_placeholders.md` 和 Table I-IV 填论文 `[P]`。

5. 同步到 `github_upload` 并 push。

## 8. GitHub 状态

上传目录：

```text
D:\Polyquant\github_upload
```

远端：

```text
https://github.com/Leroyyyyyyyyy/DIA-CW.git
```

已确认可 push。最新提交以 `git log -1 --oneline` 为准。上一次已确认推送提交：

```text
abaa595 Wire latest dia and Weather outputs into evaluation
```

如果 Git push 连接超时，用：

```powershell
git -C D:\Polyquant\github_upload -c http.version=HTTP/1.1 -c http.lowSpeedLimit=0 push
```

## 9. 禁止事项

- 不要把 `dia` / `Weather(2)` 整包直接 merge 到主仓库。
- 不要用 `dia --sample` 的 BTC 输出填论文。
- 不要只用 Weather 的 3 条 trades 算 coverage / threshold。
- 不要让三套 backtest 分别生成 Table I-III。
- 不要上传 `.venv`、`__pycache__`、`target`、`output`、zip、大型 raw data。
