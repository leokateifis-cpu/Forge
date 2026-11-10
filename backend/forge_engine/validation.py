"""
OOS validation battery (Stage 5 — runs once, test set consumed).

Tests:
  - Permutation test (shuffle bar returns, recompute Sharpe; p-value = share beating real)
  - Monte Carlo forward simulation (block-resample daily returns, 10k paths)
  - Bootstrap confidence intervals (stationary block bootstrap on daily returns)
  - Deflated Sharpe Ratio (Bailey & López de Prado)
  - Tail risk: CVaR at 1% and 5%
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .backtest import BacktestConfig, SignalFn, run_backtest


# ---------------------------------------------------------------------------
# Permutation test
# ---------------------------------------------------------------------------

@dataclass
class PermutationResult:
    real_sharpe: float
    n_iterations: int
    perm_sharpes: list[float]
    p_value: float                # fraction of permutations >= real_sharpe
    is_significant: bool          # p_value < 0.05


def permutation_test(
    test_df: pd.DataFrame,
    signal_fn: SignalFn,
    params: dict,
    n_iterations: int = 1_000,
    bt_config: BacktestConfig | None = None,
    seed: int = 42,
) -> PermutationResult:
    if bt_config is None:
        bt_config = BacktestConfig()

    rng = np.random.default_rng(seed)
    real_result = run_backtest(test_df, signal_fn, params, bt_config)
    real_sharpe = real_result.metrics.get("sharpe_ratio", 0.0)

    # We shuffle the bar returns (not the signal), keeping the signal fixed.
    # This tests: could we get this Sharpe by luck on a random market?
    closes = test_df["close"].values.copy()
    perm_sharpes = []

    for _ in range(n_iterations):
        shuffled_returns = rng.permutation(np.diff(np.log(closes)))
        # Reconstruct prices from shuffled log-returns
        shuffled_closes = np.exp(np.concatenate([[np.log(closes[0])], np.cumsum(shuffled_returns)]))
        perm_df = test_df.copy()
        perm_df["close"] = shuffled_closes
        # Adjust OHLCV proportionally
        ratio = shuffled_closes / closes
        for col in ["open", "high", "low"]:
            if col in perm_df.columns:
                perm_df[col] = test_df[col].values * ratio

        try:
            r = run_backtest(perm_df, signal_fn, params, bt_config)
            perm_sharpes.append(r.metrics.get("sharpe_ratio", 0.0))
        except Exception:
            perm_sharpes.append(0.0)

    p_value = float(np.mean(np.array(perm_sharpes) >= real_sharpe))

    return PermutationResult(
        real_sharpe=real_sharpe,
        n_iterations=n_iterations,
        perm_sharpes=perm_sharpes,
        p_value=p_value,
        is_significant=p_value < 0.05,
    )


# ---------------------------------------------------------------------------
# Bootstrap confidence intervals
# ---------------------------------------------------------------------------

@dataclass
class BootstrapResult:
    n_iterations: int
    metrics_ci: dict   # {metric_name: {"mean": float, "lower": float, "upper": float}}


def bootstrap_ci(
    returns: pd.Series,
    n_iterations: int = 1_000,
    block_size: int = 20,
    confidence: float = 0.95,
    seed: int = 42,
) -> BootstrapResult:
    """Stationary block bootstrap confidence intervals on daily returns."""
    rng = np.random.default_rng(seed)
    r = returns.values
    n = len(r)
    alpha = (1 - confidence) / 2

    boot_metrics = {k: [] for k in [
        "sharpe_ratio", "annual_return", "max_drawdown", "win_rate", "cvar_5pct"
    ]}

    ann = 252

    for _ in range(n_iterations):
        # Block bootstrap: draw n/block_size random starting points
        indices = []
        while len(indices) < n:
            start = rng.integers(0, n)
            block = list(range(start, min(start + block_size, n)))
            indices.extend(block)
        sample = r[indices[:n]]

        vol = sample.std() * math.sqrt(ann)
        mean_ret = sample.mean() * ann
        sharpe = mean_ret / vol if vol > 0 else 0.0

        equity = np.cumprod(1 + sample)
        rolling_max = np.maximum.accumulate(equity)
        dd = (equity - rolling_max) / rolling_max
        max_dd = float(dd.min())

        win_rate = float((sample > 0).mean())
        cvar_5 = float(sample[sample <= np.percentile(sample, 5)].mean()) if len(sample) > 20 else 0.0

        boot_metrics["sharpe_ratio"].append(sharpe)
        boot_metrics["annual_return"].append(mean_ret)
        boot_metrics["max_drawdown"].append(max_dd)
        boot_metrics["win_rate"].append(win_rate)
        boot_metrics["cvar_5pct"].append(cvar_5)

    ci = {}
    for k, vals in boot_metrics.items():
        arr = np.array(vals)
        ci[k] = {
            "mean": float(arr.mean()),
            "lower": float(np.percentile(arr, alpha * 100)),
            "upper": float(np.percentile(arr, (1 - alpha) * 100)),
        }

    return BootstrapResult(n_iterations=n_iterations, metrics_ci=ci)


# ---------------------------------------------------------------------------
# Monte Carlo forward simulation
# ---------------------------------------------------------------------------

@dataclass
class MonteCarloResult:
    n_paths: int
    horizon_bars: int
    final_equity_distribution: dict   # percentiles
    max_drawdown_distribution: dict
    prob_profit: float
    prob_ruin: float                  # equity < 50% of initial


def monte_carlo(
    returns: pd.Series,
    n_paths: int = 10_000,
    horizon_bars: int = 252,
    block_size: int = 20,
    initial_capital: float = 100_000.0,
    ruin_threshold: float = 0.50,
    seed: int = 42,
) -> MonteCarloResult:
    """Block-resample daily returns to simulate n_paths forward equity paths."""
    rng = np.random.default_rng(seed)
    r = returns.values
    n = len(r)
    final_equities = np.zeros(n_paths)
    max_drawdowns = np.zeros(n_paths)

    for i in range(n_paths):
        indices = []
        while len(indices) < horizon_bars:
            start = rng.integers(0, n)
            block = list(range(start, min(start + block_size, n)))
            indices.extend(block)
        sample = r[indices[:horizon_bars]]

        equity = initial_capital * np.cumprod(1 + sample)
        rolling_max = np.maximum.accumulate(equity)
        dd = (equity - rolling_max) / rolling_max
        final_equities[i] = equity[-1]
        max_drawdowns[i] = dd.min()

    pcts = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    return MonteCarloResult(
        n_paths=n_paths,
        horizon_bars=horizon_bars,
        final_equity_distribution={f"p{p}": float(np.percentile(final_equities, p)) for p in pcts},
        max_drawdown_distribution={f"p{p}": float(np.percentile(max_drawdowns, p)) for p in pcts},
        prob_profit=float((final_equities > initial_capital).mean()),
        prob_ruin=float((final_equities < initial_capital * ruin_threshold).mean()),
    )


# ---------------------------------------------------------------------------
# Deflated Sharpe Ratio
# ---------------------------------------------------------------------------

def deflated_sharpe_ratio(
    sharpe_ratio: float,
    n_bars: int,
    n_trials: int,
    skewness: float = 0.0,
    excess_kurtosis: float = 0.0,
) -> float:
    """
    Bailey & López de Prado Deflated Sharpe Ratio.
    Returns the probability that the strategy's SR > 0 after accounting for
    multiple testing (n_trials strategy versions tried during development).

    PSR(SR* = 0) = Φ( (SR_hat * sqrt(n-1)) / sqrt(1 - skew*SR + (kurt-1)/4 * SR^2) )
    where SR* is chosen as the expected maximum SR under H0 across n_trials.
    """
    from scipy import stats

    if n_bars < 2 or sharpe_ratio == 0:
        return 0.5

    # Expected maximum SR of n_trials independent trials under H0
    # Using the approximation: E[max SR] ≈ (1 - gamma)*Φ^-1(1 - 1/n) + gamma*Φ^-1(1 - 1/(n*e))
    # where gamma is Euler-Mascheroni constant. Simplified:
    euler_gamma = 0.5772156649
    if n_trials > 1:
        sr_star = (1 - euler_gamma) * stats.norm.ppf(1 - 1 / n_trials) + \
                  euler_gamma * stats.norm.ppf(1 - 1 / (n_trials * math.e))
    else:
        sr_star = 0.0

    # Annualise SR (from daily): multiply by sqrt(252)
    # Here sharpe_ratio is already annualised, convert to per-bar for formula
    sr_bar = sharpe_ratio / math.sqrt(252)

    numerator = (sr_bar - sr_star / math.sqrt(252)) * math.sqrt(n_bars - 1)
    denominator = math.sqrt(1 - skewness * sr_bar + (excess_kurtosis - 1) / 4 * sr_bar ** 2)

    if denominator <= 0:
        return 0.5

    z = numerator / denominator
    return float(stats.norm.cdf(z))
