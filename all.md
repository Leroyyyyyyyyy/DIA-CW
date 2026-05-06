# DIA-CW / Polyquant 当前交接状态

> 每次切换对话或恢复工作，先读这个文件。每次路径、数据、结果、GitHub 状态变化后，都要更新本文件。

## 1. 当前总判断

- 最终代码仓库：`D:\Polyquant\poly-ok-check`
- GitHub 上传目录：`D:\Polyquant\github_upload`
- GitHub 远程：`https://github.com/Leroyyyyyyyyy/DIA-CW.git`
- GitHub 当前已推送到：`main`
- 最近已推送提交：
  - `f4c9cb7 Align repository docs with paper framework`
  - `11b4ee2 Document strategy policy integration flow`
  - `ce251cc Initial coursework backtest and evaluation repo`
- 论文 PDF：`D:\Polyquant\main.pdf`
- 论文 `[P]`：共 123 个，集中在 Page 6-8，主要是 Table I-IV 和 Discussion。

核心原则：
- 不做三套独立 backtest。
- PMXT / Nautilus 负责盘口 replay、fills、PnL、HTML report。
- `poly-ok-check` 负责统一 schema、adapter、evaluation、论文 Table I-IV。
- `dia` 和 `Weather(2)` 只作为 domain signal/evidence module。
- 所有论文最终数字必须从统一 evaluation 输出，不手工拼。

## 2. 论文框架对齐

论文是 reactive cross-domain Polymarket agent：

```text
三域输入 -> DomainReport -> opportunity score -> reactive selector -> unified evaluation -> Table I-IV
```

三域：
- Counter-Strike：Dld / `poly-ok-check`
- Bitcoin 5-minute / news：`D:\Polyquant\dia`
- Weather：`D:\Polyquant\Weather(2)`

统一核心字段：

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
正文[P]   -> research\runs\cw_final\paper_placeholders.md
```

## 3. 当前关键路径

PMXT / Nautilus 回测执行：

```text
D:\Polyquant\backtestreadme.md
D:\Polyquant\vendor\prediction-market-backtesting
D:\Polyquant\vendor\prediction-market-backtesting\scripts\polymarket_find_markets.py
D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\replays.json
D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\weather_backtest.py
D:\Polyquant\vendor\prediction-market-backtesting\strategies\ema_crossover.py
```

统一 evaluation：

```text
D:\Polyquant\poly-ok-check\research\config\cw_experiment.yaml
D:\Polyquant\poly-ok-check\research\run\run_cw_experiment.py
D:\Polyquant\poly-ok-check\research\adapters\
D:\Polyquant\poly-ok-check\research\evaluation\cw_tables.py
D:\Polyquant\poly-ok-check\research\schemas\domain_report.py
```

运行统一 evaluation：

```powershell
cd D:\Polyquant\poly-ok-check
$env:PYTHONPATH="D:\Polyquant\poly-ok-check"
python -m research.run.run_cw_experiment `
  --config research\config\cw_experiment.yaml `
  --out-dir research\runs\cw_final
```

## 4. 新版组员代码状态

### `dia`

路径：

```text
D:\Polyquant\dia\dia
```

有用输出：

```text
D:\Polyquant\dia\dia\outputs_btc_window\signals.csv
D:\Polyquant\dia\dia\outputs_btc_window\signals.jsonl
D:\Polyquant\dia\dia\outputs_btc_window\evidence.jsonl
```

当前检查结果：
- `outputs_btc_window\signals.csv` 只有 1 条 BTC signal。
- 当前内容是 sample 风格，evidence URL 是 `example.com`。
- 不能直接作为最终论文结果，除非组员明确这是 demo。

需要让组员跑正式 BTC/news 输出，不能加 `--sample`：

```powershell
cd D:\Polyquant\dia\dia
python -m dia.run_news_pipeline --domain btc `
  --start-date 2026-04-29T00:00:00+08:00 `
  --end-date 2026-04-30T23:59:59+08:00 `
  --as-of 2026-04-30T09:00:00+08:00
```

### `Weather(2)`

路径：

```text
D:\Polyquant\Weather(2)\Weather
```

对齐说明：

```text
D:\Polyquant\Weather(2)\Weather\WEATHER_GIT_ALIGNMENT.md
```

有用输出：

```text
D:\Polyquant\Weather(2)\Weather\data\processed\signals.csv
D:\Polyquant\Weather(2)\Weather\data\processed\evidence.jsonl
D:\Polyquant\Weather(2)\Weather\data\processed\backtest_signal_table.csv
D:\Polyquant\Weather(2)\Weather\data\processed\backtest_trades.csv
D:\Polyquant\Weather(2)\Weather\data\processed\backtest_summary.csv
```

当前检查结果：
- `signals.csv`：562 rows，字段已经是统一 `DomainReport` 格式。
- `backtest_signal_table.csv`：562 decision windows。
- `backtest_trades.csv`：3 trades。
- `backtest_summary.csv`：win_rate 0.3333，total_pnl -1.607242339832869。

重要注意：
- Table I / III 需要 coverage 和 threshold sensitivity，所以不能只用 `backtest_trades.csv`。
- Weather 主 decision window 应来自 `signals.csv` 或 `backtest_signal_table.csv`。
- `backtest_trades.csv` 只作为成交/PnL/evidence 补充。

## 5. 当前实现状态

已完成：
- `cw_experiment.yaml` 已切到新版 `dia` 和 `Weather(2)` 路径。
- `weather_adapter.py` 已支持优先读取 Weather 统一 `signals.csv`。
- Weather 现在走 562 条 decision windows，不再被 3 条 `backtest_trades.csv` 覆盖。
- Weather `enter/hold` 已在 adapter 中规范化成 evaluation 使用的 `YES/NO/HOLD`。
- `run_cw_experiment.py` 已支持传入 weather `signals_csv`。
- 已重跑真实输出目录 `D:\Polyquant\poly-ok-check\research\runs\cw_final`。

当前 `cw_experiment.yaml` 指向：

```text
D:/Polyquant/dia/dia/outputs_btc_window/signals.csv
D:/Polyquant/dia/dia/outputs_btc_window/evidence.jsonl
D:/Polyquant/Weather(2)/Weather/data/processed/signals.csv
D:/Polyquant/Weather(2)/Weather/data/processed/evidence.jsonl
D:/Polyquant/Weather(2)/Weather/data/processed/backtest_signal_table.csv
D:/Polyquant/Weather(2)/Weather/data/processed/backtest_trades.csv
```

最新 evaluation 检查：

```text
loaded_reports = 582
methods = proposed_agent: 582
domains = weather: 562, cs2: 19, btc: 1
weather actions = HOLD: 456, NO: 92, YES: 14
weather acted = 106
```

当前 `cw_final` 结果：

```text
proposed_selected: 117
available_decision_windows: 582
proposed_coverage_pct: 20.10
proposed_hit_rate_pct: 46.15
proposed_brier: 0.178711
proposed_p_l: -2.391522
domain_switches: 2
exits: 9
```

注意：这仍不能作为最终论文定稿数值，因为 BTC/news 仍是 sample。

仍有问题：
- BTC/news 当前没有 resolved outcome，P/L / Brier 可能无法最终定稿。
- BTC/news 当前仍是 sample 输出：1 条 signal，evidence 使用 `SampleCoinDesk` / `example.com`。
- 已尝试本地跑 `python -m dia.run_news_pipeline --domain btc ...` 非 sample，但 120 秒超时，没有改写输出。
- baseline rows 当前还不是完整真实 baseline，Table I 定稿前必须补齐：
  - market-only
  - data-only
  - news-only
  - data + news
  - proposed agent

## 6. 下一步执行顺序

1. 让 dia 负责人交正式 BTC/news 输出，不要 sample；确认输出不是 `example.com`。
2. 加 resolved outcomes 配置，至少覆盖最终进入论文的 BTC、CS2、Weather selected signals。
3. 补完整 baseline 生成逻辑。
4. 在正式 BTC 输出到位后重跑：

```powershell
cd D:\Polyquant\poly-ok-check
$env:PYTHONPATH="D:\Polyquant\poly-ok-check"
python -m research.run.run_cw_experiment `
  --config research\config\cw_experiment.yaml `
  --out-dir research\runs\cw_final
```

5. 检查新 `cw_final`：
   - Table I 五个 method 都有真实值。
   - Table II 三个 domain 都有值。
   - Table III threshold grid 有 coverage/PnL tradeoff。
   - Table IV 有 CS2、BTC、Weather、switch/exit example。
6. 用 `paper_placeholders.md` 和 Table I-IV 填 `main.pdf` 里的 `[P]`。
7. 更新 `github_upload` 的 README / docs 后 push。

## 7. GitHub 状态

本地上传仓库：

```text
D:\Polyquant\github_upload
```

远程：

```text
https://github.com/Leroyyyyyyyyy/DIA-CW.git
```

当前已连接并可 push。之前 GitHub 推送成功。  
如遇到 Git 连接超时，可用：

```powershell
git -C D:\Polyquant\github_upload -c http.version=HTTP/1.1 -c http.lowSpeedLimit=0 push
```

## 8. 不能做的事

- 不要把 `dia` 和 `Weather(2)` 整包直接 merge 进主仓库。
- 不要从 Weather 自己的 3 条 trades 手工抄最终论文 PnL。
- 不要用 `dia --sample` 的 1 条 BTC 结果定稿论文。
- 不要让三套 backtest 分别生成 Table I-III。
- 不要把 `.venv`、`__pycache__`、`target`、`output`、zip、大型 raw data 上传 GitHub。

## 9. 当前未定风险

- BTC/news 正式历史输出还没确认，这是当前最大阻塞。
- BTC resolved outcome 还没接入。
- PMXT/Nautilus execution-level PnL 与当前 fixed-stake evaluation PnL 的最终口径需要统一。
- `cw_final` 当前仍是旧数据初版，不是最终论文数值。
- 根目录 `codex_pytest_tmp_polyquant` 是 pytest 临时权限异常目录，不影响逻辑，但不用提交。
