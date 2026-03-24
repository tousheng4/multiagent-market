from __future__ import annotations

import fcntl
import io
import os
import re
import zipfile
from typing import Dict, Iterable, List, Optional
from urllib.request import urlopen

import duckdb
import pandas as pd

from ..market.models.exchange import Exchange


class SnapshotStore:
    """Build/save/read snapshots with DuckDB."""

    def __init__(self, out_dir: str):
        self.out_dir = out_dir

    @staticmethod
    def _table(name: str) -> str:
        normalized_name = (
            re.sub(r"[^A-Za-z0-9_]", "_", name).strip("_") or "market_snapshots"
        )
        return (
            f"t_{normalized_name}" if normalized_name[0].isdigit() else normalized_name
        )

    def _database_path(self, name: str) -> str:
        return os.path.join(self.out_dir, f"{name}.duckdb")

    def _lock(self, name: str) -> str:
        return os.path.join(self.out_dir, f"{name}.lock")

    def build(self, symbols: Iterable[str], raw_dir: str) -> pd.DataFrame:
        upper_symbols = [symbol.upper() for symbol in symbols]
        connection = duckdb.connect(database=":memory:")
        ready_symbols: List[str] = []

        try:
            for symbol in upper_symbols:
                file_path = os.path.join(raw_dir, f"{symbol}_daily.csv")
                if not os.path.exists(file_path):
                    continue
                escaped_file_path = file_path.replace("'", "''")

                source_columns = {
                    column_meta[0]
                    for column_meta in connection.execute(
                        f"SELECT * FROM read_csv_auto('{escaped_file_path}', header=true, all_varchar=true, ignore_errors=true) LIMIT 0"
                    ).description
                }

                def pick(candidates: List[str]) -> str:
                    for candidate in candidates:
                        if candidate in source_columns:
                            return f'"{candidate}"'
                    return "NULL"

                date_expr = pick(["Date", "Data", "date"])
                close_expr = pick(["Close", "Zamkniecie", "close"])
                open_expr = pick(["Open", "Otwarcie", "open"])
                high_expr = pick(["High", "Najwyzszy", "high"])
                low_expr = pick(["Low", "Najnizszy", "low"])
                volume_expr = pick(["Volume", "Wolumen", "volume"])

                # 缺少核心列时直接跳过该 symbol，避免后续 inner join 清空整体结果
                if date_expr == "NULL" or close_expr == "NULL":
                    continue

                view_name = f"price_{symbol}"
                connection.execute(
                    f"""
                    CREATE OR REPLACE TEMP VIEW "{view_name}" AS
                    WITH source_rows AS (
                      SELECT
                        COALESCE(
                          try_strptime({date_expr}, '%Y-%m-%d'),
                          try_strptime({date_expr}, '%Y%m%d')
                        ) AS parsed_date,
                        try_cast({close_expr} AS DOUBLE) AS close,
                        try_cast({open_expr} AS DOUBLE) AS open,
                        try_cast({high_expr} AS DOUBLE) AS high,
                        try_cast({low_expr} AS DOUBLE) AS low,
                        try_cast({volume_expr} AS BIGINT) AS volume
                      FROM read_csv_auto('{escaped_file_path}', header=true, all_varchar=true, ignore_errors=true)
                    )
                    SELECT
                      strftime(parsed_date, '%Y-%m-%d') AS date,
                      COALESCE(open, close) AS open,
                      COALESCE(high, close) AS high,
                      COALESCE(low, close) AS low,
                      close,
                      COALESCE(volume, 0) AS volume
                    FROM source_rows
                    WHERE parsed_date IS NOT NULL AND close IS NOT NULL
                    QUALIFY ROW_NUMBER() OVER (PARTITION BY parsed_date ORDER BY parsed_date DESC) = 1
                    """,
                )
                row_count = connection.execute(
                    f'SELECT COUNT(*) FROM "{view_name}"'
                ).fetchone()
                if row_count and int(row_count[0]) > 0:
                    ready_symbols.append(symbol)

            if not ready_symbols:
                return pd.DataFrame()

            base_symbol = ready_symbols[0]
            select_columns: List[str] = ["base_prices.date"]
            for index, symbol in enumerate(ready_symbols):
                table_alias = "base_prices" if index == 0 else f"joined_prices_{index}"
                select_columns.extend(
                    [
                        f'{table_alias}.open AS "{symbol}_open"',
                        f'{table_alias}.high AS "{symbol}_high"',
                        f'{table_alias}.low AS "{symbol}_low"',
                        f'{table_alias}.close AS "{symbol}_close"',
                        f'{table_alias}.volume AS "{symbol}_volume"',
                    ]
                )

            join_clauses: List[str] = []
            for index, symbol in enumerate(ready_symbols[1:], start=1):
                join_clauses.append(
                    f'INNER JOIN "price_{symbol}" joined_prices_{index} ON joined_prices_{index}.date = base_prices.date'
                )

            connection.execute(f"""
                CREATE OR REPLACE TEMP VIEW snapshot_prices AS
                SELECT {", ".join(select_columns)}
                FROM "price_{base_symbol}" base_prices
                {" ".join(join_clauses)}
                ORDER BY base_prices.date
                """)

            factor_file_path = os.path.join(raw_dir, "fama_french_5f_daily.csv")
            if not os.path.exists(factor_file_path):
                output_frame = connection.execute(
                    "SELECT * FROM snapshot_prices ORDER BY date"
                ).fetchdf()
            else:
                escaped_factor_path = factor_file_path.replace("'", "''")
                connection.execute(
                    """
                    CREATE OR REPLACE TEMP VIEW factor_rows AS
                    WITH source_rows AS (
                      SELECT
                        raw_date,
                        mkt_rf_raw,
                        smb_raw,
                        hml_raw,
                        rmw_raw,
                        cma_raw,
                        rf_raw
                      FROM read_csv(
                        '__FAC_PATH__',
                        header=false,
                        delim=',',
                        all_varchar=true,
                        null_padding=true,
                        strict_mode=false,
                        ignore_errors=true,
                        columns={
                          'raw_date':'VARCHAR',
                          'mkt_rf_raw':'VARCHAR',
                          'smb_raw':'VARCHAR',
                          'hml_raw':'VARCHAR',
                          'rmw_raw':'VARCHAR',
                          'cma_raw':'VARCHAR',
                          'rf_raw':'VARCHAR'
                        }
                      )
                    )
                    SELECT
                      strftime(
                        COALESCE(
                          try_strptime(raw_date, '%Y%m%d'),
                          try_strptime(raw_date, '%Y-%m-%d')
                        ),
                        '%Y-%m-%d'
                      ) AS date,
                      try_cast(mkt_rf_raw AS DOUBLE) AS "factor_Mkt-RF",
                      try_cast(smb_raw AS DOUBLE) AS "factor_SMB",
                      try_cast(hml_raw AS DOUBLE) AS "factor_HML",
                      try_cast(rmw_raw AS DOUBLE) AS "factor_RMW",
                      try_cast(cma_raw AS DOUBLE) AS "factor_CMA",
                      try_cast(rf_raw AS DOUBLE) AS "factor_RF"
                    FROM source_rows
                    WHERE regexp_full_match(raw_date, '^\\d{8}$') OR regexp_full_match(raw_date, '^\\d{4}-\\d{2}-\\d{2}$')
                    QUALIFY ROW_NUMBER() OVER (PARTITION BY raw_date ORDER BY raw_date DESC) = 1
                    """.replace("__FAC_PATH__", escaped_factor_path),
                )

                factor_columns = [
                    "factor_Mkt-RF",
                    "factor_SMB",
                    "factor_HML",
                    "factor_RMW",
                    "factor_CMA",
                    "factor_RF",
                ]
                factor_fill_expressions: List[str] = []
                for factor_column in factor_columns:
                    factor_fill_expressions.append(f"""
                        COALESCE(
                          LAST_VALUE(factor_rows."{factor_column}" IGNORE NULLS)
                            OVER (ORDER BY snapshot_rows.date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),
                          FIRST_VALUE(factor_rows."{factor_column}" IGNORE NULLS)
                            OVER (ORDER BY snapshot_rows.date ROWS BETWEEN CURRENT ROW AND UNBOUNDED FOLLOWING)
                        ) AS "{factor_column}"
                        """)

                output_frame = connection.execute(f"""
                    SELECT snapshot_rows.*, {", ".join(factor_fill_expressions)}
                    FROM snapshot_prices snapshot_rows
                    LEFT JOIN factor_rows ON factor_rows.date = snapshot_rows.date
                    ORDER BY snapshot_rows.date
                    """).fetchdf()
        finally:
            connection.close()

        if output_frame.empty:
            return output_frame

        output_frame["date"] = pd.to_datetime(
            output_frame["date"], errors="coerce", utc=True
        ).dt.strftime("%Y-%m-%d")
        output_frame = output_frame.dropna(subset=["date"]).sort_values("date")
        output_frame = output_frame.drop_duplicates(subset=["date"], keep="last")
        return output_frame.reset_index(drop=True)

    def save(self, df: pd.DataFrame, name: str = "market_snapshots") -> Dict[str, str]:
        if df.empty:
            return {}

        os.makedirs(self.out_dir, exist_ok=True)
        database_path = self._database_path(name)
        lock_path = self._lock(name)
        table = self._table(name)

        write_frame = df.copy()
        write_frame["date"] = pd.to_datetime(
            write_frame["date"], errors="coerce", utc=True
        ).dt.strftime("%Y-%m-%d")
        write_frame = write_frame.dropna(subset=["date"]).sort_values("date")
        write_frame = write_frame.drop_duplicates(subset=["date"], keep="last")

        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                connection = duckdb.connect(database=database_path)
                committed = False
                try:
                    connection.execute("BEGIN TRANSACTION")
                    connection.register("tmp_write_frame", write_frame)
                    connection.execute(
                        f'CREATE OR REPLACE TABLE "{table}" AS SELECT * FROM tmp_write_frame'
                    )
                    connection.unregister("tmp_write_frame")
                    connection.execute(
                        f'CREATE INDEX IF NOT EXISTS "idx_{table}_date" ON "{table}" (date)'
                    )
                    connection.execute("COMMIT")
                    committed = True
                finally:
                    if not committed:
                        try:
                            connection.execute("ROLLBACK")
                        except Exception:
                            pass
                    connection.close()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        return {"duckdb": database_path, "table": table}

    def read(self, name: str = "market_snapshots") -> Optional[pd.DataFrame]:
        database_path = self._database_path(name)
        lock_path = self._lock(name)
        if not os.path.exists(database_path):
            return None

        table = self._table(name)
        with open(lock_path, "a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            try:
                connection = duckdb.connect(database=database_path, read_only=True)
                try:
                    table_count_result = connection.execute(
                        """
                        SELECT COUNT(*)
                        FROM information_schema.tables
                        WHERE table_schema = 'main' AND table_name = ?
                        """,
                        [table],
                    ).fetchone()
                    if not table_count_result or int(table_count_result[0]) == 0:
                        return None
                    output_frame = connection.execute(
                        f'SELECT * FROM "{table}" ORDER BY date'
                    ).fetchdf()
                finally:
                    connection.close()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

        if output_frame.empty or "date" not in output_frame.columns:
            return None

        output_frame["date"] = pd.to_datetime(
            output_frame["date"], errors="coerce", utc=True
        ).dt.strftime("%Y-%m-%d")
        output_frame = output_frame.dropna(subset=["date"]).sort_values("date")
        output_frame = output_frame.drop_duplicates(subset=["date"], keep="last")
        return output_frame.reset_index(drop=True)

    def rows(self, df: Optional[pd.DataFrame], symbols: Iterable[str]) -> List[Dict]:
        if df is None or df.empty:
            return []

        upper_symbols = [symbol.upper() for symbol in symbols]
        output_rows: List[Dict] = []

        for record in df.to_dict(orient="records"):
            prices_by_symbol: Dict[str, Dict] = {}
            for symbol in upper_symbols:
                close_value = record.get(f"{symbol}_close")
                if close_value is None or (
                    isinstance(close_value, float) and pd.isna(close_value)
                ):
                    continue
                open_value = record.get(f"{symbol}_open")
                high_value = record.get(f"{symbol}_high")
                low_value = record.get(f"{symbol}_low")
                volume_value = record.get(f"{symbol}_volume")
                prices_by_symbol[symbol] = {
                    "date": record.get("date"),
                    "close": float(close_value),
                    "open": (
                        None
                        if (
                            open_value is None
                            or (isinstance(open_value, float) and pd.isna(open_value))
                        )
                        else float(open_value)
                    ),
                    "high": (
                        None
                        if (
                            high_value is None
                            or (isinstance(high_value, float) and pd.isna(high_value))
                        )
                        else float(high_value)
                    ),
                    "low": (
                        None
                        if (
                            low_value is None
                            or (isinstance(low_value, float) and pd.isna(low_value))
                        )
                        else float(low_value)
                    ),
                    "volume": (
                        0
                        if (
                            volume_value is None
                            or (
                                isinstance(volume_value, float)
                                and pd.isna(volume_value)
                            )
                        )
                        else int(volume_value)
                    ),
                }

            factors_by_name = {
                key.replace("factor_", "", 1): float(value)
                for key, value in record.items()
                if key.startswith("factor_")
                and not (value is None or (isinstance(value, float) and pd.isna(value)))
            }
            output_rows.append(
                {
                    "date": record.get("date"),
                    "prices": prices_by_symbol,
                    "factors": factors_by_name,
                }
            )

        return output_rows


class DataLoader:
    """Data entry: download, build snapshot, read/write snapshot, make rows."""

    DEFAULT = ["AAPL", "TSLA", "SPY"]

    def __init__(self, root_dir: Optional[str] = None):
        base = root_dir or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data")
        )
        self.root_dir = base
        self.raw_dir = os.path.join(base, "raw")
        self.out_dir = os.path.join(base, "processed")
        self.store = SnapshotStore(self.out_dir)

    def download(
        self, symbols: Optional[Iterable[str]] = None, with_factors: bool = True
    ) -> None:
        upper_symbols = [symbol.upper() for symbol in (symbols or self.DEFAULT)]
        os.makedirs(self.raw_dir, exist_ok=True)

        for symbol in upper_symbols:
            stooq_url = f"https://stooq.pl/q/d/l/?s={symbol.lower()}.us&i=d"
            try:
                with urlopen(stooq_url) as response:
                    response_bytes = response.read()
            except Exception:
                continue
            with open(
                os.path.join(self.raw_dir, f"{symbol}_daily.csv"), "wb"
            ) as output_file:
                output_file.write(response_bytes)

        if not with_factors:
            return

        factors_zip_url = (
            "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
            "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip"
        )
        try:
            with urlopen(factors_zip_url) as response:
                response_bytes = response.read()
        except Exception:
            return

        zip_archive = zipfile.ZipFile(io.BytesIO(response_bytes))
        archive_csv_name = next(
            (
                member_name
                for member_name in zip_archive.namelist()
                if member_name.lower().endswith(".csv")
            ),
            None,
        )
        if not archive_csv_name:
            return
        with open(
            os.path.join(self.raw_dir, "fama_french_5f_daily.csv"),
            "w",
            encoding="utf-8",
            newline="",
        ) as output_file:
            output_file.write(zip_archive.read(archive_csv_name).decode("utf-8"))

    def build(self, symbols: Iterable[str]) -> pd.DataFrame:
        return self.store.build(
            [symbol.upper() for symbol in symbols],
            self.raw_dir,
        )

    def save(self, df: pd.DataFrame, name: str = "market_snapshots") -> Dict[str, str]:
        return self.store.save(df, name)

    def read(self, name: str = "market_snapshots") -> Optional[pd.DataFrame]:
        return self.store.read(name)

    def rows(
        self,
        symbols: Iterable[str],
        name: str = "market_snapshots",
        prefer: bool = True,
        persist: bool = True,
    ) -> List[Dict]:
        upper_symbols = [symbol.upper() for symbol in symbols]
        snapshot_frame: Optional[pd.DataFrame] = self.read(name) if prefer else None
        if snapshot_frame is None:
            snapshot_frame = self.build(upper_symbols)
            if persist and not snapshot_frame.empty:
                self.save(snapshot_frame, name)
        return self.store.rows(snapshot_frame, upper_symbols)


class DataFeed:
    """Step feed driven by snapshot rows."""

    def __init__(
        self,
        exchange: Exchange,
        symbols: List[str],
        loader: Optional[DataLoader] = None,
        snapshot_name: str = "market_snapshots",
        prefer_snapshot: bool = True,
        save_snapshot: bool = True,
    ):
        self.exchange = exchange
        self.symbols = [symbol.upper() for symbol in symbols]
        self.loader = loader or DataLoader()
        self.rows_data = self.loader.rows(
            self.symbols,
            name=snapshot_name,
            prefer=prefer_snapshot,
            persist=save_snapshot,
        )
        self.index = 0
        self.length = len(self.rows_data)

    def step(self) -> Optional[Dict]:
        if self.index >= self.length:
            return None
        row = self.rows_data[self.index]
        for symbol, price_record in row.get("prices", {}).items():
            close_price = price_record.get("close")
            if close_price is not None:
                self.exchange.update_price(symbol, float(close_price))
        self.exchange.step()
        self.index += 1
        return row

    def reset(self) -> None:
        self.index = 0
