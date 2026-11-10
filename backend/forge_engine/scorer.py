"""
Composite score (0–100) for a validated strategy.

Scoring weights:
  - Statistical significance (permutation p-value + Deflated Sharpe)  30 pts
  - OOS performance net of costs                                       25 pts
  - OOS vs in-sample consistency                                       15 pts
  - Robustness (sensitivity + walk-forward stability)                  15 pts
  - Risk (Monte Carlo drawdown + CVaR)                                 15 pts

Skipped stages cap the score:
  - Stage 3 (split) skipped:    cap at 40
  - Stage 4 (dev) skipped:      cap at 60
  - Stage 5 (validation) skipped: cap at 20 (no OOS, no statistical tests)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .validation import PermutationResult, MonteCarloResult, BootstrapResult
from .walk_forward import WalkForwardResult
from .sensitivity import SensitivityResult


@dataclass
class ScoreBreakdown:
    significance: float          # 0–30
    oos_performance: float       # 0–25
    oos_vs_insample: float       # 0–15
    robustness: float            # 0–15
    risk: float                  # 0–15
    raw_total: float             # 0–100 before stage caps
    total: float                 # 0–100 after stage caps
    skipped_stages: list[int]
    cap_applied: int | None      # the score was capped to this value
    notes: list[str]


def compute_score(
    oos_metrics: dict,
    insample_metrics: dict,
    permutation: PermutationResult,
    monte_carlo: MonteCarloResult,
    bootstrap: BootstrapResult,
    walk_forward: WalkForwardResult,
    sensitivity: SensitivityResult,
    dsr_probability: float,
    skipped_stages: list[int] | None = None,
) -> ScoreBreakdown:
    if skipped_stages is None:
        skipped_stages = []

    notes = []

    # --- 1. Statistical significance (30 pts) ---
    # Permutation: p < 0.01 → 20 pts; p < 0.05 → 15; p < 0.10 → 8; else 0
    p = permutation.p_value
    if p < 0.01:
        perm_score = 20.0
    elif p < 0.05:
        perm_score = 15.0
    elif p < 0.10:
        perm_score = 8.0
    else:
        perm_score = 0.0
        notes.append(f"Permutation p-value {p:.2f}: strategy performance not distinguishable from random.")

    # DSR: scales 0–10 based on probability
    dsr_score = dsr_probability * 10.0

    significance = min(30.0, perm_score + dsr_score)

    # --- 2. OOS performance (25 pts) ---
    oos_sharpe = oos_metrics.get("sharpe_ratio", 0.0)
    if oos_sharpe >= 1.5:
        perf_score = 25.0
    elif oos_sharpe >= 1.0:
        perf_score = 20.0
    elif oos_sharpe >= 0.5:
        perf_score = 12.0
    elif oos_sharpe > 0:
        perf_score = 5.0
    else:
        perf_score = 0.0
        notes.append("OOS Sharpe ratio is negative: strategy lost money on unseen data.")

    oos_performance = perf_score

    # --- 3. OOS vs in-sample consistency (15 pts) ---
    is_sharpe = insample_metrics.get("sharpe_ratio", 0.0)
    if is_sharpe > 0 and oos_sharpe > 0:
        ratio = oos_sharpe / is_sharpe
        if ratio >= 0.80:
            consist_score = 15.0
        elif ratio >= 0.60:
            consist_score = 10.0
        elif ratio >= 0.40:
            consist_score = 5.0
        else:
            consist_score = 0.0
            notes.append(f"OOS Sharpe is only {ratio:.0%} of in-sample Sharpe — significant degradation.")
    elif oos_sharpe > 0:
        consist_score = 10.0
    else:
        consist_score = 0.0

    oos_vs_insample = consist_score

    # --- 4. Robustness (15 pts) ---
    # Sensitivity: not fragile → 8 pts
    sens_score = 0.0 if sensitivity.overall_fragile else 8.0
    if sensitivity.overall_fragile:
        notes.append(f"Fragile parameters: {'; '.join(sensitivity.fragility_reasons[:3])}")

    # Walk-forward consistency: fraction of folds with positive Sharpe
    wf_score = walk_forward.consistency_score * 7.0

    robustness = sens_score + wf_score

    # --- 5. Risk (15 pts) ---
    # Monte Carlo: prob_profit and expected max drawdown
    prob_profit = monte_carlo.prob_profit
    p50_dd = monte_carlo.max_drawdown_distribution.get("p50", -0.30)
    p95_dd = monte_carlo.max_drawdown_distribution.get("p95", -0.60)

    mc_profit_score = prob_profit * 7.0
    # Drawdown: p95 < 20% → 5 pts; < 30% → 3; < 50% → 1; else 0
    if p95_dd > -0.20:
        dd_score = 5.0
    elif p95_dd > -0.30:
        dd_score = 3.0
    elif p95_dd > -0.50:
        dd_score = 1.0
    else:
        dd_score = 0.0
        notes.append(f"95th percentile forward drawdown is {p95_dd:.0%}.")

    # CVaR check
    cvar_5 = oos_metrics.get("cvar_5pct", 0.0)
    cvar_score = 3.0 if cvar_5 > -0.03 else (1.0 if cvar_5 > -0.05 else 0.0)

    risk = mc_profit_score + dd_score + cvar_score

    # --- Total ---
    raw_total = significance + oos_performance + oos_vs_insample + robustness + risk
    raw_total = min(100.0, raw_total)

    # Stage caps
    cap = None
    if 3 in skipped_stages:
        cap = 40
        notes.append("Stage 3 (data split) was skipped: score capped at 40. OOS results cannot be trusted without a held-out test set.")
    elif 4 in skipped_stages:
        cap = 60
        notes.append("Stage 4 (in-sample development) was skipped: score capped at 60. Fragility and walk-forward checks were not performed.")
    elif 5 in skipped_stages:
        cap = 20
        notes.append("Stage 5 (OOS validation) was skipped: score capped at 20. No out-of-sample evidence of edge.")

    total = min(raw_total, cap) if cap is not None else raw_total

    return ScoreBreakdown(
        significance=round(significance, 1),
        oos_performance=round(oos_performance, 1),
        oos_vs_insample=round(oos_vs_insample, 1),
        robustness=round(robustness, 1),
        risk=round(risk, 1),
        raw_total=round(raw_total, 1),
        total=round(total, 1),
        skipped_stages=skipped_stages,
        cap_applied=cap,
        notes=notes,
    )
