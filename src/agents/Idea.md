<!-- File: /root/gf/multiagent-market/src/agents/LLM_MultiAgent_Design.md -->

# LLM 多子代理协作交易思路（基于现有架构）

## 目标
- 在现有架构上增加一个多子代理协作的交易方案
- 支持联网工具获取外部信息
- 保持低耦合、强约束、可回测

## 角色划分
- 数据代理（Data Agent）
  - 订阅 `data` 信号，提炼结构化特征与技术信号
  - 参考：`src/environment/simulation.py:61-63, 99-113`
- 新闻/宏观代理（News/Macro Agent）
  - 定期用联网工具抓取新闻/公告/宏观数据，输出情绪与事件标签
- 策略代理（Strategy Agent，LLM）
  - 整合数据+新闻，生成行动建议 JSON（`buy/sell/hold`、`symbol/qty/limit_price`、理由）
- 风险代理（Risk Agent，规则型）
  - 对建议施加硬约束（资金、持仓、价格、频率），必要时改写为 `hold` 或缩量
- 执行代理（Execution Agent）
  - 落地下单，通过 `exchange.submitOrder` 或工具封装
  - 参考：`src/agents/tool/marketTools.py:228`，`src/market/exchange.py:72-133`
- 评估代理（Evaluator/Monitor）
  - 订阅 `order_submitted` 与 `trade_executed`，归档动作与结果指标，用于复盘与调参
  - 参考：`src/market/exchange.py:50-56, 119-131`

## 数据与工具
- 市场工具（已具备）
  - `get_market_data`、`get_account`、`submit_order`、`get_trade_history`（`src/agents/tool/marketTools.py:228`）
- 联网工具（建议）
  - HTTP 抓取器：URL/查询 → 文本/JSON；限速与重试
  - 新闻搜索器：封装搜索/新闻 API；统一输出：
    - `[{source,title,summary,sentiment,symbols:[...]}, ...]`
  - 安全：密钥走环境变量；失败与速率限制容错
- 特征加工
  - 数据代理将行情转为简要特征（动量、波动、支撑/阻力、盘口价）
  - 新闻代理输出情绪与事件标签

## 事件编排
- 实例级信号命名空间，避免跨实例串扰：
  - 仿真：`src/environment/simulation.py:60-63`
  - 交易所：`src/market/exchange.py:50-56`
- 订阅与生命周期
  - 代理按能力订阅：数据订阅 `data`；评估订阅 `order_submitted/trade_executed`；有快照处理能力的订阅 `market_snapshot`
  - 参考：`src/environment/simulation.py:88-96`
  - 注销：`unregisterAgent(agentId)` 断开订阅与清理（`src/environment/simulation.py:99-116`）
- 协作消息
  - 数据/新闻产出结构化输出；策略代理融合生成建议
  - 建议通过共享内存/轻量队列传递，或用 `logMessage(meta)` 记录（`src/agents/BaseAgent.py:70-90, 91-100`）

## 决策流程
1. `Simulation.step` 触发 `data` 事件 → 数据代理与新闻代理产出要素
2. 策略融合（LLM）
   - Prompt 包含：账户/行情关键字段、新闻摘要、近期记忆
   - 输出严格 JSON：`{"action":"buy|sell|hold","symbol":"TSLA","qty":10,"price":1.23,"reason":"..."}`
3. 风险审查（规则）
   - 资金覆盖、持仓覆盖、最大下单量、限价合理性、频率限制
   - 不通过则改写为 `hold` 或缩量
4. 执行
   - `SubmitOrderTool` 或 `exchange.submitOrder(...)` 落地
5. 反馈
   - 评估代理订阅成交/下单信号，记录绩效与异常，供下轮参考或调参

## 风险控制重点
- 硬约束优先于 LLM：所有建议先走风险代理再执行
- 仓位上下限与单步下单量门槛保持常数或依据波动动态调整
- 异常隔离与日志：
  - 数据/快照发送有独立异常保护（`src/environment/simulation.py:99-147`）
  - 交易所事件派发异常记录（`src/market/exchange.py:119-131`）
- 联网工具必须超时与重试；失败时策略代理仅基于市场数据做降级决策

## 最小落地步骤
- 在 `agents` 目录定义子代理类（继承 `BaseAgent`）：
  - DataAgent：`onEvent(type="data")` 输出特征到本地记忆
  - NewsAgent：定时或按步抓取新闻，解析为情绪与事件标签，写入记忆
  - StrategyAgent（LLM）：读取记忆与账户/行情 → 输出建议 JSON
  - RiskAgent：审查与改写建议
  - ExecutionAgent：提交订单并记录执行结果
- 在 `Simulation.registerAgent` 时按需连接信号（`src/environment/simulation.py:88-96`）
- 在 `main.py` 中注册这些代理并运行若干步评估（`main.py:12-23`）

## 参考范式（开源思路）
- ReAct + 工具调用：各子代理在“思考-行动-观察”闭环内使用有限工具，输出结构化结果，彼此作为上游输入
- 多代理编排：用有向工作流（管线/图）实现角色分工与串并联；LLM 仅在策略融合处参与，其他代理尽量规则化与可测
- 记忆与复盘：每 N 步归档建议、执行与结果，形成回测与在线学习基础

## 扩展方向
- 调度优化：NewsAgent 低频调度（如每 M 步一次），节约资源
- 任务路由：仅在涉及的 `symbols` 上进行策略融合与执行，避免全量遍历
- 多账户支持：在 `Simulation` 层面维护多代理账户，评估收益与风控差异（现有支持，`src/market/exchange.py:218-236`）