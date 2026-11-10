"""
Forced train/test split.

The test set dates are stored; the data object itself is never handed to any
Stage 4 job. Only the Stage 5 OOS reveal job receives the test key.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd


@dataclass
class SplitConfig:
    test_fraction: float = 0.2          # fallback if MTR calculation is unavailable
    min_train_bars: int = 252           # at least 1 year in-sample
    min_test_bars: int = 63             # at least 1 quarter OOS


@dataclass
class DataSplit:
    train_start: date
    train_end: date
    test_start: date
    test_end: date
    train_bars: int
    test_bars: int
    recommended_by: str                 # "mtr" | "fraction" | "user"


def compute_recommended_split(
    df: pd.DataFrame,
    expected_sharpe: float | None = None,
    config: SplitConfig | None = None,
) -> DataSplit:
    """
    Recommend a train/test split.

    If expected_sharpe is provided, uses an approximation of the Minimum Track
    Record Length (Bailey & López de Prado) to set the test size:
        MTR(SR, SR0=0) ≈ (1 + (1 - skew*SR + (kurt-1)/4 * SR^2)) * (z_alpha / SR)^2
    We use a simplified version: test_bars = ceil((z / SR)^2 * 252) floored at min_test_bars.

    Falls back to fraction split when expected_sharpe is None or MTR is unreliable.
    """
    if config is None:
        config = SplitConfig()

    n = len(df)
    total_bars = n

    if expected_sharpe is not None and expected_sharpe > 0.1:
        # Annualised SR → daily SR
        daily_sr = expected_sharpe / math.sqrt(252)
        # MTR at 95% confidence: z = 1.645
        z = 1.645
        mtr_bars = math.ceil((z / daily_sr) ** 2)
        mtr_bars = max(mtr_bars, config.min_test_bars)
        # Cap at 40% of total data
        mtr_bars = min(mtr_bars, int(total_bars * 0.40))
        test_bars = mtr_bars
        method = "mtr"
    else:
        test_bars = max(
            config.min_test_bars,
            int(total_bars * config.test_fraction),
        )
        method = "fraction"

    train_bars = total_bars - test_bars
    if train_bars < config.min_train_bars:
        # Not enough data; squeeze test to minimum
        train_bars = max(config.min_train_bars, total_bars - config.min_test_bars)
        test_bars = total_bars - train_bars

    split_idx = train_bars
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:]

    return DataSplit(
        train_start=train_df.index[0].date() if hasattr(train_df.index[0], "date") else train_df.index[0],
        train_end=train_df.index[-1].date() if hasattr(train_df.index[-1], "date") else train_df.index[-1],
        test_start=test_df.index[0].date() if hasattr(test_df.index[0], "date") else test_df.index[0],
        test_end=test_df.index[-1].date() if hasattr(test_df.index[-1], "date") else test_df.index[-1],
        train_bars=len(train_df),
        test_bars=len(test_df),
        recommended_by=method,
    )


def apply_split(df: pd.DataFrame, split: DataSplit) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply a confirmed split to a DataFrame, returning (train, test)."""
    idx = df.index
    # Normalise index to date for comparison
    if hasattr(idx[0], "date"):
        dates = pd.Series([i.date() for i in idx], index=idx)
    else:
        dates = pd.Series(idx, index=idx)

    train_mask = dates <= split.train_end
    test_mask = dates >= split.test_start

    return df[train_mask].copy(), df[test_mask].copy()
