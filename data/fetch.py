"""
阶段 1 数据入口：
1) 下载 Stooq + Fama-French 到 data/raw（可选）
2) 清洗并按日期对齐
3) 生成统一快照产物到 data/processed（DuckDB）

示例：
- python data/fetch.py
- python data/fetch.py --skip-download --symbols AAPL,TSLA,SPY
"""

from __future__ import annotations

import argparse
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.data.pipeline import DataLoader


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build unified market snapshots for stage-1 pipeline.")
    parser.add_argument("--symbols", default="AAPL,TSLA,SPY", help="Comma-separated symbols.")
    parser.add_argument("--artifact-name", default="market_snapshots", help="Output artifact name.")
    parser.add_argument("--skip-download", action="store_true", help="Skip download and use existing raw files.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    data_root = os.path.abspath(os.path.dirname(__file__))
    loader = DataLoader(root_dir=data_root)

    if not args.skip_download:
        print(f"[stage1] downloading raw datasets for: {symbols}")
        loader.download(symbols=symbols, with_factors=True)

    print("[stage1] building aligned snapshot frame")
    frame = loader.build(symbols)
    written = loader.save(frame, name=args.artifact_name)

    print(f"[stage1] snapshot rows: {len(frame)}")
    if written:
        print(f"[stage1] wrote duckdb: {written.get('duckdb')}")
        print(f"[stage1] table: {written.get('table')}")
    else:
        print("[stage1] no snapshot artifact written (empty frame)")


if __name__ == "__main__":
    main()
