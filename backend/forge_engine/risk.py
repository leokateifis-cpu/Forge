"""
Account type risk optimisation (Account Setup tab).

Two modes:
  1. Prop firm: given a set of prop firm accounts, find the optimal risk-per-trade
     that maximises EV = P(pass) × net_payout − fee, subject to the firm's drawdown rules.
  2. Live account: modified Kelly Criterion adjusted for actual OOS Sharpe and max DD.

The EV calculation uses the strategy's Monte Carlo distribution (from Stage 5).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# ---------------------------------------------------------------------------
# Prop firm database (top firms — rules as of 2024; update regularly)
# ---------------------------------------------------------------------------

PROP_FIRM_DB: list[dict] = [
    {
        "firm": "Topstep",
        "account_name": "Standard",
        "website": "https://www.topstep.com",
        "account_sizes": [50_000, 100_000, 150_000],
        "max_daily_loss_pct": 0.02,
        "trailing_drawdown_pct": 0.04,
        "profit_target_pct": 0.06,
        "evaluation_fee": 165,
        "payout_pct": 0.80,
    },
    {
        "firm": "FTMO",
        "account_name": "Challenge",
        "website": "https://ftmo.com",
        "account_sizes": [10_000, 25_000, 50_000, 100_000, 200_000],
        "max_daily_loss_pct": 0.05,
        "trailing_drawdown_pct": 0.10,
        "profit_target_pct": 0.10,
        "evaluation_fee": 155,
        "payout_pct": 0.80,
    },
    {
        "firm": "FTMO",
        "account_name": "Swing",
        "website": "https://ftmo.com",
        "account_sizes": [10_000, 25_000, 50_000, 100_000, 200_000],
        "max_daily_loss_pct": 0.08,
        "trailing_drawdown_pct": 0.10,
        "profit_target_pct": 0.10,
        "evaluation_fee": 250,
        "payout_pct": 0.80,
    },
    {
        "firm": "Apex Trader Funding",
        "account_name": "Full",
        "website": "https://apextraderfunding.com",
        "account_sizes": [25_000, 50_000, 100_000, 150_000, 300_000],
        "max_daily_loss_pct": 0.025,
        "trailing_drawdown_pct": 0.06,
        "profit_target_pct": 0.06,
        "evaluation_fee": 137,
        "payout_pct": 0.90,
    },
    {
        "firm": "My Funded Futures",
        "account_name": "Standard",
        "website": "https://myfundedfutures.com",
        "account_sizes": [25_000, 50_000, 100_000, 150_000],
        "max_daily_loss_pct": 0.025,
        "trailing_drawdown_pct": 0.05,
        "profit_target_pct": 0.06,
        "evaluation_fee": 125,
        "payout_pct": 0.80,
    },
    {
        "firm": "Earn2Trade",
        "account_name": "Gauntlet Mini",
        "website": "https://earn2trade.com",
        "account_sizes": [25_000, 50_000, 100_000, 200_000],
        "max_daily_loss_pct": 0.04,
        "trailing_drawdown_pct": 0.08,
        "profit_target_pct": 0.10,
        "evaluation_fee": 150,
        "payout_pct": 0.80,
    },
    {
        "firm": "Lucid Trader",
        "account_name": "Pro",
        "website": "https://lucidtraderfunding.com",
        "account_sizes": [25_000, 50_000, 100_000],
        "max_daily_loss_pct": 0.03,
        "trailing_drawdown_pct": 0.06,
        "profit_target_pct": 0.08,
        "evaluation_fee": 97,
        "payout_pct": 0.85,
    },
    {
        "firm": "Lucid Trader",
        "account_name": "Flex",
        "website": "https://lucidtraderfunding.com",
        "account_sizes": [25_000, 50_000, 100_000],
        "max_daily_loss_pct": 0.04,
        "trailing_drawdown_pct": 0.08,
        "profit_target_pct": 0.08,
        "evaluation_fee": 147,
        "payout_pct": 0.85,
    },
    {
        "firm": "Funding Pips",
        "account_name": "Starter",
        "website": "https://fundingpips.com",
        "account_sizes": [5_000, 10_000, 25_000],
        "max_daily_loss_pct": 0.04,
        "trailing_drawdown_pct": 0.08,
        "profit_target_pct": 0.08,
        "evaluation_fee": 32,
        "payout_pct": 0.80,
    },
    {
        "firm": "Funding Pips",
        "account_name": "Master",
        "website": "https://fundingpips.com",
        "account_sizes": [50_000, 100_000],
        "max_daily_loss_pct": 0.04,
        "trailing_drawdown_pct": 0.08,
        "profit_target_pct": 0.08,
        "evaluation_fee": 95,
        "payout_pct": 0.80,
    },
    {
        "firm": "Funding Pips",
        "account_name": "Royal",
        "website": "https://fundingpips.com",
        "account_sizes": [200_000],
        "max_daily_loss_pct": 0.04,
        "trailing_drawdown_pct": 0.08,
        "profit_target_pct": 0.08,
        "evaluation_fee": 350,
        "payout_pct": 0.80,
    },
    {
        "firm": "FundedNext",
        "account_name": "Evaluation",
        "website": "https://fundednext.com",
        "account_sizes": [15_000, 25_000, 50_000, 100_000, 200_000],
        "max_daily_loss_pct": 0.05,
        "trailing_drawdown_pct": 0.10,
        "profit_target_pct": 0.10,
        "evaluation_fee": 84,
        "payout_pct": 0.90,
    },
    {
        "firm": "FundedNext",
        "account_name": "Express",
        "website": "https://fundednext.com",
        "account_sizes": [15_000, 25_000, 50_000, 100_000],
        "max_daily_loss_pct": 0.05,
        "trailing_drawdown_pct": 0.10,
        "profit_target_pct": 0.25,
        "evaluation_fee": 199,
        "payout_pct": 0.95,
    },
    {
        "firm": "FundedNext",
        "account_name": "Stellar",
        "website": "https://fundednext.com",
        "account_sizes": [15_000, 25_000, 50_000, 100_000, 200_000],
        "max_daily_loss_pct": 0.05,
        "trailing_drawdown_pct": 0.10,
        "profit_target_pct": 0.10,
        "evaluation_fee": 99,
        "payout_pct": 0.90,
    },
]


@dataclass
class PropFirmResult:
    firm: str
    account_size: float
    optimal_risk_pct: float          # risk per trade as % of account
    optimal_risk_dollars: float
    ev: float                        # expected value ($)
    prob_pass: float
    expected_days_to_target: float
    net_payout: float
    evaluation_fee: float
    notes: str


@dataclass
class LiveAccountResult:
    risk_pct: float                  # risk per trade as % of account
    risk_dollars: float
    expected_annual_return_pct: float
    expected_max_drawdown_pct: float
    prob_ruin: float
    kelly_fraction: float


def compute_prop_firm_ev(
    mc_daily_returns: np.ndarray,       # from Monte Carlo OOS simulation
    oos_sharpe: float,
    oos_max_dd: float,
    account_size: float,
    max_daily_loss_pct: float,
    trailing_drawdown_pct: float,
    profit_target_pct: float,
    evaluation_fee: float,
    payout_pct: float,
    risk_grid: np.ndarray | None = None,
    n_sims: int = 5_000,
    seed: int = 42,
) -> tuple[float, float, float]:
    """
    Returns (optimal_risk_pct, prob_pass, expected_days_to_target).
    Simulates the evaluation under each risk level, picks the one that maximises EV.
    """
    if risk_grid is None:
        risk_grid = np.arange(0.005, 0.051, 0.005)  # 0.5% to 5% step 0.5%

    rng = np.random.default_rng(seed)
    best_ev = -float("inf")
    best_risk = risk_grid[0]
    best_pass_prob = 0.0
    best_days = float("inf")

    for risk_pct in risk_grid:
        pass_count = 0
        total_days = []

        for _ in range(n_sims):
            equity = account_size
            peak = equity
            day = 0
            passed = False
            failed = False

            while day < 252:  # max 1 year evaluation window
                day += 1
                r_idx = rng.integers(0, len(mc_daily_returns))
                r = mc_daily_returns[r_idx] * risk_pct / 0.01  # scale by risk
                # Clamp to reasonable single-trade range
                r = max(-risk_pct * 3, min(r, risk_pct * 3))
                equity *= (1 + r)
                peak = max(peak, equity)

                # Daily loss check
                daily_loss_pct = (equity - account_size) / account_size
                if daily_loss_pct < -max_daily_loss_pct:
                    failed = True
                    break

                # Trailing drawdown check
                trail_dd = (equity - peak) / peak
                if trail_dd < -trailing_drawdown_pct:
                    failed = True
                    break

                # Profit target
                if (equity - account_size) / account_size >= profit_target_pct:
                    passed = True
                    total_days.append(day)
                    break

            if passed:
                pass_count += 1

        prob_pass = pass_count / n_sims
        avg_days = float(np.mean(total_days)) if total_days else 252.0
        net_payout = account_size * profit_target_pct * payout_pct
        ev = prob_pass * net_payout - evaluation_fee

        if ev > best_ev:
            best_ev = ev
            best_risk = risk_pct
            best_pass_prob = prob_pass
            best_days = avg_days

    return best_risk, best_pass_prob, best_days


def rank_prop_accounts(
    mc_daily_returns: np.ndarray,
    oos_sharpe: float,
    oos_max_dd: float,
    user_accounts: list[dict] | None = None,
    top_n: int = 20,
) -> list[PropFirmResult]:
    """
    Rank prop firm accounts by EV. user_accounts is a list of
    {"firm": "Topstep", "account_size": 50000} dicts.
    If None, ranks all accounts in PROP_FIRM_DB.
    """
    candidates = []

    db = PROP_FIRM_DB if user_accounts is None else _filter_db(user_accounts)

    for firm_info in db:
        sizes = firm_info["account_sizes"] if user_accounts is None else \
            [a["account_size"] for a in user_accounts if a["firm"] == firm_info["firm"]]

        for size in sizes:
            risk_pct, prob_pass, avg_days = compute_prop_firm_ev(
                mc_daily_returns=mc_daily_returns,
                oos_sharpe=oos_sharpe,
                oos_max_dd=oos_max_dd,
                account_size=size,
                max_daily_loss_pct=firm_info["max_daily_loss_pct"],
                trailing_drawdown_pct=firm_info["trailing_drawdown_pct"],
                profit_target_pct=firm_info["profit_target_pct"],
                evaluation_fee=firm_info["evaluation_fee"],
                payout_pct=firm_info["payout_pct"],
            )

            net_payout = size * firm_info["profit_target_pct"] * firm_info["payout_pct"]
            ev = prob_pass * net_payout - firm_info["evaluation_fee"]

            candidates.append(PropFirmResult(
                firm=firm_info["firm"],
                account_size=size,
                optimal_risk_pct=round(risk_pct * 100, 2),
                optimal_risk_dollars=round(size * risk_pct, 2),
                ev=round(ev, 2),
                prob_pass=round(prob_pass, 3),
                expected_days_to_target=round(avg_days, 1),
                net_payout=round(net_payout, 2),
                evaluation_fee=firm_info["evaluation_fee"],
                notes="",
            ))

    candidates.sort(key=lambda x: x.ev, reverse=True)
    return candidates[:top_n]


def _filter_db(user_accounts: list[dict]) -> list[dict]:
    names = {a["firm"].lower() for a in user_accounts}
    return [f for f in PROP_FIRM_DB if f["firm"].lower() in names]


# ---------------------------------------------------------------------------
# Live account: modified Kelly
# ---------------------------------------------------------------------------

def compute_live_account_risk_table(
    oos_sharpe: float,
    oos_max_dd: float,
    account_size: float,
    max_acceptable_dd_pct: float,
    n_levels: int = 10,
) -> list[LiveAccountResult]:
    """
    Compute a table of risk levels using modified Kelly Criterion.
    Kelly f* = SR / sqrt(252) adjusted by (1 - |max_dd|) to account for strategy quality.
    """
    # Full Kelly (daily)
    daily_sr = oos_sharpe / math.sqrt(252)
    full_kelly = max(0.0, daily_sr ** 2 / (1 + daily_sr ** 2) if daily_sr > 0 else 0.0)

    # Adjust for drawdown quality
    dd_adjustment = max(0.1, 1 - abs(oos_max_dd) * 2)
    full_kelly *= dd_adjustment

    # Generate a range from 0.1× to 1.0× full Kelly
    fractions = np.linspace(0.1, 1.0, n_levels)

    results = []
    ann = 252

    for frac in fractions:
        risk_pct = full_kelly * frac
        risk_dollars = account_size * risk_pct

        # Expected annual return: risk × daily SR × sqrt(252)
        exp_ann_ret = risk_pct * oos_sharpe

        # Expected max drawdown: scales roughly with sqrt(risk)
        # Simple approximation: scale OOS max DD by risk fraction
        exp_dd = oos_max_dd * frac

        # Probability of ruin: P(equity < 0) — simplified for display
        # Using Gambler's ruin: p_ruin ≈ exp(-2 * edge / variance * ruin_level)
        edge = risk_pct * daily_sr
        variance = risk_pct ** 2
        ruin_level = max_acceptable_dd_pct
        if variance > 0 and edge > 0:
            prob_ruin = min(0.99, math.exp(-2 * edge / variance * ruin_level))
        else:
            prob_ruin = 0.99

        results.append(LiveAccountResult(
            risk_pct=round(risk_pct * 100, 3),
            risk_dollars=round(risk_dollars, 2),
            expected_annual_return_pct=round(exp_ann_ret * 100, 2),
            expected_max_drawdown_pct=round(exp_dd * 100, 2),
            prob_ruin=round(prob_ruin, 4),
            kelly_fraction=round(frac, 2),
        ))

    return results
