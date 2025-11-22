## 目标

* 在 `src/market/models/` 下集中放置三类核心实体（订单、订单簿、成交/类型枚举），理清模块边界。

* 新增面向 Agent 的窄接口网关（`MarketGateway`），代理不直接依赖 `Exchange`。

* 保证 `Exchange` 在仿真上下文中保持单例（同一 `Simulation` 使用一个实例），并通过适配器注入到各 Agent。

## 目录与文件重组

1. 创建目录：`src/market/models/`
2. 移动并重命名（保留原名）：

* `src/market/order.py` → `src/market/models/order.py`

* `src/market/orderbook.py` → `src/market/models/orderbook.py`

* 若有成交/类型枚举同文件，保持在 `order.py` 中；`Trade/OrderType/OrderSide` 一并迁移

1. 更新引用：

* `from ..market.order` 与 `from ..market.orderbook` 改为 `from ..market.models.order` 与 `from ..market.models.orderbook`

* 涉及文件：`src/market/exchange.py`、`src/agents/SimpleAgents.py`、`src/strategy/templates.py` 等

## 引入接口网关

1. 定义 `MarketGateway`（协议/抽象类）：

* `get_account(agent_id) -> Dict`

* `get_market_data(symbol) -> Dict`

* `submit_order(agent_id, symbol, order_type, side, qty, price) -> Tuple[Order, List[Trade]>`

* `get_trade_history(symbol?, agent_id?) -> List[Trade]`

1. 实现 `ExchangeGateway` 适配器：

* 内部持有 `Exchange`（由 `Simulation` 管理单例）

* 方法中直接调用 `Exchange` 的同名能力

1. 在 `Simulation.registerAgent` 注入 `gateway` 到代理：

* 若代理具备 `market` 属性，注入 `ExchangeGateway(self.exchange)`；保留 `exchange` 注入以兼容旧代码

## 单例保证

* `Simulation` 初始化时持有一个 `Exchange` 实例；在 `reset()` 重新生成交易所实例，但仍作为此 `Simulation` 的唯一实例（`src/environment/simulation.py` 已具备）。

* 不在全局创建单例；通过 `Simulation` 生命周期保证作用域内唯一。

## 兼容策略

* 代理可逐步迁移：先新增使用 `market` 网关的代码路径，保留 `self.exchange` 作为后备。

* 工具链（`src/agents/tool/marketTools.py`）可复用 `exchange` 或改用 `gateway`；初期不强制改造。

## 验证与回滚

* 跑 `python main.py` 验证行情驱动、下单、成交事件与快照输出正常。

* 若出现引用错误，优先修复导入路径；如需回滚，保留原文件路径映射（短期内可在 `src/market/__init__.py` 提供别名导出）。

## 后续扩展

* 将 `MarketGateway` 替换为远程客户端（HTTP/RPC）时，代理代码无需更改。

* 在 `MarketGateway` 中加入批量接口与风控前置检查以优化性能。

