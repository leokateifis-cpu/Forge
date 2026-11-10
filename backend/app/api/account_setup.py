"""
Account Setup tab endpoints.

- GET  /prop-firms           — list known prop firms
- POST /prop-firms/rank      — rank accounts by EV using a strategy's OOS metrics
- POST /live/kelly-table     — compute Kelly-based risk table
- PUT  /type                 — save account type to user profile
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import numpy as np

from app.db.base import get_db
from app.models.user import User
from app.models.report import Report
from app.core.security import get_current_user
from forge_engine.risk import (
    PROP_FIRM_DB, rank_prop_accounts, compute_live_account_risk_table
)

router = APIRouter()


class PropFirmRankRequest(BaseModel):
    project_id: UUID
    user_accounts: Optional[list[dict]] = None   # [{firm, account_size}] or None for all


class LiveRiskRequest(BaseModel):
    project_id: UUID
    account_size: float
    max_acceptable_dd_pct: float = 0.20


class AccountTypeRequest(BaseModel):
    account_type: str   # "prop_firm" | "live"


@router.get("/prop-firms")
def list_prop_firms():
    return [
        {
            "firm": f["firm"],
            "account_sizes": f["account_sizes"],
            "max_daily_loss_pct": f["max_daily_loss_pct"],
            "trailing_drawdown_pct": f["trailing_drawdown_pct"],
            "profit_target_pct": f["profit_target_pct"],
            "evaluation_fee": f["evaluation_fee"],
            "payout_pct": f["payout_pct"],
        }
        for f in PROP_FIRM_DB
    ]


@router.post("/prop-firms/rank")
def rank_prop_firm_accounts(
    req: PropFirmRankRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(Report).filter(Report.project_id == req.project_id).first()
    if not report or not report.findings:
        raise HTTPException(400, "Strategy must be validated (Stage 5) before prop firm analysis")

    findings = report.findings
    oos_metrics = findings.get("oos_metrics", {})
    mc_data = findings.get("monte_carlo", {})

    oos_sharpe = oos_metrics.get("sharpe_ratio", 0.0)
    oos_max_dd = oos_metrics.get("max_drawdown", -0.20)

    # Reconstruct daily returns from equity curve for simulation
    equity_list = findings.get("equity_curve", [])
    if len(equity_list) > 1:
        equity = np.array(equity_list)
        daily_returns = np.diff(equity) / equity[:-1]
    else:
        # Fall back to synthetic returns matching OOS metrics
        ann_ret = oos_metrics.get("annual_return", 0.05)
        vol = oos_metrics.get("annual_volatility", 0.15)
        daily_returns = np.random.normal(ann_ret / 252, vol / np.sqrt(252), 252)

    results = rank_prop_accounts(
        mc_daily_returns=daily_returns,
        oos_sharpe=oos_sharpe,
        oos_max_dd=oos_max_dd,
        user_accounts=req.user_accounts,
        top_n=20,
    )

    return [
        {
            "firm": r.firm,
            "account_size": r.account_size,
            "optimal_risk_pct": r.optimal_risk_pct,
            "optimal_risk_dollars": r.optimal_risk_dollars,
            "ev": r.ev,
            "prob_pass": r.prob_pass,
            "expected_days_to_target": r.expected_days_to_target,
            "net_payout": r.net_payout,
            "evaluation_fee": r.evaluation_fee,
        }
        for r in results
    ]


@router.post("/live/kelly-table")
def live_kelly_table(
    req: LiveRiskRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(Report).filter(Report.project_id == req.project_id).first()
    if not report or not report.findings:
        raise HTTPException(400, "Strategy must be validated before risk analysis")

    oos_metrics = report.findings.get("oos_metrics", {})
    oos_sharpe = oos_metrics.get("sharpe_ratio", 0.0)
    oos_max_dd = oos_metrics.get("max_drawdown", -0.20)

    table = compute_live_account_risk_table(
        oos_sharpe=oos_sharpe,
        oos_max_dd=oos_max_dd,
        account_size=req.account_size,
        max_acceptable_dd_pct=req.max_acceptable_dd_pct,
    )

    return [
        {
            "risk_pct": r.risk_pct,
            "risk_dollars": r.risk_dollars,
            "expected_annual_return_pct": r.expected_annual_return_pct,
            "expected_max_drawdown_pct": r.expected_max_drawdown_pct,
            "prob_ruin": r.prob_ruin,
            "kelly_fraction": r.kelly_fraction,
        }
        for r in table
    ]


@router.put("/type")
def set_account_type(
    req: AccountTypeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if req.account_type not in ("prop_firm", "live"):
        raise HTTPException(400, "account_type must be 'prop_firm' or 'live'")
    user.account_type = req.account_type
    db.commit()
    return {"status": "updated", "account_type": req.account_type}
