# main.pdf [P] 占位符地图

根据 `D:\Polyquant\main.pdf` 抽取，当前共有 123 个 `[P]`，集中在第 6、7、8 页。

## Page 6: Table I 和总体分析

位置：
```text
TABLE I
OVERALL BASELINE COMPARISON ACROSS ALL DOMAINS.
Method Hit rate Brier P/L Signals Coverage
```

需要填：
- Table I: 5 个 method x 5 个指标，共 25 个值。
- method: market-only, data-only, news-only, data + news, proposed agent。
- 指标: hit rate, Brier, P/L, signals, coverage。
- 正文分析: proposed selected opportunities、available decision windows、coverage、hit rate、Brier、P/L。
- baseline 差值: 相对 market-only 的 hit-rate change、Brier change、P/L change。
- baseline 差值: 相对 data-plus-news 的 P/L change、coverage change。
- reactive 行为: domain switches、exits。

负责人：
- Dld 负责从统一 evaluation 生成所有数值。
- `acy_news(1)` 和 `Weather` 负责人只负责保证自己的信号输入完整，不直接手填 Table I 数字。

输出文件：
```text
research/runs/cw_final/table1_overall.csv
research/runs/cw_final/paper_placeholders.md
```

## Page 7: Table II

位置：
```text
TABLE II
PER-DOMAIN PERFORMANCE OF THE PROPOSED AGENT.
Domain Hit rate Brier P/L Signals Share
```

需要填：
- Counter-Strike: hit rate, Brier, P/L, signals, share。
- Bitcoin 5-minute: hit rate, Brier, P/L, signals, share。
- Weather: hit rate, Brier, P/L, signals, share。
- 正文分析: highest-profit domain、对应 hit rate 和 P/L。
- 正文分析: weakest domain、对应 hit rate 和 P/L。
- selector allocation: CS2、Bitcoin、Weather 三个 domain 的 acted-decision share。

负责人：
- Dld 生成 Table II。
- Dld 检查 Counter-Strike 行。
- `acy_news(1)` 负责人检查 Bitcoin 5-minute 行。
- `Weather` 负责人检查 Weather 行。

输出文件：
```text
research/runs/cw_final/table2_by_domain.csv
research/runs/cw_final/paper_placeholders.md
```

## Page 7: Table III

位置：
```text
TABLE III
SENSITIVITY OF THE PROPOSED AGENT TO THE DECISION THRESHOLD.
tau Hit rate Brier P/L Coverage
```

需要填：
- 4 个 threshold row x 5 个指标，共 20 个值。
- 指标: tau, hit rate, Brier, P/L, coverage。
- 正文分析: reported operating threshold。
- operating threshold 下的 hit rate、Brier、coverage。
- lower threshold 下的 threshold value、coverage change、P/L change。
- higher threshold 下的 threshold value、coverage change、P/L change。

负责人：
- Dld 负责 threshold grid 和 sensitivity analysis。

输出文件：
```text
research/runs/cw_final/table3_threshold.csv
research/runs/cw_final/paper_placeholders.md
```

## Page 7: Table IV

位置：
```text
TABLE IV
REPRESENTATIVE SIGNALS SELECTED BY THE REACTIVE CROSS-DOMAIN AGENT.
Domain Market p_m p_hat Edge Score Action Outcome
```

需要填：
- Counter-Strike row: market, market probability, model probability, edge, score, action, outcome。
- Bitcoin 5-minute row: market, market probability, model probability, edge, score, action, outcome。
- Weather row: market, market probability, model probability, edge, score, action, outcome。
- Switch or exit case row: market, market probability, model probability, edge, score, action, outcome。

负责人：
- Dld 提供 Counter-Strike row。
- `acy_news(1)` 负责人提供 Bitcoin/news row，并保证有 `evidence_ref`。
- `Weather` 负责人提供 Weather row。
- Dld 负责 switch/exit row 和最终整理。

输出文件：
```text
research/runs/cw_final/table4_examples.csv
```

## Page 8: Discussion

需要填：
- highest-profit domain。
- lowest-profit domain。
- strongest observed result domain。

负责人：
- Dld 从 Table II 结果中生成。
- 组长负责把数字和 domain name 填进论文 discussion。

输出文件：
```text
research/runs/cw_final/paper_placeholders.md
```

## 总规则

所有 `[P]` 都应该来自统一 evaluation 输出。各 domain owner 只交稳定数据和 evidence，最终论文数值不从三个项目文件夹手动拼。
