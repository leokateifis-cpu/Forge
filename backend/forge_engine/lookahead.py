"""
Lookahead bias detector — two passes:

1. AST static analysis: flags patterns that commonly introduce future data.
2. Dynamic truncation check: computes signals on truncated data, compares with
   full-data signals. Any difference at bar t means bar t used data beyond t.

Usage:
    result = scan_strategy_code(source_code, df)
    if result.has_lookahead:
        # block progression
"""
from __future__ import annotations

import ast
import textwrap
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

import numpy as np
import pandas as pd


@dataclass
class LookaheadFinding:
    kind: str           # "ast" | "dynamic"
    severity: str       # "error" | "warning"
    description: str
    line: int | None = None
    code_snippet: str | None = None


@dataclass
class LookaheadScanResult:
    has_lookahead: bool
    findings: list[LookaheadFinding]
    ast_findings: list[LookaheadFinding]
    dynamic_findings: list[LookaheadFinding]


# ---------------------------------------------------------------------------
# AST scanner
# ---------------------------------------------------------------------------

_AST_PATTERNS = [
    # Negative shift: df['x'].shift(-1) accesses future bars
    ("negative_shift", "error",
     "Negative shift detected: .shift(-N) uses future data."),
    # center=True rolling: uses symmetric window (future + past)
    ("rolling_center", "error",
     "rolling(center=True) uses future data in the window."),
    # iloc with positive offset from current index: df.iloc[i+1]
    ("iloc_future", "error",
     "iloc with a positive offset may reference future bars."),
    # fillna(method='bfill') or ffill on target series
    ("bfill_fillna", "warning",
     "bfill() can propagate future values backwards."),
    # Whole-series statistics: df['close'].mean() without rolling/window
    ("whole_series_stat", "warning",
     "Whole-series statistic without rolling window uses future data implicitly."),
]


class _ASTVisitor(ast.NodeVisitor):
    def __init__(self, source_lines: list[str]):
        self.source_lines = source_lines
        self.findings: list[LookaheadFinding] = []

    def _snippet(self, node: ast.AST) -> str:
        try:
            line = node.lineno - 1  # type: ignore[attr-defined]
            return self.source_lines[line].strip()
        except Exception:
            return ""

    def visit_Call(self, node: ast.Call):
        func = node.func

        # .shift(-N)
        if isinstance(func, ast.Attribute) and func.attr == "shift":
            for arg in node.args:
                if isinstance(arg, ast.UnaryOp) and isinstance(arg.op, ast.USub):
                    self.findings.append(LookaheadFinding(
                        kind="ast", severity="error",
                        description="Negative shift: .shift(-N) accesses future data.",
                        line=getattr(node, "lineno", None),
                        code_snippet=self._snippet(node),
                    ))
            for kw in node.keywords:
                if kw.arg == "periods":
                    if isinstance(kw.value, ast.UnaryOp) and isinstance(kw.value.op, ast.USub):
                        self.findings.append(LookaheadFinding(
                            kind="ast", severity="error",
                            description="Negative shift (periods=): .shift(periods=-N) accesses future data.",
                            line=getattr(node, "lineno", None),
                            code_snippet=self._snippet(node),
                        ))

        # .rolling(center=True)
        if isinstance(func, ast.Attribute) and func.attr == "rolling":
            for kw in node.keywords:
                if kw.arg == "center" and isinstance(kw.value, ast.Constant) and kw.value.value:
                    self.findings.append(LookaheadFinding(
                        kind="ast", severity="error",
                        description="rolling(center=True) uses symmetric window — includes future data.",
                        line=getattr(node, "lineno", None),
                        code_snippet=self._snippet(node),
                    ))

        # .bfill() / fillna(method='bfill')
        if isinstance(func, ast.Attribute) and func.attr == "bfill":
            self.findings.append(LookaheadFinding(
                kind="ast", severity="warning",
                description=".bfill() can propagate future values backwards.",
                line=getattr(node, "lineno", None),
                code_snippet=self._snippet(node),
            ))
        if isinstance(func, ast.Attribute) and func.attr == "fillna":
            for kw in node.keywords:
                if kw.arg == "method" and isinstance(kw.value, ast.Constant) and kw.value.value == "bfill":
                    self.findings.append(LookaheadFinding(
                        kind="ast", severity="warning",
                        description="fillna(method='bfill') can propagate future values backwards.",
                        line=getattr(node, "lineno", None),
                        code_snippet=self._snippet(node),
                    ))

        # Whole-series stats without rolling: .mean() / .std() / .max() / .min() on a Series
        # Heuristic: .mean() called directly on a column access with no rolling/expanding before it
        if isinstance(func, ast.Attribute) and func.attr in ("mean", "std", "max", "min", "sum"):
            # Check the receiver isn't a rolling/expanding
            recv = func.value
            if isinstance(recv, ast.Subscript):
                # Likely df['col'].mean() — whole series
                self.findings.append(LookaheadFinding(
                    kind="ast", severity="warning",
                    description=f"Whole-series .{func.attr}() without rolling window uses all future data.",
                    line=getattr(node, "lineno", None),
                    code_snippet=self._snippet(node),
                ))

        self.generic_visit(node)


def _ast_scan(source: str) -> list[LookaheadFinding]:
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return [LookaheadFinding(kind="ast", severity="error",
                                  description=f"Syntax error in generated code: {e}")]

    lines = source.splitlines()
    visitor = _ASTVisitor(lines)
    visitor.visit(tree)
    return visitor.findings


# ---------------------------------------------------------------------------
# Dynamic truncation check
# ---------------------------------------------------------------------------

def _dynamic_scan(
    source: str,
    df: pd.DataFrame,
    n_check_bars: int = 20,
) -> list[LookaheadFinding]:
    """
    Compile the strategy, run signals on full df, then run on progressively
    truncated df. Any signal difference at bar t means bar t used data > t.
    """
    findings: list[LookaheadFinding] = []

    try:
        module = _load_strategy_module(source)
    except Exception as e:
        findings.append(LookaheadFinding(
            kind="dynamic", severity="error",
            description=f"Could not compile strategy for dynamic scan: {e}",
        ))
        return findings

    try:
        signal_fn = module.generate_signals
        default_params = getattr(module, "DEFAULT_PARAMS", {})
    except AttributeError:
        findings.append(LookaheadFinding(
            kind="dynamic", severity="error",
            description="Strategy module must define generate_signals() and DEFAULT_PARAMS.",
        ))
        return findings

    try:
        full_signals = signal_fn(df, default_params)
    except Exception as e:
        findings.append(LookaheadFinding(
            kind="dynamic", severity="error",
            description=f"generate_signals raised an error: {e}",
        ))
        return findings

    # Check the last n_check_bars
    check_indices = range(max(10, len(df) - n_check_bars), len(df))

    for i in check_indices:
        truncated = df.iloc[:i].copy()
        try:
            trunc_signals = signal_fn(truncated, default_params)
        except Exception:
            continue

        # Signal at the last bar of the truncated run
        last_idx = truncated.index[-1]
        if last_idx not in full_signals.index:
            continue

        full_val = full_signals.loc[last_idx]
        trunc_val = trunc_signals.iloc[-1] if len(trunc_signals) > 0 else np.nan

        if not np.isnan(full_val) and not np.isnan(trunc_val):
            if not np.isclose(full_val, trunc_val, atol=1e-8):
                findings.append(LookaheadFinding(
                    kind="dynamic", severity="error",
                    description=(
                        f"Signal at bar {last_idx} differs between full data ({full_val:.4f}) "
                        f"and truncated data ({trunc_val:.4f}). "
                        "The strategy uses data beyond the current bar."
                    ),
                ))
                break  # One confirmed finding is enough

    return findings


def _load_strategy_module(source: str) -> ModuleType:
    """Execute strategy source in a fresh module namespace."""
    import types
    module = types.ModuleType("_forge_strategy")
    exec(compile(source, "<strategy>", "exec"), module.__dict__)  # noqa: S102
    return module


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def scan_strategy_code(
    source: str,
    df: pd.DataFrame | None = None,
    run_dynamic: bool = True,
) -> LookaheadScanResult:
    """
    Scan strategy source for lookahead bias.

    Args:
        source: Python source of the strategy module.
        df: OHLCV DataFrame for dynamic check. Required if run_dynamic=True.
        run_dynamic: Whether to run the truncation check.

    Returns:
        LookaheadScanResult with all findings.
    """
    ast_findings = _ast_scan(source)

    dynamic_findings: list[LookaheadFinding] = []
    if run_dynamic and df is not None and len(df) >= 30:
        dynamic_findings = _dynamic_scan(source, df)

    all_findings = ast_findings + dynamic_findings
    has_lookahead = any(f.severity == "error" for f in all_findings)

    return LookaheadScanResult(
        has_lookahead=has_lookahead,
        findings=all_findings,
        ast_findings=ast_findings,
        dynamic_findings=dynamic_findings,
    )
