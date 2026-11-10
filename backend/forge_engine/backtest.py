"""
Core backtesting engine.

Strategy contract:
  - A strategy is a Python class with:
      params: dict[str, float]  — named parameters with their values
      generate_signals(df: pd.DataFrame, params: dict) -> pd.Series
          Returns a position series in [-1, 0, 1] (short, flat, long), indexed like df.
  - The engine handles fills, costs, and P&L.
  - The engine never touches adjusted-close contamination; that is the lookahead scanner's job.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Callable


SignalFn = Callable[[pd.DataFrame, dict], pd.Series]


@dataclass
class BacktestConfig:
    commission_bps: float = 2.0        # one-way, basis points of notional
    slippage_bps: float = 1.0          # one-way, basis points
    spread_bps: float = 1.0            # half-spread applied each side
    initial_capital: float = 100_000.0


@dataclass
class BacktestResult:
    equity: pd.Series                  # daily equity curve
    returns: pd.Series                 # daily net returns
    positions: pd.Series               # position series
    trades: pd.DataFrame               # entry_date, exit_date, pnl, direction
    metrics: dict = field(default_factory=dict)


def run_backtest(
    df: pd.DataFrame,
    signal_fn: SignalFn,
    params: dict,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """
    Run a single backtest on df (OHLCV, indexed by date).
    Returns equity, returns, positions, trades, and summary metrics.
    """
    if config is None:
        config = BacktestConfig()

    positions = signal_fn(df, params)
    positions = positions.reindex(df.index).fillna(0).clip(-1, 1)

    # Daily returns of the underlying
    underlying_returns = df["close"].pct_change().fillna(0)

    # Position changes drive transaction costs
    pos_changes = positions.diff().abs().fillna(positions.abs())
    total_cost_bps = config.commission_bps + config.slippage_bps + config.spread_bps
    cost_per_unit = total_cost_bps / 10_000.0
    costs = pos_changes * cost_per_unit

    # Strategy returns = position(t-1) * return(t) - costs(t)
    strategy_returns = positions.shift(1).fillna(0) * underlying_returns - costs

    equity = (1 + strategy_returns).cumprod() * config.initial_capital

    trades = _extract_trades(positions, df["close"], config)
    metrics = _compute_metrics(strategy_returns, equity, config)

    return BacktestResult(
        equity=equity,
        returns=strategy_returns,
        positions=positions,
        trades=trades,
        metrics=metrics,
    )


def _extract_trades(
    positions: pd.Series,
    prices: pd.Series,
    config: BacktestConfig,
) -> pd.DataFrame:
    """Extract individual round-trip trades from position series."""
    records = []
    pos_prev = 0.0
    entry_date = None
    entry_price = None
    direction = 0

    cost_bps = (config.commission_bps + config.slippage_bps + config.spread_bps) / 10_000

    for date, pos in positions.items():
        if pos_prev == 0 and pos != 0:
            # Open
            entry_date = date
            entry_price = prices[date]
            direction = int(pos)
        elif pos_prev != 0 and (pos == 0 or np.sign(pos) != np.sign(pos_prev)):
            # Close
            exit_price = prices[date]
            if entry_price and entry_price > 0:
                raw_ret = direction * (exit_price - entry_price) / entry_price
                cost = cost_bps * 2  # entry + exit
                net_ret = raw_ret - cost
                records.append({
                    "entry_date": entry_date,
                    "exit_date": date,
                    "direction": "long" if direction > 0 else "short",
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "return_pct": net_ret * 100,
                    "pnl": net_ret * config.initial_capital * abs(pos_prev),
                })
            if pos != 0:
                entry_date = date
                entry_price = prices[date]
                direction = int(pos)
            else:
                entry_date = None
                entry_price = None
                direction = 0
        pos_prev = pos

    return pd.DataFrame(records) if records else pd.DataFrame(
        columns=["entry_date", "exit_date", "direction", "entry_price", "exit_price", "return_pct", "pnl"]
    )


def _compute_metrics(
    returns: pd.Series,
    equity: pd.Series,
    config: BacktestConfig,
) -> dict:
    """Compute standard performance metrics from daily return series."""
    ann_factor = 252
    n = len(returns)
    if n < 2:
        return {}

    total_return = equity.iloc[-1] / config.initial_capital - 1
    ann_return = (1 + total_return) ** (ann_factor / n) - 1

    vol = returns.std() * np.sqrt(ann_factor)
    sharpe = ann_return / vol if vol > 0 else 0.0

    neg_returns = returns[returns < 0]
    downside_vol = neg_returns.std() * np.sqrt(ann_factor) if len(neg_returns) > 1 else 0.0
    sortino = ann_return / downside_vol if downside_vol > 0 else 0.0

    # Drawdown
    rolling_max = equity.cummax()
    drawdown = (equity - rolling_max) / rolling_max
    max_dd = drawdown.min()

    calmar = ann_return / abs(max_dd) if max_dd != 0 else 0.0

    # Win rate from non-zero returns
    nonzero = returns[returns != 0]
    win_rate = (nonzero > 0).mean() if len(nonzero) > 0 else 0.0

    # Profit factor
    gross_profit = returns[returns > 0].sum()
    gross_loss = abs(returns[returns < 0].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # CVaR at 1% and 5%
    cvar_1 = returns[returns <= returns.quantile(0.01)].mean()
    cvar_5 = returns[returns <= returns.quantile(0.05)].mean()

    return {
        "total_return": total_return,
        "annual_return": ann_return,
        "annual_volatility": vol,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "max_drawdown": max_dd,
        "calmar_ratio": calmar,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "cvar_1pct": cvar_1,
        "cvar_5pct": cvar_5,
        "num_days": n,
    }
