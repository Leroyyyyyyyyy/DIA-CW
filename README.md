# Polyquant 仓库整合总说明

## 1. 当前结论

- 最终主仓库用：`D:\Polyquant\poly-ok-check`
- 论文 PnL 回测执行口径用：`D:\Polyquant\backtestreadme.md` 里的 PMXT / Nautilus workflow。
- 回测执行目录用：`D:\Polyquant\vendor\prediction-market-backtesting`
- `poly-ok-check` 当前主要负责统一 schema、adapter、evaluation、论文 Table I-IV 聚合。
- `D:\Polyquant\acy_news(1)` 和 `D:\Polyquant\Weather` 不作为最终主回测系统，而是作为 domain module 接入。
- 最终论文 Table I-IV 和正文 `[P]` 数值，应该从统一 evaluation 输出生成，不要手工从三套系统拼。

## 2. 当前回测以 `backtestreadme.md` 为准

当前真正要跑论文 PnL 的回测，不是先 merge 三套代码，也不是优先用 `poly-ok-check\research\backtest`，而是按照：

- `D:\Polyquant\backtestreadme.md`
- `D:\Polyquant\vendor\prediction-market-backtesting`

这套 PMXT / Nautilus 流程来跑。

核心流程：

```text
1. 搜 event / market
2. 展开 event，确定 market_slug
3. 查 Yes / No token_index
4. 扫 PMXT 可用窗口
5. 写 backtests/private/replays.json
6. runner 加载 PMXT 历史盘口数据
7. runner 加载策略和参数
8. runner 加载模拟成交 / 延迟配置
9. 跑回测
10. 输出终端结果和 HTML 报告
```

关键文件：

```text
D:\Polyquant\vendor\prediction-market-backtesting\scripts\polymarket_find_markets.py
D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\replays.json
D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\weather_backtest.py
D:\Polyquant\vendor\prediction-market-backtesting\strategies\ema_crossover.py
D:\Polyquant\vendor\prediction-market-backtesting\output\
```

`poly-ok-check\research\backtest` 可以保留为轻量研究/汇总辅助，但当前论文里 P/L、fills、HTML report、PMXT replay 这类回测证据，应优先按 `backtestreadme.md` 这条链路产生。

`acy_news(1)` 里的 `backtest` 更像 historical signal collection：按历史 `as_of` 时间重复生成 signals/evidence，但没有完整盘口回放、成交、持仓和 PnL。因此它适合当 news/BTC signal module，不适合当最终主回测。

`Weather` 的回测结果有天气 domain 价值，但最终仍应通过 adapter 转成统一格式，再进入总 evaluation。

### 组员策略如何接入回测

另外两个组员现在不需要各自写一套 backtest，也不需要改 PMXT data loader、execution、fill、PnL 模拟。

他们需要接入的是统一的 policy / strategy 层。当前代码里对应位置是：

```text
D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\weather_backtest.py
```

具体入口是 `STRATEGY_CONFIGS`：

```python
STRATEGY_CONFIGS = [
    {
        "strategy_path": "strategies:QuoteTickEMACrossoverStrategy",
        "config_path": "strategies:QuoteTickEMACrossoverConfig",
        "config": {
            "trade_size": Decimal(5),
            "fast_period": 8,
            "slow_period": 21,
            "entry_buffer": 0.0,
            "take_profit": 0.01,
            "stop_loss": 0.01,
        },
    }
]
```

也就是说，真正要替换或扩展的是 `strategy_path` / `config_path` 指向的策略，而不是回测框架本身。

推荐做法：

```text
strategies/
├─ signal_policy.py        # 统一读取 signal CSV 的策略
├─ news_signal_policy.py   # acy_news(1) 的 news/BTC 策略封装
└─ weather_signal_policy.py# Weather 的天气策略封装
```

更省事的做法是先只做一个统一 `SignalPolicyStrategy`，让两个组员都输出同一种 signal CSV：

```text
timestamp,market_slug,token_index,market_prob,model_prob,
edge,score,action,evidence_ref
```

分工口径：

- `acy_news(1)` 负责人：把 BTC/news 逻辑封装成 news policy，或者稳定输出统一 `signals.csv`。
- `Weather` 负责人：把 weather forecast 逻辑封装成 weather policy，或者稳定输出统一 `backtest_signal_table.csv`。
- Dld：负责把这些 policy / signal 接入 PMXT runner，统一跑 replay、fills、PnL、HTML report。

一句话：组员负责“决策信号/策略”，Dld 负责“统一回测执行和论文表格”。最终不要出现三套 backtest 分别算 PnL 的情况。

## 3. 已经做了什么

### 文档

已新增：

- `D:\Polyquant\poly-ok-check\docs\repo_structure.md`
- `D:\Polyquant\poly-ok-check\docs\responsibilities.md`
- `D:\Polyquant\poly-ok-check\docs\paper_fill_plan.md`

这些文件说明：

- 最终仓库应该长什么样
- 谁负责哪个代码模块
- 谁负责论文哪些结果
- 为什么不让三套 backtest 并列作为最终结果来源

### 统一格式

已新增统一 report schema：

- `D:\Polyquant\poly-ok-check\research\schemas\domain_report.py`

统一字段：

```text
method,domain,timestamp,market_id,target,market_prob,model_prob,
data_score,news_score,edge,action,outcome,evidence_ref,pnl,metadata
```

目标是让 CS2、BTC/news、weather 都转成同一种 `DomainReport`，再统一计算论文表格。

### 三个 adapter

已新增：

- `research\adapters\acy_news_adapter.py`
- `research\adapters\weather_adapter.py`
- `research\adapters\cs2_adapter.py`

作用：

- `acy_news_adapter.py`：读取 `acy_news(1)\dia\outputs...\signals.csv/jsonl`，转成统一 report。
- `weather_adapter.py`：读取 `Weather\Weather\data\processed\backtest_trades.csv` 或 `backtest_signal_table.csv`，转成统一 report。
- `cs2_adapter.py`：读取 Dld 的 CS2 signal 和 backtest timeline，转成统一 report。

### evaluation 层

已新增：

- `D:\Polyquant\poly-ok-check\research\evaluation\cw_tables.py`

当前能生成：

- Table I: overall baseline comparison
- Table II: per-domain results
- Table III: threshold sensitivity
- Table IV: representative signals
- `paper_placeholders.md`

### 总控 runner

已新增：

- `D:\Polyquant\poly-ok-check\research\run\run_cw_experiment.py`
- `D:\Polyquant\poly-ok-check\research\config\cw_experiment.yaml`

当前命令：

```powershell
cd D:\Polyquant\poly-ok-check
$env:PYTHONPATH="D:\Polyquant\poly-ok-check"

python -m research.run.run_cw_experiment `
  --config research\config\cw_experiment.yaml `
  --out-dir research\runs\cw_final
```

已跑通，输出在：

```text
D:\Polyquant\poly-ok-check\research\runs\cw_final\
```

当前生成文件：

- `unified_domain_reports.csv`
- `table1_overall.csv`
- `table2_by_domain.csv`
- `table3_threshold.csv`
- `table4_examples.csv`
- `paper_placeholders.md`

注意：这些是根据当前已有输出跑出的初版聚合结果，不等于最终论文定稿数值。

## 4. 当前推荐最终仓库结构

```text
poly-ok-check/
├─ src/                         # Rust Market Data Hub / runtime contracts
├─ tests/                       # Rust tests
├─ research/
│  ├─ adapters/                 # 三方输出转统一 DomainReport
│  ├─ backtest/                 # 轻量研究/汇总辅助；论文 PnL 回测优先看 vendor PMXT
│  ├─ config/                   # cw_experiment.yaml 等实验配置
│  ├─ domains/
│  │  ├─ cs2/                   # Dld CS2
│  │  ├─ news/                  # acy_news(1) 接入点
│  │  └─ weather/               # Weather 接入点
│  ├─ evaluation/               # Table I-IV 聚合
│  ├─ run/                      # run_cw_experiment.py
│  └─ schemas/                  # domain_report.py 等统一格式
└─ docs/
   ├─ repo_structure.md
   ├─ responsibilities.md
   └─ paper_fill_plan.md
```

## 5. `main.pdf` 需要填什么

我已经按 `D:\Polyquant\main.pdf` 抽取过 `[P]`，当前共有 123 个，占位符只集中在第 6、7、8 页。

详细清单已写入：

- `D:\Polyquant\poly-ok-check\docs\paper_placeholder_map.md`

按论文位置分：

- Page 6: Table I 和总体分析，共 38 个 `[P]`。
- Page 7: Table II、Table III、Table IV，共 82 个 `[P]`。
- Page 8: Discussion，共 3 个 `[P]`。

这些 `[P]` 不是随便填描述，而是都要从可复现代码结果里来：

- Table I: overall baseline comparison。
- Table II: per-domain performance。
- Table III: threshold sensitivity。
- Table IV: representative signals。
- Discussion: highest-profit domain、lowest-profit domain、strongest observed result。

## 6. 代码负责部分分配

### Dld

代码范围：
- `D:\Polyquant\backtestreadme.md`
- `D:\Polyquant\vendor\prediction-market-backtesting\scripts\polymarket_find_markets.py`
- `D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\replays.json`
- `D:\Polyquant\vendor\prediction-market-backtesting\backtests\private\weather_backtest.py`
- `D:\Polyquant\poly-ok-check\research\backtest\`
- `D:\Polyquant\poly-ok-check\research\adapters\cs2_adapter.py`
- `D:\Polyquant\poly-ok-check\research\evaluation\`
- `D:\Polyquant\poly-ok-check\research\run\run_cw_experiment.py`
- `D:\Polyquant\poly-ok-check\research\config\cw_experiment.yaml`
- `D:\Polyquant\poly-ok-check\research\domains\cs2\`

具体责任：
- 维护最终主仓库结构。
- 按 `backtestreadme.md` 维护主回测执行流程，包括 PMXT replay、order/fill、PnL、HTML report。
- 负责 CS2 数据对齐、CS2 signal、CS2 backtest timeline。
- 负责把 CS2、news/BTC、weather 三方输出统一转成 `DomainReport`。
- 负责最后一键运行 `run_cw_experiment.py`，生成统一结果。

必须交付：
- PMXT replay 配置和回测输出。
- 终端 summary / HTML report / fills / PnL 证据。
- CS2 的 signal/report。
- `cw_experiment.yaml` 中三方路径确认无误。
- `research\runs\cw_final\table1_overall.csv`
- `research\runs\cw_final\table2_by_domain.csv`
- `research\runs\cw_final\table3_threshold.csv`
- `research\runs\cw_final\table4_examples.csv`
- `research\runs\cw_final\paper_placeholders.md`

### `acy_news(1)` 负责人

代码范围：
- `D:\Polyquant\acy_news(1)\dia\polymarket_signal_agent\`
- `D:\Polyquant\acy_news(1)\dia\outputs...\`

具体责任：
- 负责 news hub / BTC news / evidence collection。
- 负责 news/BTC signal 的生成逻辑。
- 负责每个 signal 对应的 evidence 记录。
- 不负责最终 PnL 回测；原来的 `backtest` 只定位为 historical signal collection。

必须交付：
```text
signals.csv
signals.jsonl
evidence.jsonl
```

交付要求：
- `signals.csv` 至少要能提供 timestamp、market_id、market_prob、model_prob 或 direction、action、evidence_ref。
- `evidence.jsonl` 里每条 evidence 要能被 `evidence_ref` 找到。
- 最终不要手动给论文 PnL 数字，只提供信号和证据，由 Dld 的统一 evaluation 生成表格。

### `Weather` 负责人

代码范围：
- `D:\Polyquant\Weather\Weather\`
- `D:\Polyquant\Weather\Weather\data\processed\`

具体责任：
- 负责 weather forecast model。
- 负责 weather market signal。
- 负责 weather-specific backtest / analysis，作为 appendix 或 evidence。
- 负责解释天气模型为什么会给出某个 market probability / model probability。

必须交付：
```text
backtest_signal_table.csv
backtest_trades.csv
backtest_summary.csv
```

交付要求：
- `backtest_signal_table.csv` 负责给统一 adapter 读。
- `backtest_trades.csv` 可作为 weather 自己 domain 的佐证。
- `backtest_summary.csv` 可作为论文 discussion 或 appendix 的补充。
- 最终 Table I-III 的统一结果仍由 Dld 的 evaluation 生成。

### 组长 / 论文负责人

代码范围：
- 不负责主要代码实现。
- 负责 Prism / LaTeX 论文主文档。

具体责任：
- 维护作者信息、学号、邮箱。
- 管理论文 `[P]` 占位符。
- 根据 Dld 输出的 `paper_placeholders.md` 和 Table I-IV CSV 填论文。
- 确认每个 domain owner 在 VIII. AUTHOR CONTRIBUTIONS 中认领自己的贡献。

## 7. 论文结果填写分配

### Table I: Overall Baseline Comparison

负责人：Dld。

数据来源：
```text
D:\Polyquant\poly-ok-check\research\runs\cw_final\table1_overall.csv
```

填写内容：
- proposed agent 的 P/L、coverage、hit rate、Brier score。
- market-only、data-only、news-only、data+news 等 baseline 对比。

注意：
- 不能从 `acy_news(1)` 或 `Weather` 的单独 backtest 手工抄 PnL。
- 如果 baseline 还没补完，Table I 先不要定稿。

### Table II: Per-Domain Performance

负责人：Dld 生成，各 domain owner 检查自己那一行。

数据来源：
```text
D:\Polyquant\poly-ok-check\research\runs\cw_final\table2_by_domain.csv
```

检查分配：
- Dld 检查 CS2 行。
- `acy_news(1)` 负责人检查 news/BTC 行。
- `Weather` 负责人检查 weather 行。

填写内容：
- 每个 domain 的 signal 数量、coverage、hit rate、P/L、Brier score。

### Table III: Threshold Sensitivity

负责人：Dld。

数据来源：
```text
D:\Polyquant\poly-ok-check\research\runs\cw_final\table3_threshold.csv
```

填写内容：
- 不同 edge threshold 下的 coverage、switch/exit、P/L、hit rate。
- 用来支持论文里“reactive agent 会在低信心时退出或切换”的论点。

### Table IV: Representative Signals

负责人：每个 domain owner 提供样例，Dld 统一整理。

数据来源：
```text
D:\Polyquant\poly-ok-check\research\runs\cw_final\table4_examples.csv
```

样例分配：
- Dld：提供一个 CS2 代表信号，最好包含 market probability、model probability、edge、最终 outcome。
- `acy_news(1)` 负责人：提供一个 BTC/news 代表信号，必须带 `evidence_ref`。
- `Weather` 负责人：提供一个 weather 代表信号，说明天气预测如何影响 market decision。
- Dld 额外补一个 switch 或 exit 的例子，如果结果里有。

### 正文 `[P]` 占位符

负责人：Dld 生成数字，组长填入论文。

数据来源：
```text
D:\Polyquant\poly-ok-check\research\runs\cw_final\paper_placeholders.md
```

填写方式：
- Dld 跑完最终数据后，把 `paper_placeholders.md` 发给组长。
- 组长只从这个文件和 Table I-IV CSV 填 `[P]`。
- 如果某个 `[P]` 没有对应生成项，就先标出来，不要凭感觉补。

### VIII. AUTHOR CONTRIBUTIONS

Dld 建议写：

```text
Dld was responsible for the final repository integration, the Counter-Strike
market component, the primary backtesting system, and aggregation of the
experimental results used in the paper tables.
```

## 8. 接下来要做什么

### 必须做

1. 和组员确认最终主仓库就是 `poly-ok-check`。
2. 让 `acy_news(1)` 负责人固定输出路径和字段，不要频繁改 CSV schema。
3. 让 `Weather` 负责人固定输出路径和字段。
4. 确认 `cw_experiment.yaml` 里的三方路径都是最终版本。
5. 补完整 baseline：
   - market-only
   - data-only
   - news-only
   - data + news
   - proposed agent
6. 用最终数据重跑 `run_cw_experiment.py`。
7. 用 `research\runs\cw_final\paper_placeholders.md` 填论文。

### 建议做

1. 把 `acy_news(1)` 的 `backtest` 命令改名或在 README 里说明为 `historical_collect`。
2. 给每个 adapter 加更多真实样例测试。
3. 给 `cw_experiment.yaml` 增加 resolved outcomes 配置。
4. 明确哪些数据文件太大，不进 git。
5. 在最终 README 里只保留一条主复现路径。

## 9. 当前注意点

- 当前没有直接搬动 `acy_news(1)` 和 `Weather` 的代码，只做了 adapter 和 integration layer。
- 当前 `cw_final` 输出是初版聚合，不是最终论文数值。
- pytest 在当前 sandbox 遇到 Windows temp 权限问题；手动 smoke 和 `compileall` 已通过，runner 已跑通。
- 根目录存在一个 `codex_pytest_tmp_polyquant` 权限异常临时目录，是 pytest 创建的，当前 sandbox 无法清理；不影响代码逻辑。
