"""
Market data loader.

Priority:
  1. Built-in ES/NQ local datasets (OHLCV + TBBO) — no API, no latency.
  2. User-uploaded CSV/Parquet.
  3. yfinance fallback (development only; replace with Polygon.io in production).
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

# Location of bundled data files (populated at build time or via download script)
_DATA_DIR = Path(os.environ.get("FORGE_DATA_DIR", "/app/data"))

# Canonical column names expected throughout the engine
OHLCV_COLS = ["open", "high", "low", "close", "volume"]


def load_instrument(
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    timeframe: str = "1D",
) -> pd.DataFrame:
    """
    Load OHLCV data for a symbol.

    Tries local bundled data first, then yfinance fallback.
    Returns a DataFrame with lowercase OHLCV columns, DatetimeIndex.
    """
    # Normalise symbol
    symbol_upper = symbol.upper().replace("/", "").replace("-", "")

    # 1. Local bundled data
    local = _load_local(symbol_upper, timeframe)
    if local is not None:
        return _slice(local, start, end)

    # 2. yfinance fallback (dev)
    try:
        return _load_yfinance(symbol, start, end, timeframe)
    except Exception as e:
        raise RuntimeError(
            f"No local data for {symbol} and yfinance failed: {e}. "
            "Upload a CSV/Parquet file or connect Polygon.io."
        ) from e


def load_from_file(path: str | Path) -> pd.DataFrame:
    """Load user-uploaded CSV or Parquet file."""
    path = Path(path)
    if path.suffix.lower() == ".parquet":
        df = pd.read_parquet(path)
    else:
        df = pd.read_csv(path, parse_dates=True, index_col=0)

    return _normalise(df)


def _load_local(symbol: str, timeframe: str) -> pd.DataFrame | None:
    """Try to load from the bundled data directory."""
    candidates = [
        _DATA_DIR / f"{symbol}_{timeframe}.parquet",
        _DATA_DIR / f"{symbol}_{timeframe}.csv",
        _DATA_DIR / f"{symbol}.parquet",
        _DATA_DIR / f"{symbol}.csv",
    ]
    for path in candidates:
        if path.exists():
            if path.suffix == ".parquet":
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path, parse_dates=True, index_col=0)
            return _normalise(df)
    return None


def _load_yfinance(
    symbol: str,
    start: str | None,
    end: str | None,
    timeframe: str,
) -> pd.DataFrame:
    """yfinance fallback — daily data only in free tier."""
    import yfinance as yf  # type: ignore

    # Map timeframe to yfinance interval
    interval_map = {
        "1D": "1d", "1H": "1h", "15M": "15m", "5M": "5m", "1M": "1m",
    }
    interval = interval_map.get(timeframe.upper(), "1d")

    kwargs: dict = {"period": "max" if start is None else None}
    if start:
        kwargs = {"start": start}
    if end:
        kwargs["end"] = end

    ticker = yf.Ticker(symbol)
    df = ticker.history(interval=interval, **kwargs)
    return _normalise(df)


def _normalise(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure lowercase OHLCV columns and DatetimeIndex."""
    df = df.copy()
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]

    # Map common alternative names
    rename = {
        "adj_close": "close",
        "adjclose": "close",
        "vol": "volume",
    }
    df = df.rename(columns=rename)

    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    df = df.sort_index()

    # Keep only OHLCV
    present = [c for c in OHLCV_COLS if c in df.columns]
    return df[present].dropna(subset=["close"])


def _slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if start:
        df = df[df.index >= pd.Timestamp(start)]
    if end:
        df = df[df.index <= pd.Timestamp(end)]
    return df
