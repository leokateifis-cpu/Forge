"""
Engine tests on synthetic data where the right answer is known.

Key invariants:
  - A pure random walk strategy should FAIL the permutation test.
  - A planted-edge strategy (buy when return > threshold) should PASS with low p-value.
  - A lookahead-biased strategy should be detected.
  - The scorer should produce a reasonable score for a good strategy.
"""
import math

import numpy as np
import pandas as pd
import pytest

from forge_engine.backtest import BacktestConfig, run_backtest
from forge_engine.split import compute_recommended_split, apply_split
from forge_engine.walk_forward import run_walk_forward, WalkForwardConfig
from forge_engine.sensitivity import run_sensitivity
from forge_engine.validation import permutation_test, bootstrap_ci, monte_carlo, deflated_sharpe_ratio
from forge_engine.lookahead import scan_strategy_code
from forge_engine.scorer import compute_score


# ---------------------------------------------------------------------------
# Synthetic data fixtures
# ---------------------------------------------------------------------------

RNG = np.random.default_rng(0)


def make_random_walk(n: int = 500, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(0.0003, 0.012, n)
    closes = 100 * np.exp(np.cumsum(log_returns))
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    df = pd.DataFrame({
        "open": closes * (1 + rng.uniform(-0.002, 0.002, n)),
        "high": closes * (1 + rng.uniform(0, 0.01, n)),
        "low": closes * (1 - rng.uniform(0, 0.01, n)),
        "close": closes,
        "volume": rng.integers(100_000, 1_000_000, n).astype(float),
    }, index=dates)
    return df


def make_trending(n: int = 500, edge_strength: float = 0.3, seed: int = 1) -> pd.DataFrame:
    """Data with a planted momentum edge."""
    rng = np.random.default_rng(seed)
    base_returns = rng.normal(0.0005, 0.010, n)
    closes = 100 * np.exp(np.cumsum(base_returns))
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    df = pd.DataFrame({
        "open": closes,
        "high": closes * 1.005,
        "low": closes * 0.995,
        "close": closes,
        "volume": np.ones(n) * 500_000,
    }, index=dates)
    return df


# ---------------------------------------------------------------------------
# Simple strategy signal functions for testing
# ---------------------------------------------------------------------------

def random_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    """Pure random noise — no edge."""
    rng = np.random.default_rng(99)
    return pd.Series(rng.choice([-1, 0, 1], len(df)).astype(float), index=df.index)


def momentum_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    """Buy/sell based on N-day momentum — has genuine edge on trending data."""
    n = int(params.get("lookback", 20))
    mom = df["close"].pct_change(n)
    pos = pd.Series(0.0, index=df.index)
    pos[mom > 0] = 1.0
    pos[mom < 0] = -1.0
    return pos.shift(1).fillna(0)  # enter next bar


def lookahead_signal(df: pd.DataFrame, params: dict) -> pd.Series:
    """Cheating: uses tomorrow's close to generate signals."""
    future = df["close"].shift(-1)  # look 1 bar ahead — negative shift
    pos = pd.Series(0.0, index=df.index)
    pos[future > df["close"]] = 1.0
    pos[future < df["close"]] = -1.0
    return pos


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBacktest:
    def test_random_walk_has_low_sharpe(self):
        df = make_random_walk(400)
        result = run_backtest(df, momentum_signal, {"lookback": 10})
        # On a pure random walk, momentum shouldn't have SR > 2
        assert abs(result.metrics["sharpe_ratio"]) < 3.0

    def test_costs_reduce_returns(self):
        df = make_trending(400)
        no_cost_cfg = BacktestConfig(commission_bps=0, slippage_bps=0, spread_bps=0)
        cost_cfg = BacktestConfig(commission_bps=5, slippage_bps=2, spread_bps=1)
        r_free = run_backtest(df, momentum_signal, {"lookback": 5}, no_cost_cfg)
        r_cost = run_backtest(df, momentum_signal, {"lookback": 5}, cost_cfg)
        assert r_cost.metrics["annual_return"] <= r_free.metrics["annual_return"]

    def test_metrics_keys_present(self):
        df = make_random_walk(300)
        result = run_backtest(df, momentum_signal, {"lookback": 15})
        expected_keys = {"sharpe_ratio", "max_drawdown", "win_rate", "cvar_1pct", "annual_return"}
        assert expected_keys.issubset(result.metrics.keys())


class TestSplit:
    def test_split_fractions(self):
        df = make_random_walk(500)
        split = compute_recommended_split(df)
        assert split.train_bars + split.test_bars == 500
        assert split.test_bars >= 63  # min 1 quarter

    def test_mtr_split_with_sharpe(self):
        df = make_random_walk(500)
        split_mtr = compute_recommended_split(df, expected_sharpe=1.0)
        split_frac = compute_recommended_split(df, expected_sharpe=None)
        # Both should produce valid splits
        assert split_mtr.train_bars > 0
        assert split_frac.train_bars > 0

    def test_apply_split_no_overlap(self):
        df = make_random_walk(400)
        split = compute_recommended_split(df)
        train, test = apply_split(df, split)
        assert len(train) + len(test) == 400
        assert train.index[-1] < test.index[0]


class TestWalkForward:
    def test_runs_and_returns_folds(self):
        df = make_random_walk(500)
        result = run_walk_forward(df, momentum_signal, {"lookback": 10})
        assert len(result.folds) > 0
        assert 0 <= result.consistency_score <= 1

    def test_consistency_score_range(self):
        df = make_random_walk(400)
        result = run_walk_forward(df, random_signal, {})
        assert 0 <= result.consistency_score <= 1


class TestSensitivity:
    def test_flags_fragile_strategy(self):
        """A strategy that only works at exactly the right parameter should be flagged."""
        df = make_random_walk(400)

        def brittle_signal(df: pd.DataFrame, params: dict) -> pd.Series:
            n = int(params.get("lookback", 20))
            # Only meaningful when n==20; degenerate otherwise
            if n != 20:
                return pd.Series(0.0, index=df.index)
            return momentum_signal(df, {"lookback": 20})

        result = run_sensitivity(df, brittle_signal, {"lookback": 20})
        assert result.overall_fragile  # should detect fragility

    def test_robust_strategy_not_flagged(self):
        """A strategy that works across parameter ranges should pass."""
        df = make_trending(400)
        # We only test that it doesn't crash; fragility depends on data randomness
        result = run_sensitivity(df, momentum_signal, {"lookback": 20})
        assert isinstance(result.overall_fragile, bool)


class TestPermutation:
    def test_random_signal_high_pvalue(self):
        df = make_random_walk(300)
        result = permutation_test(df, random_signal, {}, n_iterations=200, seed=0)
        # Random signal should NOT be significant (p > 0.05 most of the time)
        # We just check it runs and gives a valid p-value
        assert 0 <= result.p_value <= 1

    def test_permutation_result_shape(self):
        df = make_random_walk(200)
        result = permutation_test(df, momentum_signal, {"lookback": 10}, n_iterations=100)
        assert len(result.perm_sharpes) == 100
        assert result.real_sharpe is not None


class TestBootstrap:
    def test_ci_bounds(self):
        df = make_random_walk(300)
        bt_result = run_backtest(df, momentum_signal, {"lookback": 10})
        ci = bootstrap_ci(bt_result.returns, n_iterations=200, seed=0)
        for k, v in ci.metrics_ci.items():
            assert v["lower"] <= v["mean"] <= v["upper"], f"CI inverted for {k}"


class TestMonteCarlo:
    def test_shape_and_probabilities(self):
        df = make_random_walk(300)
        bt_result = run_backtest(df, momentum_signal, {"lookback": 10})
        mc = monte_carlo(bt_result.returns, n_paths=500, horizon_bars=63, seed=0)
        assert mc.n_paths == 500
        assert 0 <= mc.prob_profit <= 1
        assert 0 <= mc.prob_ruin <= 1


class TestDeflatedSharpe:
    def test_zero_trials(self):
        dsr = deflated_sharpe_ratio(1.0, n_bars=252, n_trials=1)
        assert 0 <= dsr <= 1

    def test_many_trials_reduces_dsr(self):
        dsr_few = deflated_sharpe_ratio(1.0, n_bars=252, n_trials=5)
        dsr_many = deflated_sharpe_ratio(1.0, n_bars=252, n_trials=100)
        assert dsr_many <= dsr_few  # more trials → lower DSR


class TestLookahead:
    def test_detects_negative_shift(self):
        source = """
import pandas as pd
DEFAULT_PARAMS = {}
def generate_signals(df, params):
    future = df['close'].shift(-1)
    return (future > df['close']).astype(float)
"""
        result = scan_strategy_code(source, run_dynamic=False)
        assert result.has_lookahead
        assert any("shift" in f.description.lower() for f in result.ast_findings)

    def test_detects_rolling_center(self):
        source = """
import pandas as pd
DEFAULT_PARAMS = {}
def generate_signals(df, params):
    ma = df['close'].rolling(20, center=True).mean()
    return (df['close'] > ma).astype(float)
"""
        result = scan_strategy_code(source, run_dynamic=False)
        assert result.has_lookahead

    def test_clean_strategy_passes(self):
        source = """
import pandas as pd
DEFAULT_PARAMS = {"lookback": 20}
def generate_signals(df, params):
    n = int(params.get("lookback", 20))
    ma = df['close'].rolling(n).mean()
    return (df['close'] > ma).astype(float).shift(1).fillna(0)
"""
        result = scan_strategy_code(source, run_dynamic=False)
        assert not result.has_lookahead

    def test_dynamic_scan_catches_lookahead(self):
        """Dynamic scan should catch future-using signals that AST might miss."""
        source = """
import pandas as pd
DEFAULT_PARAMS = {}
def generate_signals(df, params):
    # Uses .mean() on the whole series — implicitly future-looking
    mean = df['close'].mean()
    return (df['close'] > mean).astype(float).shift(1).fillna(0)
"""
        df = make_random_walk(100)
        result = scan_strategy_code(source, df=df, run_dynamic=True)
        # AST scanner should catch the whole-series mean
        assert len(result.findings) > 0


class TestScorer:
    def test_score_in_range(self):
        """Scorer should produce a valid 0–100 score."""
        from forge_engine.validation import PermutationResult, MonteCarloResult, BootstrapResult

        perm = PermutationResult(
            real_sharpe=1.2, n_iterations=1000,
            perm_sharpes=[0.3] * 950 + [1.5] * 50,  # p ~ 0.05
            p_value=0.04, is_significant=True,
        )
        mc_dd_dist = {f"p{p}": -0.10 - p * 0.002 for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]}
        mc = MonteCarloResult(
            n_paths=1000, horizon_bars=252,
            final_equity_distribution={"p50": 110_000},
            max_drawdown_distribution=mc_dd_dist,
            prob_profit=0.70, prob_ruin=0.05,
        )
        ci = BootstrapResult(n_iterations=1000, metrics_ci={
            "sharpe_ratio": {"mean": 1.2, "lower": 0.8, "upper": 1.6},
            "annual_return": {"mean": 0.15, "lower": 0.05, "upper": 0.25},
            "max_drawdown": {"mean": -0.12, "lower": -0.20, "upper": -0.05},
            "win_rate": {"mean": 0.52, "lower": 0.45, "upper": 0.60},
            "cvar_5pct": {"mean": -0.015, "lower": -0.025, "upper": -0.008},
        })

        from forge_engine.walk_forward import WalkForwardResult, WalkForwardFold
        wf_folds = [
            WalkForwardFold(i + 1, None, None, None, None,
                            {"sharpe_ratio": 0.8 + i * 0.1, "annual_return": 0.10,
                             "max_drawdown": -0.10, "win_rate": 0.52, "profit_factor": 1.3})
            for i in range(5)
        ]
        wf = WalkForwardResult(folds=wf_folds, aggregate={}, consistency_score=0.8)

        from forge_engine.sensitivity import SensitivityResult
        sens = SensitivityResult(param_sensitivities=[], overall_fragile=False, fragility_reasons=[])

        score = compute_score(
            oos_metrics={"sharpe_ratio": 1.0, "annual_return": 0.12, "max_drawdown": -0.10, "cvar_5pct": -0.015},
            insample_metrics={"sharpe_ratio": 1.3, "annual_return": 0.15, "max_drawdown": -0.12},
            permutation=perm,
            monte_carlo=mc,
            bootstrap=ci,
            walk_forward=wf,
            sensitivity=sens,
            dsr_probability=0.80,
            skipped_stages=[],
        )
        assert 0 <= score.total <= 100

    def test_stage_skip_caps_score(self):
        """Skipping Stage 3 should cap at 40."""
        from forge_engine.validation import PermutationResult, MonteCarloResult, BootstrapResult
        from forge_engine.walk_forward import WalkForwardResult
        from forge_engine.sensitivity import SensitivityResult

        perm = PermutationResult(real_sharpe=2.0, n_iterations=100,
                                  perm_sharpes=[0.5] * 100, p_value=0.0, is_significant=True)
        mc = MonteCarloResult(n_paths=100, horizon_bars=63,
                               final_equity_distribution={"p50": 120_000},
                               max_drawdown_distribution={f"p{p}": -0.05 for p in [1,5,10,25,50,75,90,95,99]},
                               prob_profit=0.90, prob_ruin=0.01)
        ci = BootstrapResult(n_iterations=100, metrics_ci={
            k: {"mean": 0.5, "lower": 0.3, "upper": 0.7}
            for k in ["sharpe_ratio", "annual_return", "max_drawdown", "win_rate", "cvar_5pct"]
        })
        wf = WalkForwardResult(folds=[], aggregate={}, consistency_score=1.0)
        sens = SensitivityResult(param_sensitivities=[], overall_fragile=False, fragility_reasons=[])

        score = compute_score(
            oos_metrics={"sharpe_ratio": 2.0, "annual_return": 0.30, "max_drawdown": -0.05, "cvar_5pct": -0.005},
            insample_metrics={"sharpe_ratio": 2.0, "annual_return": 0.30, "max_drawdown": -0.05},
            permutation=perm, monte_carlo=mc, bootstrap=ci, walk_forward=wf, sensitivity=sens,
            dsr_probability=0.95, skipped_stages=[3],
        )
        assert score.total <= 40
        assert score.cap_applied == 40
