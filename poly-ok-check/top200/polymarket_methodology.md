# Polymarket Top200 代码方法说明

这个版本的代码做了 4 件事：

1. 通过官方 leaderboard API 拉取 `WEEK` 和 `MONTH` 的前 200。
2. 对每个地址拉取公开的 `trades`、`activity`、`positions`。
3. 通过 `gamma-api /markets` 用 `conditionId` 补充市场元数据（如 `negRisk`、`category`）。
4. 按启发式规则打标签，输出：
   - `market_maker_like`
   - `arb_or_conversion_like`
   - `directional_like`
   - `short_term_scalper_like`
   - `systematic_bot_like`

## 关键输出文件

- `leaderboard_week_top200.csv`
- `leaderboard_month_top200.csv`
- `trader_summary_week.csv`
- `trader_summary_month.csv`
- `trader_market_summary_week.csv`
- `trader_market_summary_month.csv`
- `strategy_market_summary_week.csv`
- `strategy_market_summary_month.csv`

## 主要特征

### 地址层特征
- `trade_count`：交易笔数
- `unique_markets`：涉及多少个 market
- `top1_market_volume_share`：是否集中押单一市场
- `one_sided_side_ratio`：买/卖是否明显偏单边
- `paired_outcome_market_ratio`：同一 market 是否交易过多个 outcome
- `two_sided_market_ratio`：同一 market 是否买卖双向都做过
- `fast_roundtrip_market_ratio`：同一 market 是否 24 小时内双向往返
- `neg_risk_market_ratio`：交易是否集中在 neg risk 市场
- `maker_rebate_count`：是否拿过 maker rebate
- `split_count / merge_count / conversion_count`：是否有拆分 / 合并 / 转换行为

### market 层特征
- 每个地址在哪些 market 最活跃
- 不同策略标签的地址，最常出没在哪些 market
- 哪些 market 更容易出现“做市型 / 套利型 / 短线型”地址

## “怎么下单”能分析到什么程度

这个脚本能较稳妥分析的是：
- 更像被动挂单吃 maker rebate，还是更像主动成交
- 是否频繁做双边、跨 outcome、neg risk / conversion / merge / split
- 是否更像方向单、短线往返、或系统化策略

但它**不能**完整还原：
- 别人所有未成交挂单
- 别人所有撤单轨迹
- 每一笔成交前的完整盘口状态

因此这里的“怎么下单”是**行为推断**，不是对私有订单日志的精确回放。
