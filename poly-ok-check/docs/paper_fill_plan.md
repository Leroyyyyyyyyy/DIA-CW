# 论文填表计划

## 结果来源

论文里的最终数字只从这里生成：

```text
research/runs/cw_final/
```

统一 runner 会输出：

- `unified_domain_reports.csv`
- `table1_overall.csv`
- `table2_by_domain.csv`
- `table3_threshold.csv`
- `table4_examples.csv`
- `paper_placeholders.md`

## 回测执行来源

论文 PnL 和成交证据的主回测执行口径以这里为准：

```text
D:\Polyquant\backtestreadme.md
D:\Polyquant\vendor\prediction-market-backtesting
```

核心产物：
- `backtests/private/replays.json`
- 终端 summary。
- `output/*.html` 回测报告。
- fills / PnL 结果。

`poly-ok-check` 的 evaluation 层负责把这些回测结果和各 domain signal 汇总成论文 Table I-IV，不替代 PMXT / Nautilus 回测执行层。

## PDF 占位符总览

根据 `D:\Polyquant\main.pdf` 抽取，当前有 123 个 `[P]`：

- Page 6: Table I 和总体分析，共 38 个。
- Page 7: Table II、Table III、Table IV，共 82 个。
- Page 8: Discussion，共 3 个。

更细的逐表清单见：
```text
docs/paper_placeholder_map.md
```

## Table I: Overall Baseline Comparison

负责人：Dld。

数据文件：
```text
research/runs/cw_final/table1_overall.csv
```

填写内容：
- proposed agent 的 P/L、coverage、hit rate、Brier score。
- market-only、data-only、news-only、data+news 等 baseline。

## Table II: Per-Domain Performance

负责人：Dld 生成，各 domain owner 检查。

数据文件：
```text
research/runs/cw_final/table2_by_domain.csv
```

检查分配：
- Dld 检查 CS2 行。
- `acy_news(1)` 负责人检查 news/BTC 行。
- `Weather` 负责人检查 weather 行。

## Table III: Threshold Sensitivity

负责人：Dld。

数据文件：
```text
research/runs/cw_final/table3_threshold.csv
```

填写内容：
- 不同 edge threshold 下的 coverage、switch/exit、P/L、hit rate。
- 用来支持 reactive agent 在低信心时退出或切换的论点。

## Table IV: Representative Signals

负责人：每个 domain owner 提供样例，Dld 统一整理。

数据文件：
```text
research/runs/cw_final/table4_examples.csv
```

样例分配：
- Dld 提供 CS2 代表信号，并补 switch/exit 样例。
- `acy_news(1)` 负责人提供 BTC/news 代表信号，必须能对应 `evidence_ref`。
- `Weather` 负责人提供 weather 代表信号，说明天气预测如何影响 market decision。

## 正文 `[P]`

负责人：Dld 生成，组长填入论文。

数据文件：
```text
research/runs/cw_final/paper_placeholders.md
```

## VIII. AUTHOR CONTRIBUTIONS

Dld 建议写：

```text
Dld was responsible for the final repository integration, the Counter-Strike
market component, the PMXT/Nautilus backtesting workflow, and aggregation of
the experimental results used in the paper tables.
```

## 规则

不要手工从三个文件夹拼最终论文数字。如果一个数字进了论文，它应该能从统一 reports 复现；否则只能标成 domain-specific appendix result。
