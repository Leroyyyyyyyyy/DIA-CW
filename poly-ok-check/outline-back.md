# Research System Outline Back

## 核心原则

按当前 plan 的接口定义落地，但按上一版分层架构约束职责。

必须始终守住：

1. 模型学的是 `fair_win_prob`，不是市场价格。
2. 市场只提供交易参照，不定义真相。
3. 策略只消费 `edge_net`，不直接碰原始比赛特征。

一句话：

> 比赛概率建模、市场对齐、交易执行必须彻底解耦。

## 架构总览

系统采用“双时钟 + 双层对象 + 分层决策”。

- 双时钟
  - `event_time`: 比赛真实事件时间
  - `market_time`: 市场快照时间
- 双层对象
  - `DataPackage`: 只含比赛侧、在 `available_ts_s` 时刻可见的信息
  - `AlignedMarketFrame`: `DataPackage + 市场快照 + edge 字段`
- 分层决策
  - 预测层输出 `model_win_prob`
  - 校准层输出 `fair_win_prob`
  - 市场层输出 `market_implied_prob / P_mkt_hat`
  - edge 层输出 `edge_raw / edge_net`
  - 执行层只消费 `AlignedMarketFrame + RiskContext`

## 当前 plan 的固定修改

### 概率定义

- `model_win_prob`: 原始模型输出
- `fair_win_prob`: 校准后的公平胜率

```text
fair_win_prob = calibrator(model_win_prob)
```

### DataPackage 必须补的字段

- `visibility_flags`
- `feature_version`

### DataSimulator 必须是双粒度

- 基础时钟：每 10 秒一个快照
- 事件时钟：关键事件立即补发 `DataPackage`

关键事件至少包括：

- `round_end`
- `pistol_round_end`
- `economy_reset`
- `timeout_start`
- `bomb_exploded`
- `bomb_defused`

### MarketAligner 必须输出对齐质量

- `market_snapshot_ts_s`
- `market_age_ms`
- `alignment_gap_ms`
- `is_stale_snapshot`

### edge 必须拆成本项

- `fees`
- `slippage_est`
- `latency_penalty`
- `liquidity_penalty`
- `edge_raw`
- `edge_net`

### 极端概率规则不是绝对交易命令

- `fair_win_prob >= 0.90`: 允许继续持有已有顺势仓位
- `fair_win_prob <= 0.10`: 强制平掉 `YES` 仓位，或允许切到 `NO`

但不能绕过：

- 风控
- 流动性要求
- stale 市场限制

### 标签切分必须防泄漏

- 按 `match_id / series_id / tournament_date` 分组切分
- 同一场比赛不同时间片不能同时进入 train 和 val/test
- 不能让未来事件泄漏到过去样本

### AgentCommander 不能只看 edge 数值

执行层必须消费：

- `AlignedMarketFrame`
- `RiskContext`

因为执行还依赖：

- spread
- depth
- stale 状态
- 当前持仓
- drawdown
- 赛事等级
- 开仓权限 / reduce-only

## V1 比赛数据

V1 比赛数据层先固定使用下面 13 个 Kaggle CSDS 文件：

- `header.parquet`
- `csds.parquet`
- `round_start.parquet`
- `round_state.parquet`
- `round_end.parquet`
- `player_status.parquet`
- `player_info.parquet`
- `player_death.parquet`
- `bomb_state.parquet`
- `player_hurt.parquet`
- `bomb_action.parquet`
- `player_personal.parquet`
- `item_equip.parquet`

### V1 文件职责

- `header`: 比赛级元数据，含 `map_name`、`tick_rate`
- `csds`: 比赛/样本元信息与索引
- `round_start`: 回合开始边界
- `round_state`: 回合状态主通道，提供比分、phase、时间轴
- `round_end`: 回合结束事件，用于关键事件驱动与标签对齐
- `player_status`: 玩家逐时状态，用于经济、存活、装备价值聚合
- `player_info`: 玩家到队伍 / side 的映射，用于稳定 team identity
- `player_death`: 击杀事件，用于人数优势和事件切片
- `bomb_state`: 炸弹状态，用于 planted / exploded / defused
- `player_hurt`: 伤害事件，用于交火强度与序列特征
- `bomb_action`: 下包 / 拆包 / 丢包 / 捡包动作
- `player_personal`: 稳定身份字段，用于跨回合实体跟踪
- `item_equip`: 装备事件，用于经济与装备解释

### V1 目标

先保证：

1. 能稳定构建 `scoreboard`
2. 能稳定构建 `team_state`
3. 能稳定构建 `event_log`
4. 能补出可选 `player_state`
5. 能支持后续接入 Polymarket 历史市场数据做 `edge_net`

## 外部数据层依赖

除了 Kaggle 比赛数据，还必须补 4 类外部数据。

### 1. Polymarket 市场快照数据

至少要有：

- `timestamp`
- `best_bid`
- `best_ask`
- `mid`
- `depth`
- `volume`
- `spread`

用途：

- 市场时间对齐
- `market_implied_prob`
- 市场中枢滤波
- 滑点与流动性惩罚估计

### 2. 赛前先验数据

至少要有：

- `HLTV ranking`
- `Elo`
- 队伍近期状态
- `map pool` 强弱
- 开盘赔率

用途：

- prior
- baseline 特征
- 赛前强弱建模

### 3. 赛事等级和赛事质量数据

至少要有：

- `event_tier`
- 比赛重要性
- 队伍级别
- 是否官方大赛
- 是否低级别比赛

用途：

- 决定是否允许开仓
- 进入 `RiskContext`
- 策略过滤与分层评估

### 4. 队伍和选手名称标准化映射表

至少要覆盖：

- Kaggle 比赛名
- HLTV 名称
- Polymarket 市场标题名称

至少要有：

- `source_name`
- `normalized_name`
- `source_system`
- `team_id`
- alias 列表

用途：

- 实体对齐
- 市场匹配
- 统一历史统计

### 数据层优先级

第一优先级：

- Kaggle 比赛数据
- Polymarket 市场快照

第二优先级：

- 赛前先验
- 赛事质量

第三优先级：

- 名称标准化映射

## 算法层最终推荐

不是继续把贝叶斯越堆越复杂，而是升级成分层混合算法：

> 贝叶斯规则层 + CatBoost 主胜率模型 + 序列模型增益层 + 概率校准层 + 市场滤波层 + 成本感知错价判定 + Bandit/PPO 执行层 + GA/CMA-ES 参数进化层

```text
P_fair = Calibrate(w1 * P_cat + w2 * P_bayes + w3 * P_seq)
edge_raw = P_fair - P_mkt_hat
edge_net = edge_raw - fee - slippage - latency - liquidity
action = pi(edge_net, spread, depth, drawdown, inventory)
```

### 分层职责

#### 1. 主胜率模型

- 首选 `CatBoost`
- 可替代 `LightGBM`

适合结构化强交互特征：

- 比分
- 经济差
- 存活人数差
- 手枪局
- map / side
- BO3 map 位置
- Elo / HLTV / 开盘先验

```text
P_cat = f_CatBoost(x_t)
```

#### 2. 贝叶斯规则层

贝叶斯不单独扛全部预测，只做规则修正，处理强逻辑事件：

- 手枪局
- 经济崩溃
- 人数优势
- 连续强起失败
- 暂停后的 momentum 变化

```text
P_bayes = BayesUpdate(P_prior, E_t)
```

实际落地建议：

- `CatBoost` 给基础概率
- `Bayes` 只做修正

#### 3. 序列增益层

优先：

- `TCN`

后续再考虑：

- `Transformer Encoder`

用途：

- 最近几回合经济演化
- 人数交换趋势
- 爆弹与残局成功率
- 最近 30 到 60 秒比赛状态与市场偏离轨迹

```text
P_seq = f_TCN_or_Transformer(x_{t-k:t})
```

#### 4. 概率校准层

推荐顺序：

- `Platt scaling`
- `Isotonic regression`
- `Beta calibration`

```text
P_ensemble = w1 * P_cat + w2 * P_bayes + w3 * P_seq
P_fair = Calibrator(P_ensemble)
```

#### 5. 市场共识滤波层

第一阶段推荐：

- `Logit-Kalman Filter`

后续如有必要再考虑：

- `Unscented Kalman Filter`
- `Particle Filter`

#### 6. 错价判定层

```text
edge_net = P_fair - P_mkt_hat - C
C = fee + slippage + latency_penalty + liquidity_penalty
```

只有 `edge_net > threshold` 才允许入场。

#### 7. 执行层

第一阶段：

- `Contextual Bandit`

负责：

- 是否入场
- YES / NO
- 仓位档位
- 挂单 / 吃单

后续升级：

- `Constrained PPO`

但 PPO 只负责执行，不负责学习谁会赢。

#### 8. 元优化层

推荐：

- `GA`
- `CMA-ES`
- `Population-Based Training`

只优化策略超参数：

- entry / exit threshold
- min depth
- max spread
- ensemble 权重
- latency penalty
- size buckets
- 风控参数

不要让进化算法训练主预测模型参数。

### 唯一推荐名称

> Calibrated CatBoost + Bayesian Rule Layer + TCN Sequence Layer + Logit Kalman Market Filter + Cost-Aware Edge Scorer + Contextual Bandit Execution + CMA-ES Hyperparameter Evolution

### 为什么不是纯贝叶斯到底

1. 特征依赖强，朴素贝叶斯容易重复计数。
2. 特征交互复杂，GBDT 更擅长。
3. 时序性强，需要序列层。
4. 交易系统还要处理市场噪音、成本、深度、延迟和仓位。

### 版本路线

- `V1`: Baseline Bayesian + DataSimulator + MarketAligner + EdgeCalculator + Rule Strategy
- `V2`: CatBoost + Bayesian Layer + Calibrator
- `V3`: + TCN + Logit Kalman
- `V4`: + Contextual Bandit
- `V5`: + Constrained PPO + CMA-ES / PBT

### 生产级目标形态

```text
P_fair = Calibrate(0.5 * P_cat + 0.2 * P_bayes + 0.3 * P_tcn)
P_mkt_hat = KalmanFilter(mid, spread, depth, vol)
edge_net = P_fair - P_mkt_hat - fee - slip - latency - liquidity
a_t = Bandit_or_PPO(edge_net, spread, depth, dd, inv)
theta_star = CMA_ES(thresholds, weights, risk_params)
```

### 当前最优先的 5 个模块

1. `CatBoost`
2. `Bayesian rule layer`
3. `Probability calibration`
4. `Logit Kalman`
5. `Contextual Bandit`

## 训练与交易分工

系统里同时存在两条线：

1. 比赛真实世界
2. 市场定价世界

### 最核心的一句话

模型训练的是：

> 在当前比赛状态下，真实有多大概率最终赢下比赛。

监督标签是最终比赛结果，不是 `Polymarket` 价格。

### 为什么不能拿 Polymarket 价格当训练标签

因为市场价格只是：

- 市场共识
- 带噪声
- 带情绪
- 带流动性偏差
- 带手续费和点差影响

如果用市场价格当标签，模型会学成“市场怎么想”，而不是“真实胜率应该是多少”。

### 训练时发生什么

从比赛数据切出很多时间点样本：

- 某秒
- 某次击杀后
- 某次下包后
- 某回合结束后

每个样本输入当前状态特征，标签是最终比赛结果。

模型学习的是：

```text
P(final_win | current_match_state)
```

输出：

- `model_win_prob`
- 经校准后得到 `fair_win_prob`

### Polymarket 数据在系统里的 4 个作用

1. 时间对齐
   - 用 `MarketAligner` 在 `available_ts_s` 时刻匹配当时真实可见的市场快照
2. 偏差分析
   - 分析模型与市场在哪些状态下分歧最大
3. 计算 edge
   - `edge_raw = fair_win_prob - market_implied_prob`
   - `edge_net = edge_raw - cost`
4. 交易回测
   - 回放真实盘口、深度、成交与成本环境

### 训练阶段和交易阶段的明确分工

训练阶段：

```text
CS2_state -> model -> fair_win_prob
label = final_match_outcome
```

这个阶段里，哪怕没有 `Polymarket` 数据，也可以训练比赛胜率模型。

交易 / 回测阶段：

```text
CS2_state -> fair_win_prob
Polymarket_snapshot -> market_implied_prob
fair_win_prob - market_implied_prob -> edge_raw
edge_raw - cost -> edge_net
edge_net + risk_rules -> action
```

### 裁判和盘口的类比

- 模型像独立裁判，只根据比赛状态判断谁更该赢
- Polymarket 像报价机，只给出市场当前愿意交易的价格

交易逻辑是：

> 当独立裁判的判断和盘口报价之间出现足够大且可执行的偏差时，才下单。

### 系统里其实有两个预测器

预测器 A：比赛预测器

- 输出：`fair_win_prob`
- 标签：最终比赛结果
- 数据：CS2 比赛状态
- 作用：判断真实胜率

预测器 B：市场执行器

- 输出：`ENTER / HOLD / EXIT / SKIP`、仓位、YES/NO
- 目标：净盈利、控制回撤、减少无效交易
- 数据：`fair_win_prob + 市场数据 + 成本 + 风控`
- 作用：判断怎么交易

### 最该避免的错误

1. 直接用 `Polymarket` 价格监督训练比赛模型
2. 只因为模型和市场不一致就直接交易
3. 把“预测比赛”和“执行交易”混成一个模型

必须坚持：

- 一个模型负责 `fair_win_prob`
- 一个模块负责 `edge_net`
- 一个策略模块负责动作

### 最后一条总结

比赛模型回答：

> 按比赛本身看，谁更可能赢？

市场数据回答：

> 市场当前把这个概率报价成了多少？

交易系统真正关心的是：

> 我的真实概率判断，和市场报价之间，扣完成本后还有没有剩余优势？

## 实现约束

1. `research` 子系统必须与 Rust runtime 解耦。
2. 只实现 Python 研究 / 回测框架，不实现真实下单。
3. 模块职责清晰、可测试，不要过度抽象。
4. Python 版本 3.10+。
5. 第一版先做最小闭环，不上复杂 ML 框架。

## 后续推进顺序

1. 先守住研究层职责边界，不让市场和策略逻辑反向污染建模层。
2. 先打通真实 CSDS 比赛数据到标准 channel 的映射，再接 Polymarket 历史市场数据。
3. 在真实数据跑通之前，`BayesianPredictor` 保持接口稳定即可，不要过早复杂化。
