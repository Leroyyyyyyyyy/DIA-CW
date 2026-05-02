# Polymarket PMXT 回测精简流程

当前workflow：

```
1. 搜 event / market
2. 展开 event，选 market_slug
3. 查 Yes / No token_index
4. 自动扫 PMXT 可用窗口
5. 写入 replays.json
6. runner 读取 replay 配置
7. runner 加载 PMXT 历史盘口数据
8. runner 加载策略和参数
9. runner 加载模拟成交 / 延迟配置
10. 跑回测
11. 输出终端结果和 HTML 报告

```

关键文件(example)

```
scripts/polymarket_find_markets.py
负责找市场、查 token、扫 PMXT、生成 replays.json

backtests/private/replays.json
负责告诉 runner 跑哪个市场和哪段时间

backtests/private/weather_backtest.py
负责组装数据、策略、成交延迟、报告并启动回测

strategies/ema_crossover.py
负责真正的 EMA 买卖逻辑

output/
负责存 HTML 报告


```


## 1. 初始化并进入环境

初始化并进入
```
cd xxxxx\prediction-market-backtesting

uv venv --python 3.13

uv pip install "nautilus_trader[polymarket,visualization]==1.225.0" `
  bokeh plotly numpy py-clob-client duckdb textual nbformat nbclient ipykernel `
  httpx pandas pyarrow msgspec

$env:PYTHONUTF8="1"
$env:BACKTEST_ENABLE_TIMING="0"

.venv\Scripts\python.exe -c "import nautilus_trader; import prediction_market_extensions; print('ok')"


```
仅进入
```powershell
cd xxx\prediction-market-backtesting
$env:PYTHONUTF8="1"
$env:BACKTEST_ENABLE_TIMING="0"
```

检查依赖：

```powershell
.venv\Scripts\python.exe -c "import nautilus_trader; import prediction_market_extensions; print('ok')"
```

看到 `ok` 就可以继续。

## 2. 搜 event / market

现在用正式脚本：

```text
scripts\polymarket_find_markets.py
```

搜 event：

```powershell
.venv\Scripts\python.exe scripts\polymarket_find_markets.py `
  --query hurricane `
  --active `
  --limit 10
```

输出重点看：

```text
event_slug
markets
title
```

展开 event 里的 markets：

```powershell
.venv\Scripts\python.exe scripts\polymarket_find_markets.py `
  --event where-will-2026-rank-among-the-hottest-years-on-record
```

输出重点看：

```text
market_slug
question
volume
active / closed
```

回测真正使用的是 `market_slug`，不是 `event_slug`。

## 3. 确认 Yes / No token_index

把 `market_slug` 换成要回测的市场：

```powershell
.venv\Scripts\python.exe scripts\polymarket_find_markets.py `
  --market will-ludvig-aberg-win-the-2026-masters-tournament `
  --tokens
```

输出类似：

```text
token_index outcome price token_id
0           Yes     ...
1           No      ...
```

通常 `0=Yes`、`1=No`，但每个市场都要确认一次。

## 4. 自动扫 PMXT 可用窗口

新 event 不知道该扫哪段时间时，直接省略 `--scan-start/--scan-end`：

```powershell
.venv\Scripts\python.exe scripts\polymarket_find_markets.py `
  --market will-ludvig-aberg-win-the-2026-masters-tournament `
  --tokens `
  --scan-pmxt `
  --token-index 0
```

自动范围规则：

```text
closed market: 从 endDate 往前扫，默认 lookback 7 天
open market: 从 now - 3 小时往前扫，默认 lookback 7 天
如果 market 有 startDate，会自动截断到 startDate 之后
```

默认扫描参数：

```text
--scan-lookback-days 7
--scan-delay-hours 3
--scan-step-hours 6
--window-minutes 10
--max-windows 28
```

输出重点看：

```text
PMXT scan range for ...
window_start
window_end
quotes
```

只有 `quotes > 0` 的窗口才适合写进 replay。想看空窗口也打印出来，加：

```powershell
--scan-all
```

想扫得更细，比如每小时试一个 10 分钟窗口：

```powershell
--scan-step-hours 1 --window-minutes 10
```

想扫更久：

```powershell
--scan-lookback-days 14 --max-windows 100
```

也可以对 event 下所有 markets 自动扫：

```powershell
.venv\Scripts\python.exe scripts\polymarket_find_markets.py `
  --event where-will-2026-rank-among-the-hottest-years-on-record `
  --scan-pmxt `
  --token-index 0 `
  --max-windows 6
```

event 里 market 多时会比较慢，建议先用小的 `--max-windows` 试。

## 5. 写 replays.json

推荐让扫描脚本直接写 runner 使用的 replay 配置，避免手动复制时间：

```powershell
.venv\Scripts\python.exe scripts\polymarket_find_markets.py `
  --market will-ludvig-aberg-win-the-2026-masters-tournament `
  --tokens `
  --scan-pmxt `
  --token-index 0 `
  --write-replays backtests\private\replays.json
```

写出的文件类似：

```json
[
  {
    "market_slug": "will-ludvig-aberg-win-the-2026-masters-tournament",
    "token_index": 0,
    "start_time": "2026-04-05T00:00:00Z",
    "end_time": "2026-04-05T00:10:00Z",
    "quotes": 346,
    "records": 692,
    "order_book_deltas": 346
  }
]
```

脚本只会把 `quotes > 0` 的窗口写进去。没有命中时会写空列表，runner 会拒绝空 replay 文件。

如果你已经知道具体 UTC 窗口，也可以做指定窗口检查：

```powershell
.venv\Scripts\python.exe scripts\polymarket_find_markets.py `
  --market will-ludvig-aberg-win-the-2026-masters-tournament `
  --tokens `
  --check-pmxt `
  --token-index 0 `
  --start-time 2026-04-05T05:10:00Z `
  --end-time 2026-04-05T05:20:00Z
```

如果你想强制限制扫描范围，才手动传：

```powershell
--scan-start 2026-04-05T00:00:00Z --scan-end 2026-04-06T00:00:00Z
```

## 6. DATA 配置
（现版本默认archive）
runner 里 PMXT 数据源顺序是：

```python
DATA = MarketDataConfig(
    platform=Polymarket,
    data_type=QuoteTick,
    vendor=PMXT,
    sources=(
        "local:D:/Polyquant/data/pmxt_raws",
        "archive:r2v2.pmxt.dev",
        "relay:209-209-10-83.sslip.io",
    ),
)
```

作用：

```text
local: 优先读本地 raw，最快，也能避免重复下载
archive: 本地没有时从 PMXT archive 取
relay: archive 不可用时兜底
```

## 7. REPLAYS 配置

`backtests\private\weather_backtest.py` 会优先读取：

```text
backtests\private\replays.json
```

这个文件由第 5 步自动生成。runner 内部等价于生成：

```python
REPLAYS = (
    QuoteReplay(
        market_slug="will-ludvig-aberg-win-the-2026-masters-tournament",
        token_index=0,
        start_time="2026-04-05T00:00:00Z",
        end_time="2026-04-05T00:10:00Z",
    ),
)
```

如果 `replays.json` 不存在，runner 才会使用内置 smoke 默认窗口。

## 8. 策略参数



当前 smoke runner 用短周期确认链路能成交：

```python
"fast_period": 8,
"slow_period": 21,
"entry_buffer": 0.0,
"take_profit": 0.01,
"stop_loss": 0.01,
```

这只是 smoke 参数，不代表策略优化结果。

## 9. 过滤和 HTML

调试阶段降低过滤条件，并开启 HTML：

```python
EXPERIMENT = build_replay_experiment(
    ...
    min_quotes=1,
    min_price_range=0.0,
    emit_html=True,
    chart_output_path="output",
)
```

HTML 生成是原项目自带能力，runner 通过 `emit_html=True` 触发。

输出目录：

```text
D:\Polyquant\vendor\prediction-market-backtesting\output
```

示例报告：

```text
D:\Polyquant\vendor\prediction-market-backtesting\output\weather_backtest_will-ludvig-aberg-win-the-2026-masters-tournament_legacy.html
```

如果某个很短窗口只有 1 笔成交，可能出现 legacy chart 的 `x_range=None` 警告。回测结果仍会打印；要稳定生成图，通常扩大 replay 窗口或换一个更活跃的命中窗口。

## 10. 跑回测

```powershell
.venv\Scripts\python.exe backtests\private\weather_backtest.py
```

当前自动生成的 smoke replay 已验证：

```text
Market                                                Quotes  Fills   PnL (USDC)
will-ludvig-aberg-win-the-2026-masters-tournament        346      1      +0.0000
TOTAL                                                             1      +0.0000
```

这里 PnL 仍可能是 0，但原因已经不是 warmup 没成交，而是这个自动命中的 10 分钟窗口只有 1 笔 fill，未形成可实现盈亏。想看更明显的 PnL，扩大窗口或扫描更多命中窗口。

=

## 12. 最短命令清单

```powershell
cd D:\Polyquant\vendor\prediction-market-backtesting
$env:PYTHONUTF8="1"
$env:BACKTEST_ENABLE_TIMING="0"

# 搜 event
.venv\Scripts\python.exe scripts\polymarket_find_markets.py --query hurricane --active --limit 10

# 展开 event
.venv\Scripts\python.exe scripts\polymarket_find_markets.py --event where-will-2026-rank-among-the-hottest-years-on-record

# 看 token
.venv\Scripts\python.exe scripts\polymarket_find_markets.py --market will-ludvig-aberg-win-the-2026-masters-tournament --tokens

# 自动扫 PMXT 可用窗口
.venv\Scripts\python.exe scripts\polymarket_find_markets.py --market will-ludvig-aberg-win-the-2026-masters-tournament --tokens --scan-pmxt --token-index 0

# 自动扫并写入 runner 使用的 replay 配置
.venv\Scripts\python.exe scripts\polymarket_find_markets.py --market will-ludvig-aberg-win-the-2026-masters-tournament --tokens --scan-pmxt --token-index 0 --write-replays backtests\private\replays.json

# 跑回测
.venv\Scripts\python.exe backtests\private\weather_backtest.py
```
