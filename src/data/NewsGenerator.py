"""
模拟新闻生成器

根据价格变动生成伪新闻，通过 EventHub 发出 EV_NEWS 事件。
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from ..environment.event_hub import EventHub


# 简单的新闻模板，按价格变动方向选择
TEMPLATES_UP = [
    "{symbol} 上涨 {pct:.1f}%，受益于AI芯片需求旺盛",
    "{symbol} 涨 {pct:.1f}%，分析师上调目标价",
    "{symbol} 大涨 {pct:.1f}%，机构资金大幅流入",
    "{symbol} 攀升 {pct:.1f}%，财报超预期",
    "{symbol} 走强 {pct:.1f}%，行业景气度回升",
]
TEMPLATES_DOWN = [
    "{symbol} 下跌 {pct:.1f}%，获利盘了结",
    "{symbol} 跌 {pct:.1f}%，市场情绪谨慎",
    "{symbol} 大跌 {pct:.1f}%，机构抛售",
    "{symbol} 走低 {pct:.1f}%，宏观压力显现",
    "{symbol} 走弱 {pct:.1f}%，行业数据不及预期",
]
TEMPLATES_FLAT = [
    "{symbol} 走势平稳，基本面无明显变化",
    "{symbol} 小幅波动，市场观望情绪浓厚",
    "{symbol} 区间震荡，成交清淡",
]


class NewsGenerator:
    """模拟新闻生成器"""

    def __init__(self, hub: "EventHub", symbols: List[str]):
        self.hub = hub
        self.symbols = symbols
        # 价格缓存：symbol -> 上一步的价格
        self._last_prices: Dict[str, float] = {}
        # 历史新闻列表
        self.news_history: List[Dict[str, Any]] = []

    def generate(self, step: int, current_prices: Dict[str, float]) -> None:
        """
        根据当前价格与上一步价格的差异，生成伪新闻并发出 EV_NEWS 事件。

        Args:
            step: 当前仿真步
            current_prices: symbol -> 当前价格
        """
        for symbol in self.symbols:
            last_price = self._last_prices.get(symbol)
            current_price = current_prices.get(symbol)

            news_entry: Dict[str, Any] = {
                "symbol": symbol,
                "step": step,
                "news": "",
                "change_pct": 0.0,
            }

            if last_price is not None and current_price is not None and last_price > 0:
                pct = (current_price - last_price) / last_price * 100
                news_entry["change_pct"] = pct

                if abs(pct) < 0.1:
                    template = random.choice(TEMPLATES_FLAT)
                elif pct > 0:
                    template = random.choice(TEMPLATES_UP)
                else:
                    template = random.choice(TEMPLATES_DOWN)

                news_entry["news"] = template.format(symbol=symbol, pct=abs(pct))
            else:
                # 无历史价格时用中性模板
                news_entry["news"] = f"{symbol} 今日开始交易，首日成交清淡"

            self.news_history.append(news_entry)

            self.hub.emit(
                "news",
                payload={
                    "symbol": symbol,
                    "news": news_entry["news"],
                    "step": step,
                    "change_pct": news_entry["change_pct"],
                },
                src="news_generator",
            )

        # 更新缓存
        for symbol, price in current_prices.items():
            self._last_prices[symbol] = price

    def get_recent_news(self, n: int = 10) -> List[Dict[str, Any]]:
        """返回最近 n 条新闻"""
        return self.news_history[-n:]
