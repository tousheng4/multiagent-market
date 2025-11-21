"""
下载常用公开金融数据到 data/raw。

包含：
- Stooq 日线 OHLCV：AAPL、TSLA、SPY
- Fama-French 5 因子（2x3，日频）

运行：python3 data/fetch_public_data.py
"""

from __future__ import annotations

import io
import os
import sys
import zipfile
from urllib.request import urlopen


DEF_SYMBOLS = ["aapl", "tsla", "spy"]


def download_stooq(symbols: list[str], out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for sym in symbols:
        url = f"https://stooq.pl/q/d/l/?s={sym}.us&i=d"
        try:
            with urlopen(url) as resp:
                data = resp.read()
        except Exception as exc:
            print(f"[stooq] download failed for {sym}: {exc}", file=sys.stderr)
            continue
        out_path = os.path.join(out_dir, f"{sym.upper()}_daily.csv")
        with open(out_path, "wb") as f:
            f.write(data)
        print(f"[stooq] wrote {out_path} ({len(data)} bytes)")


def download_fama_french(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    url = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
    try:
        with urlopen(url) as resp:
            zdata = resp.read()
    except Exception as exc:
        print(f"[fama_french] download failed: {exc}", file=sys.stderr)
        return

    zf = zipfile.ZipFile(io.BytesIO(zdata))
    name = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
    if not name:
        print("[fama_french] csv not found in zip", file=sys.stderr)
        return

    content = zf.read(name).decode("utf-8")
    clean_lines = [line for line in content.splitlines() if line.strip() and not line.lower().startswith("copyright")]

    out_path = os.path.join(out_dir, "fama_french_5f_daily.csv")
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        f.write("\n".join(clean_lines) + "\n")
    print(f"[fama_french] wrote {out_path} with {len(clean_lines)} lines")


def main():
    raw_dir = os.path.join(os.path.dirname(__file__), "raw")
    download_stooq(DEF_SYMBOLS, raw_dir)
    download_fama_french(raw_dir)


if __name__ == "__main__":
    main()
