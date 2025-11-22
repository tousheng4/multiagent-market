from __future__ import annotations

from typing import Dict, Iterable, List, Optional
import os
import csv

from ..market.models.exchange import Exchange


class DataLoader:
    """
    读取本地 `data/raw` 目录中的日线CSV与因子CSV，提供迭代接口。

    约定：
    - 价格CSV（来自 stooq）列包含：Date,Open,High,Low,Close,Volume
    - 因子CSV（fama_french_5f_daily.csv）包含日期列（YYYYMMDD 或 YYYY-MM-DD），其他列为因子值
    """

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data"))
        self.raw_dir = os.path.join(self.root_dir, "raw")

    def _read_price_csv(self, filename: str) -> List[Dict]:
        path = os.path.join(self.raw_dir, filename)
        rows: List[Dict] = []
        if not os.path.exists(path):
            return rows
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                # 支持英文与波兰文列名（stooq常见）：
                date = r.get("Date") or r.get("Data") or r.get("date")
                def _num(keys: List[str], cast):
                    for k in keys:
                        v = r.get(k)
                        if v is not None and v != "":
                            try:
                                return cast(v)
                            except Exception:
                                pass
                    return None

                rows.append({
                    "date": date,
                    "close": _num(["Close", "Zamkniecie", "close"], float),
                    "open": _num(["Open", "Otwarcie", "open"], float),
                    "high": _num(["High", "Najwyzszy", "high"], float),
                    "low": _num(["Low", "Najnizszy", "low"], float),
                    "volume": _num(["Volume", "Wolumen", "volume"], lambda x: int(float(x))),
                })
        return rows

    def _read_factors_csv(self, filename: str = "fama_french_5f_daily.csv") -> List[Dict]:
        path = os.path.join(self.raw_dir, filename)
        rows: List[Dict] = []
        if not os.path.exists(path):
            return rows
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                # 统一日期键名
                date_key = next((k for k in r.keys() if k.lower() in ("date", "yyyymmdd")), "date")
                row = {"date": r.get(date_key)}
                for k, v in r.items():
                    if k == date_key:
                        continue
                    try:
                        row[k] = float(v)
                    except Exception:
                        row[k] = None
                rows.append(row)
        return rows

    def load_prices(self, symbols: Iterable[str]) -> Dict[str, List[Dict]]:
        data: Dict[str, List[Dict]] = {}
        for s in symbols:
            filename = f"{s.upper()}_daily.csv"
            data[s] = self._read_price_csv(filename)
        return data

    def load_factors(self) -> List[Dict]:
        return self._read_factors_csv()


class DataFeed:
    """
    将 DataLoader 的数据以时间序列步进的形式推送到 Exchange。
    - 使用收盘价作为 `lastPrice` 更新（可扩展为中间价/盘口）
    - 可选择性携带因子数据，供 Agent 从 MemoryStore 或自取
    """

    def __init__(self, exchange: Exchange, symbols: List[str], loader: Optional[DataLoader] = None):
        self.exchange = exchange
        self.symbols = symbols
        self.loader = loader or DataLoader()
        self.priceData = self.loader.load_prices(symbols)
        self.factors = self.loader.load_factors()
        # 使用索引推进
        self.index = 0
        # 对齐长度（以最短价格序列为准），若没有有效数据则长度为0
        lengths = [len(self.priceData[s]) for s in symbols if self.priceData.get(s)]
        self.length = min(lengths) if lengths else 0

    def step(self) -> Optional[Dict]:
        if self.index >= self.length:
            return None

        snapshot: Dict = {"prices": {}, "factors": {}}

        for s in self.symbols:
            rows = self.priceData.get(s) or []
            if self.index < len(rows):
                px = rows[self.index].get("close")
                if px is not None:
                    # 推送到交易所行情
                    self.exchange.updateMarketPrice(s, px)
                    snapshot["prices"][s] = {"date": rows[self.index].get("date"), "close": px}

        # 附带同日因子（简单示例：按索引对齐；实际可用日期join）
        if self.index < len(self.factors):
            snapshot["factors"] = self.factors[self.index]

        # 推进交易所时间
        self.exchange.step()

        self.index += 1
        return snapshot

    def reset(self) -> None:
        self.index = 0
