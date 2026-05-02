# Polymarket Bot TODO

## 当前状态
- [x] Rust 项目初始化
- [x] CLOB `ok()` 跑通
- [x] REST 快照拉取（book/tick/fee/neg_risk）
- [x] `jsonl` 落盘（startup + bootstrap snapshot）
- [ ] 自动化执行层（鉴权/下单/撤单）

## TODO 清单
- [ ] **WS 实时流接入（核心）**
  - [ ] 订阅 orderbook/user channel
  - [ ] 处理断线重连与心跳
  - [ ] 去重/乱序保护（按 timestamp/hash）
  - [ ] 无帧超时时降级到 REST 兜底
- [ ] 执行层最小闭环
  - [ ] L1/L2 鉴权
  - [ ] 下单（post-only）+ 撤单/改单
  - [ ] 失败重试与幂等 client_order_id
- [ ] 风控层
  - [ ] 单笔风险上限
  - [ ] 单市场仓位上限
  - [ ] 日内回撤熔断（kill-switch）
- [ ] 策略层 v0
  - [ ] 先做单一错价策略（dry-run）
  - [ ] 记录信号、理论成交、实际成交偏差
- [ ] 观测与复盘
  - [ ] 结构化日志（json）
  - [ ] PnL 归因（手续费/滑点/库存）
  - [ ] 每日回放与参数复盘

## 里程碑
- [ ] M1: 数据层稳定（REST + WS）
- [ ] M2: 执行层可用（小额实盘前）
- [ ] M3: 风控上线（必须先于实盘）
- [ ] M4: $100 小额实盘 14 天验证
