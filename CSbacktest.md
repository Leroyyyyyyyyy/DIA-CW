# CS 市场 Backtest 进度

## 维护要求

- 以后更新本文件必须“特别精简但不缺关键点”：只保留结论、已验证事实、文件路径、关键命令、阻塞点、下一步。
- 不写长过程流水账；如果某一步失败，写清楚失败原因和下一步可执行动作。

## 当前目标

找 2025 或 2026 年真实 CS2 比赛，把 Polymarket 市场数据和 `.dem` 解析数据对齐，先打通第一场端到端回测链路。

## 本地已有能力

- demo 解析脚本：`D:\Polyquant\poly-ok-check\research\run\run_cs2_demo_poc.py`
- demo 对齐脚本：`D:\Polyquant\poly-ok-check\research\run\align_demo_to_market_time.py`
- price-history 回测入口：`D:\Polyquant\poly-ok-check\research\run\run_market_backtest.py`
- PMXT L2 replay 入口：`D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\weather_backtest.py`
- Polymarket market/PMXT 查询脚本：`D:\Polyquant\vendor\prediction-market-backtesting\scripts\polymarket_find_markets.py`

## 本地已解析 demo

已解析的 demo 是：

- `D:\Polyquant\data\cs2_demos\dem\megoshort-vs-chickenburger-m1-mirage.dem`
- `D:\Polyquant\data\cs2_demos\dem\megoshort-vs-chickenburger-m2-train.dem`

输出：

- `D:\Polyquant\data\cs2_demos\parsed\grid_2873664_m1_mirage\`
- `D:\Polyquant\data\cs2_demos\parsed\grid_2873664_m2_train\`

摘要：

- map1 mirage: snapshots=4390, economy_rows=883, player_deaths=141, round_rows=39
- map2 train: snapshots=4178, economy_rows=840, player_deaths=156, round_rows=39

注意：这场是 `megoshort vs Chicken Burger`，时间 `2026-01-03T09:00:00Z`，暂未找到对应 Polymarket 市场，不能作为真实市场回测第一场。

## 第一场候选

优先候选已切到 2026 Polymarket CS2 单场：

- Polymarket slug: `cs2-run2-omega1-2026-04-03`
- Title: `Counter-Strike: Rune Eaters vs Omega (BO3) - CCT Europe Series #20 Group Stage`
- Market start: `2026-04-02T11:32:39Z`
- Game start: `2026-04-03T08:10:00Z`
- Market end: `2026-04-03T14:10:00Z`
- Result: Omega won, score `1-2`
- Market volume: about `33653.66`
- Token 0: Rune Eaters, token_id `48173552318431392518969319643418757891164437723036024679743103719877608586042`, final price `0`
- Token 1: Omega, token_id `75287410072070313482138182655077017926296883899317007126163412308302485037905`, final price `1`
- Polymarket page: `https://polymarket.com/event/cs2-run2-omega1-2026-04-03`
- Gamma API: `https://gamma-api.polymarket.com/markets/slug/cs2-run2-omega1-2026-04-03`

## 已验证数据覆盖

Polymarket price-history 已通：

- token: Omega token_index=1
- rows: `1508`
- first price ts: `1775130455`
- last price ts: `1775220997`
- price range: `0.355` to `0.9995`
- raw cache: `D:\Polyquant\poly-ok-check\research\data\polymarket\price_history\75287410072070313482138182655077017926296883899317007126163412308302485037905\1775129559_1775225400_f1.json`
- market frame cache: `D:\Polyquant\poly-ok-check\research\data\polymarket\market_frames\75287410072070313482138182655077017926296883899317007126163412308302485037905\1775129559_1775225400_f1.parquet`

PMXT L2 暂未通：

- 已查 `2026-04-02T12:00Z-12:30Z`、`2026-04-03T08:10Z-08:40Z`、`2026-04-03T10:00Z-10:30Z`
- token_index=1 全部 `quotes=0`
- 结论：第一场先走 price-history synthetic book；PMXT 后续换更适合的市场或修数据源。

## demo 状态

- HLTV 页面确认该场有 demo：`https://www.hltv.org/matches/2392388/rune-eaters-vs-omega-cct-season-3-europe-series-20`
- demo 下载目标：`https://www.hltv.org/download/demo/125472`
- 实际 R2 文件：`https://r2-demos.hltv.org/demos/125472/cct-season-3-europe-series-20-rune-eaters-vs-omega-bo3-5edZhjqYD4LDTZExxkK8B5.rar`
- 已手动下载并解压到：`D:\Polyquant\data\cs2_demos\dem\rune-eaters-vs-omega\`
- 三个 demo:
  - `rune-eaters-vs-omega-m1-ancient.dem`
  - `rune-eaters-vs-omega-m2-dust2.dem`
  - `rune-eaters-vs-omega-m3-mirage.dem`

## demo 解析与对齐已完成

单图解析输出：

- `D:\Polyquant\data\cs2_demos\parsed\cs2_run2_omega1_2026_04_03_m1_ancient\`
- `D:\Polyquant\data\cs2_demos\parsed\cs2_run2_omega1_2026_04_03_m2_dust2\`
- `D:\Polyquant\data\cs2_demos\parsed\cs2_run2_omega1_2026_04_03_m3_mirage\`

解析摘要：

- m1 ancient: snapshots=4580, economy_rows=916, deaths=143, round_rows=44, result Omega 13-8
- m2 dust2: snapshots=4590, economy_rows=918, deaths=116, round_rows=38, result Rune Eaters 13-5
- m3 mirage: snapshots=4660, economy_rows=932, deaths=151, round_rows=47, result Omega 14-7

对齐锚点：

- m1: anchor_utc `2026-04-03T08:10:00Z`, anchor_tick `68`
- m2: anchor_utc `2026-04-03T09:10:35Z`, anchor_tick `88`, 由 price-history + demo 时长反推
- m3: anchor_utc `2026-04-03T09:54:31Z`, anchor_tick `5754`, 由 price-history + demo 时长反推；前段有 knife/warmup，不能用默认 tick `99`

series-level aligned 输出：

- `D:\Polyquant\data\cs2_demos\parsed\cs2_run2_omega1_2026_04_03_series\market_aligned\`
- player_snapshot_5s rows: `13830`
- economy_snapshot_5s rows: `2766`
- player_death rows: `410`
- round_state rows: `129`
- UTC coverage: `2026-04-03T08:09:58.937500Z` to `2026-04-03T10:31:48.750000Z`

## 已落地 smoke 信号

- 信号文件：`D:\Polyquant\poly-ok-check\research\data\cs2_first_match\omega_hold_signal.csv`
- 用途：只验证 price-history runner 链路，不代表策略质量。

## 已落地 demo-derived 信号

- 信号文件：`D:\Polyquant\poly-ok-check\research\data\cs2_first_match\omega_demo_round_signal.csv`
- 来源：aligned demo 的 round_end 后比分状态
- rows: `61`
- 识别 series result: Omega `2-1`
- 用途：验证 demo parquet 能驱动 Polymarket 回测；仍不是策略 alpha。

## smoke backtest 已跑通

- run_dir: `D:\Polyquant\poly-ok-check\research\runs\cs2_first_match\20260421T151133Z`
- window: `2026-04-03T08:10:00Z` 到 `2026-04-03T14:10:00Z`
- rows: `287`
- orders: `1`
- fills: `1`
- total_pnl: `+85.8111`
- source: `clob_price_history`
- 关键参数：price-history 是 1 分钟粒度，必须设置 `--stale-threshold-ms 70000`，否则默认 15 秒会导致订单全部 expired。

可复现命令：

```powershell
cd D:\Polyquant\poly-ok-check
$env:PYTHONPATH="D:\Polyquant\poly-ok-check"

python research\run\run_market_backtest.py `
  --token-id 75287410072070313482138182655077017926296883899317007126163412308302485037905 `
  --market-id cs2-run2-omega1-2026-04-03 `
  --start-ts 1775203800 `
  --end-ts 1775225400 `
  --signals research\data\cs2_first_match\omega_hold_signal.csv `
  --signal-mode prob `
  --outcome 1.0 `
  --entry-threshold 0.03 `
  --exit-threshold -1.0 `
  --position-size 100 `
  --initial-cash 10000 `
  --fidelity-minutes 1 `
  --stale-threshold-ms 70000 `
  --out-dir research\runs\cs2_first_match
```

## demo-derived backtest 已跑通

- run_dir: `D:\Polyquant\poly-ok-check\research\runs\cs2_first_match_demo_signal\20260421T153303Z`
- signal: `omega_demo_round_signal.csv`
- rows: `287`
- orders: `19`
- fills: `19`
- total_pnl: `+42.0076`
- source: `clob_price_history`
- 关键参数仍然需要 `--stale-threshold-ms 70000`

## 下一步

1. 把 demo-derived signal 逻辑固化成可复用脚本，而不是一次性生成。
2. 改进信号：过滤 warmup、加入经济/存活/击杀强度，而不是只用 round score。
3. 如果要 PMXT L2，继续找同类 CS2 市场或修 PMXT sports 数据源；当前第一场 PMXT quotes=0。
