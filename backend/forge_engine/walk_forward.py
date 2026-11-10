"""
Walk-forward validation on the training set (Stage 4).

Runs rolling windows: fit parameters on each train fold, evaluate on the following
test fold. Returns fold-level metrics and an aggregate summary.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .backtest import BacktestConfig, BacktestResult, SignalFn, run_backtest, _compute_metrics


@dataclass
class WalkForwardConfig:
    n_folds: int = 5
    gap_bars: int = 0            # bars between train and test fold (purge gap)


@dataclass
class WalkForwardFold:
    fold_num: int
    train_start: object
    train_end: object
    test_start: object
    test_end: object
    metrics: dict


@dataclass
class WalkForwardResult:
    folds: list[WalkForwardFold]
    aggregate: dict               # mean and std of key metrics across folds
    consistency_score: float      # 0–1, fraction of folds with positive Sharpe


def run_walk_forward(
    train_df: pd.DataFrame,
    signal_fn: SignalFn,
    params: dict,
    config: WalkForwardConfig | None = None,
    bt_config: BacktestConfig | None = None,
) -> WalkForwardResult:
    """
    Walk-forward on train_df only. Never touches the test set.
    """
    if config is None:
        config = WalkForwardConfig()
    if bt_config is None:
        bt_config = BacktestConfig()

    n = len(train_df)
    fold_size = n // (config.n_folds + 1)

    folds: list[WalkForwardFold] = []

    for i in range(config.n_folds):
        # Expanding train window
        train_end_idx = (i + 1) * fold_size
        test_start_idx = train_end_idx + config.gap_bars
        test_end_idx = min(test_start_idx + fold_size, n)

        if test_end_idx <= test_start_idx:
            break

        fold_train = train_df.iloc[:train_end_idx]
        fold_test = train_df.iloc[test_start_idx:test_end_idx]

        if len(fold_test) < 20:
            continue

        result = run_backtest(fold_test, signal_fn, params, bt_config)
        metrics = result.metrics

        folds.append(WalkForwardFold(
            fold_num=i + 1,
            train_start=fold_train.index[0],
            train_end=fold_train.index[-1],
            test_start=fold_test.index[0],
            test_end=fold_test.index[-1],
            metrics=metrics,
        ))

    if not folds:
        return WalkForwardResult(folds=[], aggregate={}, consistency_score=0.0)

    aggregate = _aggregate_fold_metrics(folds)
    consistency = sum(1 for f in folds if f.metrics.get("sharpe_ratio", 0) > 0) / len(folds)

    return WalkForwardResult(folds=folds, aggregate=aggregate, consistency_score=consistency)


def _aggregate_fold_metrics(folds: list[WalkForwardFold]) -> dict:
    keys = ["sharpe_ratio", "annual_return", "max_drawdown", "win_rate", "profit_factor"]
    agg = {}
    for k in keys:
        vals = [f.metrics.get(k, np.nan) for f in folds]
        vals = [v for v in vals if not np.isnan(v)]
        if vals:
            agg[f"{k}_mean"] = float(np.mean(vals))
            agg[f"{k}_std"] = float(np.std(vals))
            agg[f"{k}_min"] = float(np.min(vals))
            agg[f"{k}_max"] = float(np.max(vals))
    return agg
