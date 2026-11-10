"""
Celery tasks for the validation pipeline.

Stage 4: run_development_task — walk-forward + sensitivity on training data only.
Stage 5: run_oos_validation_task — full battery on test data (runs once).
"""
from __future__ import annotations

import sys
import traceback
import types
from datetime import datetime

from app.tasks.celery_app import celery_app


def _load_strategy(source_code: str, params: dict):
    """Compile strategy code and return (signal_fn, params)."""
    module = types.ModuleType("_strategy")
    exec(compile(source_code, "<strategy>", "exec"), module.__dict__)  # noqa: S102
    signal_fn = module.generate_signals
    default_params = getattr(module, "DEFAULT_PARAMS", {})
    # Merge stored params over defaults
    merged = {**default_params, **params}
    return signal_fn, merged


@celery_app.task(bind=True, name="forge.development")
def run_development_task(self, project_id: str, job_id: str):
    """Walk-forward + sensitivity on training data. Stage 4."""
    from app.db.base import SessionLocal
    from app.models.job import Job, JobStatus
    from app.models.project import Project, ProjectStage, StageEvent
    from app.models.strategy import StrategyVersion
    from app.models.data_split import DataSplit
    from forge_engine.data import load_instrument
    from forge_engine.split import apply_split, DataSplit as DS
    from forge_engine.walk_forward import run_walk_forward, WalkForwardConfig
    from forge_engine.sensitivity import run_sensitivity
    from forge_engine.backtest import run_backtest, BacktestConfig
    import pandas as pd

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        project = db.query(Project).filter(Project.id == project_id).first()
        split_rec = db.query(DataSplit).filter(DataSplit.project_id == project_id).first()
        strategy = db.query(StrategyVersion).filter(
            StrategyVersion.project_id == project_id,
            StrategyVersion.is_active == True,
        ).first()

        df = load_instrument(project.instrument, timeframe=project.timeframe)
        signal_fn, params = _load_strategy(strategy.source_code, strategy.params or {})

        # Reconstruct split
        ds = DS(
            train_start=split_rec.train_start,
            train_end=split_rec.train_end,
            test_start=split_rec.test_start,
            test_end=split_rec.test_end,
            train_bars=split_rec.train_bars,
            test_bars=split_rec.test_bars,
            recommended_by=split_rec.recommended_by,
        )
        train_df, _test_df = apply_split(df, ds)

        # In-sample full backtest
        bt_config = BacktestConfig()
        is_result = run_backtest(train_df, signal_fn, params, bt_config)

        # Walk-forward
        wf_result = run_walk_forward(train_df, signal_fn, params, WalkForwardConfig(), bt_config)

        # Sensitivity
        sens_result = run_sensitivity(train_df, signal_fn, params, bt_config)

        # Package results
        wf_folds = [
            {
                "fold_num": f.fold_num,
                "train_start": str(f.train_start),
                "train_end": str(f.train_end),
                "test_start": str(f.test_start),
                "test_end": str(f.test_end),
                "metrics": f.metrics,
            }
            for f in wf_result.folds
        ]

        sens_params = []
        for ps in sens_result.param_sensitivities:
            sens_params.append({
                "param_name": ps.param_name,
                "base_value": ps.base_value,
                "shifts": ps.shifts,
                "is_fragile": ps.is_fragile,
            })

        result = {
            "insample_metrics": is_result.metrics,
            "walk_forward": {
                "folds": wf_folds,
                "aggregate": wf_result.aggregate,
                "consistency_score": wf_result.consistency_score,
            },
            "sensitivity": {
                "params": sens_params,
                "overall_fragile": sens_result.overall_fragile,
                "fragility_reasons": sens_result.fragility_reasons,
            },
            "equity_curve": is_result.equity.tolist(),
            "equity_dates": [str(d) for d in is_result.equity.index],
        }

        job.result = result
        job.status = JobStatus.SUCCESS
        job.finished_at = datetime.utcnow()

        # Advance stage if fragility check passed or was already flagged
        if not sens_result.overall_fragile:
            if project.current_stage == ProjectStage.DEVELOPMENT:
                event = StageEvent(
                    project_id=project_id,
                    stage=ProjectStage.DEVELOPMENT,
                    action="completed",
                )
                db.add(event)
                project.current_stage = ProjectStage.VALIDATION

        db.commit()
        return {"status": "success", "job_id": job_id}

    except Exception as e:
        db.rollback()
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.error = traceback.format_exc()
            job.finished_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(bind=True, name="forge.oos_validation")
def run_oos_validation_task(self, project_id: str, job_id: str):
    """Full OOS validation battery. Stage 5. Runs once."""
    from app.db.base import SessionLocal
    from app.models.job import Job, JobStatus
    from app.models.project import Project, ProjectStage, StageEvent
    from app.models.strategy import StrategyVersion
    from app.models.data_split import DataSplit
    from app.models.report import Report
    from forge_engine.data import load_instrument
    from forge_engine.split import apply_split, DataSplit as DS
    from forge_engine.backtest import run_backtest, BacktestConfig
    from forge_engine.validation import (
        permutation_test, bootstrap_ci, monte_carlo, deflated_sharpe_ratio
    )
    from forge_engine.walk_forward import run_walk_forward, WalkForwardConfig
    from forge_engine.sensitivity import run_sensitivity
    from forge_engine.scorer import compute_score, ScoreBreakdown
    from forge_engine.validation import PermutationResult, MonteCarloResult, BootstrapResult
    import numpy as np

    db = SessionLocal()
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.commit()

        project = db.query(Project).filter(Project.id == project_id).first()
        split_rec = db.query(DataSplit).filter(DataSplit.project_id == project_id).first()
        strategy = db.query(StrategyVersion).filter(
            StrategyVersion.project_id == project_id,
            StrategyVersion.is_active == True,
        ).first()
        n_trials = db.query(StrategyVersion).filter(StrategyVersion.project_id == project_id).count()

        # Get skipped stages
        from app.models.project import StageEvent
        skipped = [
            e.stage for e in db.query(StageEvent).filter(
                StageEvent.project_id == project_id,
                StageEvent.action == "skipped"
            ).all()
        ]

        df = load_instrument(project.instrument, timeframe=project.timeframe)
        signal_fn, params = _load_strategy(strategy.source_code, strategy.params or {})

        ds = DS(
            train_start=split_rec.train_start,
            train_end=split_rec.train_end,
            test_start=split_rec.test_start,
            test_end=split_rec.test_end,
            train_bars=split_rec.train_bars,
            test_bars=split_rec.test_bars,
            recommended_by=split_rec.recommended_by,
        )
        train_df, test_df = apply_split(df, ds)

        bt_config = BacktestConfig()

        # In-sample (needed for consistency ratio)
        is_result = run_backtest(train_df, signal_fn, params, bt_config)

        # OOS backtest
        oos_result = run_backtest(test_df, signal_fn, params, bt_config)

        # Permutation test (1000 iterations)
        perm = permutation_test(test_df, signal_fn, params, n_iterations=1_000, bt_config=bt_config)

        # Bootstrap CIs
        ci = bootstrap_ci(oos_result.returns, n_iterations=1_000)

        # Monte Carlo (10k paths)
        mc = monte_carlo(oos_result.returns, n_paths=10_000, horizon_bars=252)

        # Deflated Sharpe Ratio
        from scipy.stats import skew, kurtosis
        ret_arr = oos_result.returns.values
        dsr = deflated_sharpe_ratio(
            sharpe_ratio=oos_result.metrics.get("sharpe_ratio", 0),
            n_bars=len(ret_arr),
            n_trials=n_trials,
            skewness=float(skew(ret_arr)),
            excess_kurtosis=float(kurtosis(ret_arr)),
        )

        # Walk-forward (re-run on full data for OOS report)
        wf_result = run_walk_forward(train_df, signal_fn, params, WalkForwardConfig(), bt_config)

        # Sensitivity
        sens_result = run_sensitivity(train_df, signal_fn, params, bt_config)

        # Score
        score = compute_score(
            oos_metrics=oos_result.metrics,
            insample_metrics=is_result.metrics,
            permutation=perm,
            monte_carlo=mc,
            bootstrap=ci,
            walk_forward=wf_result,
            sensitivity=sens_result,
            dsr_probability=dsr,
            skipped_stages=skipped,
        )

        # Persist report
        report_data = {
            "oos_metrics": oos_result.metrics,
            "insample_metrics": is_result.metrics,
            "permutation": {
                "p_value": perm.p_value,
                "is_significant": perm.is_significant,
                "real_sharpe": perm.real_sharpe,
                "n_iterations": perm.n_iterations,
            },
            "bootstrap_ci": ci.metrics_ci,
            "monte_carlo": {
                "prob_profit": mc.prob_profit,
                "prob_ruin": mc.prob_ruin,
                "final_equity_distribution": mc.final_equity_distribution,
                "max_drawdown_distribution": mc.max_drawdown_distribution,
                "n_paths": mc.n_paths,
                "horizon_bars": mc.horizon_bars,
            },
            "deflated_sharpe_ratio": dsr,
            "n_trials": n_trials,
            "equity_curve": oos_result.equity.tolist(),
            "equity_dates": [str(d) for d in oos_result.equity.index],
            "score_notes": score.notes,
            "skipped_stages": skipped,
        }

        existing_report = db.query(Report).filter(Report.project_id == project_id).first()
        if existing_report:
            existing_report.score = score.total
            existing_report.score_breakdown = {
                "significance": score.significance,
                "oos_performance": score.oos_performance,
                "oos_vs_insample": score.oos_vs_insample,
                "robustness": score.robustness,
                "risk": score.risk,
                "raw_total": score.raw_total,
                "total": score.total,
                "cap_applied": score.cap_applied,
            }
            existing_report.findings = report_data
            existing_report.skipped_stages = skipped
        else:
            report = Report(
                project_id=project_id,
                score=score.total,
                score_breakdown={
                    "significance": score.significance,
                    "oos_performance": score.oos_performance,
                    "oos_vs_insample": score.oos_vs_insample,
                    "robustness": score.robustness,
                    "risk": score.risk,
                    "raw_total": score.raw_total,
                    "total": score.total,
                    "cap_applied": score.cap_applied,
                },
                findings=report_data,
                skipped_stages=skipped,
            )
            db.add(report)

        job.result = {"score": score.total}
        job.status = JobStatus.SUCCESS
        job.finished_at = datetime.utcnow()

        event = StageEvent(project_id=project_id, stage=ProjectStage.VALIDATION, action="completed")
        db.add(event)
        project.current_stage = ProjectStage.DONE

        db.commit()
        return {"status": "success", "score": score.total}

    except Exception as e:
        db.rollback()
        job = db.query(Job).filter(Job.id == job_id).first()
        if job:
            job.status = JobStatus.FAILED
            job.error = traceback.format_exc()
            job.finished_at = datetime.utcnow()
            db.commit()
        raise
    finally:
        db.close()
