"""
Parameter sensitivity analysis (Stage 4 fragility check).

For each parameter, varies it ±5%, ±10%, ±20% while holding others fixed.
A strategy is fragile if the Sharpe ratio drops > 50% at ±10% or flips sign at ±20%.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .backtest import BacktestConfig, SignalFn, run_backtest


SHIFTS = [-0.20, -0.10, -0.05, 0.05, 0.10, 0.20]


@dataclass
class ParamSensitivity:
    param_name: str
    base_value: float
    shifts: list[dict]       # [{shift_pct, param_value, sharpe, annual_return, max_dd}]
    is_fragile: bool


@dataclass
class SensitivityResult:
    param_sensitivities: list[ParamSensitivity]
    overall_fragile: bool
    fragility_reasons: list[str]


def run_sensitivity(
    train_df: pd.DataFrame,
    signal_fn: SignalFn,
    base_params: dict,
    bt_config: BacktestConfig | None = None,
    fragility_sharpe_drop_threshold: float = 0.50,
    fragility_sign_flip_shift: float = 0.20,
) -> SensitivityResult:
    """
    One-at-a-time sensitivity analysis on train_df.
    Returns per-parameter sensitivity and an overall fragility flag.
    """
    if bt_config is None:
        bt_config = BacktestConfig()

    # Base metrics
    base_result = run_backtest(train_df, signal_fn, base_params, bt_config)
    base_sharpe = base_result.metrics.get("sharpe_ratio", 0.0)

    param_results: list[ParamSensitivity] = []
    all_fragility_reasons: list[str] = []

    for param_name, base_val in base_params.items():
        if not isinstance(base_val, (int, float)):
            continue

        shifts_data = []
        is_fragile = False
        reasons: list[str] = []

        for shift_pct in SHIFTS:
            new_val = base_val * (1 + shift_pct)
            shifted_params = {**base_params, param_name: new_val}

            try:
                result = run_backtest(train_df, signal_fn, shifted_params, bt_config)
                sharpe = result.metrics.get("sharpe_ratio", 0.0)
                ann_ret = result.metrics.get("annual_return", 0.0)
                max_dd = result.metrics.get("max_drawdown", 0.0)
            except Exception:
                sharpe = ann_ret = max_dd = float("nan")

            shifts_data.append({
                "shift_pct": shift_pct,
                "param_value": new_val,
                "sharpe": sharpe,
                "annual_return": ann_ret,
                "max_drawdown": max_dd,
            })

            abs_shift = abs(shift_pct)

            # Check fragility at ±10%
            if abs_shift == 0.10 and base_sharpe != 0:
                drop = (base_sharpe - sharpe) / abs(base_sharpe)
                if drop > fragility_sharpe_drop_threshold:
                    is_fragile = True
                    reasons.append(
                        f"{param_name}: Sharpe drops {drop:.0%} at {shift_pct:+.0%} shift"
                    )

            # Check sign flip at ±20%
            if abs_shift == fragility_sign_flip_shift and base_sharpe != 0:
                if np.sign(sharpe) != np.sign(base_sharpe):
                    is_fragile = True
                    reasons.append(
                        f"{param_name}: Sharpe flips sign at {shift_pct:+.0%} shift"
                    )

        param_results.append(ParamSensitivity(
            param_name=param_name,
            base_value=base_val,
            shifts=shifts_data,
            is_fragile=is_fragile,
        ))
        all_fragility_reasons.extend(reasons)

    overall_fragile = any(p.is_fragile for p in param_results)

    return SensitivityResult(
        param_sensitivities=param_results,
        overall_fragile=overall_fragile,
        fragility_reasons=all_fragility_reasons,
    )
