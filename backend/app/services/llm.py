"""
LLM service — hypothesis interview and strategy code generation.

The hypothesis interview runs in a constrained mode: the assistant asks clarifying
questions until all required fields in the HypothesisSchema are filled.

Code generation produces a strategy module that follows the fixed contract:
  DEFAULT_PARAMS = {"lookback": 20, ...}
  def generate_signals(df: pd.DataFrame, params: dict) -> pd.Series:
      ...

If OPENAI_API_KEY is not set, all calls return stub data so the app can run
without an API key during development.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator

from app.core.config import get_settings

settings = get_settings()

HYPOTHESIS_SYSTEM_PROMPT = """You are Forge's research assistant. Your job is to help traders define a precise, testable trading hypothesis.

You ask clarifying questions until you can fill ALL of these fields:
- instrument: the specific asset (e.g. "ES" for S&P 500 E-mini futures, "AAPL" for Apple stock)
- timeframe: the bar size (e.g. "1D" for daily, "1H" for hourly)
- entry_rule: exact conditions that trigger a trade entry
- exit_rule: exact conditions that close the trade
- direction: "long", "short", or "both"
- expected_holding_period: approximate average hold (e.g. "2-5 days")
- claim: the testable statement ("Momentum persists for 3 days after a volume breakout on ES daily bars")
- falsification_condition: what result would prove the hypothesis wrong

Once ALL fields are known, respond with EXACTLY this JSON block (no other text):
<hypothesis>
{
  "instrument": "...",
  "timeframe": "...",
  "entry_rule": "...",
  "exit_rule": "...",
  "direction": "...",
  "expected_holding_period": "...",
  "claim": "...",
  "falsification_condition": "..."
}
</hypothesis>

Before that point, ask one focused question at a time. Keep answers short. Never generate code."""

CODE_GENERATION_SYSTEM_PROMPT = """You are Forge's strategy code generator.

Given a confirmed trading hypothesis, generate a Python strategy module that follows EXACTLY this contract:

```python
import pandas as pd
import numpy as np

# Parameters and their default values. The engine will sweep these for sensitivity analysis.
DEFAULT_PARAMS = {
    "param_name": default_value,
    # ... more params
}

def generate_signals(df: pd.DataFrame, params: dict) -> pd.Series:
    \"\"\"
    Args:
        df: OHLCV DataFrame with columns: open, high, low, close, volume
            Index is DatetimeIndex, sorted ascending.
        params: dict of parameter values (always use params.get("key", default))
    Returns:
        pd.Series of positions: 1.0 (long), -1.0 (short), 0.0 (flat)
        Must be indexed like df. Use .shift(1) to avoid lookahead.
    \"\"\"
    ...
```

CRITICAL RULES to avoid lookahead bias:
1. NEVER use .shift(-N) with negative N
2. NEVER use .rolling(center=True)
3. ALWAYS use .shift(1) on the final signal before returning (enter next bar)
4. NEVER compute statistics on the whole series (like df['close'].mean()) — use .rolling(N)
5. NEVER use .bfill() or fillna(method='bfill')

Return ONLY the Python code, no explanation."""

SKIP_WARNING_TEMPLATE = {
    1: "Your hypothesis has not been fully defined yet. Without a clear, testable hypothesis, the strategy code may not test what you think it does, and any results will be difficult to interpret.",
    2: "The strategy code has not been verified for lookahead bias. Without this check, any results showing good performance may reflect a strategy that uses future data — producing results that are impossible to replicate in live trading.",
    3: "The data has not been split into training and test sets. Without a held-out test period, you cannot know whether your in-sample results reflect a real edge or simply curve-fitting to historical noise.",
    4: "The in-sample development stage has not been completed. This means no walk-forward validation, no parameter sensitivity check, and no fragility analysis. Strategies that have not been tested for robustness frequently fail in live trading even when their backtest looks strong.",
    5: "The out-of-sample validation has not been run. Without this, there is no independent statistical evidence of a genuine edge. The strategy's results have not been tested against unseen data.",
}


async def run_hypothesis_chat(
    messages: list[dict],
) -> AsyncGenerator[str, None]:
    """Stream a response in the hypothesis interview."""
    if not settings.OPENAI_API_KEY:
        yield _stub_hypothesis_response(messages)
        return

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    full_messages = [{"role": "system", "content": HYPOTHESIS_SYSTEM_PROMPT}] + messages

    async for chunk in await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=full_messages,
        stream=True,
        temperature=0.3,
        max_tokens=1000,
    ):
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


async def generate_strategy_code(hypothesis: dict) -> str:
    """Generate strategy code from a confirmed hypothesis."""
    if not settings.OPENAI_API_KEY:
        return _stub_strategy_code(hypothesis)

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    user_message = f"""Generate a strategy for this hypothesis:

{json.dumps(hypothesis, indent=2)}

Remember: use DEFAULT_PARAMS, generate_signals(df, params), always .shift(1) the signal."""

    response = await client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": CODE_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.1,
        max_tokens=2000,
    )

    code = response.choices[0].message.content
    # Strip markdown code fences if present
    code = code.strip()
    if code.startswith("```python"):
        code = code[9:]
    if code.startswith("```"):
        code = code[3:]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()


def parse_hypothesis_from_response(text: str) -> dict | None:
    """Extract the <hypothesis>...</hypothesis> JSON block from an LLM response."""
    import re
    match = re.search(r"<hypothesis>\s*(\{.*?\})\s*</hypothesis>", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None


def get_skip_warning(stage: int) -> str:
    return SKIP_WARNING_TEMPLATE.get(
        stage,
        f"This stage has not been completed. Skipping it means the strategy has not been fully validated."
    )


# ---------------------------------------------------------------------------
# Stubs for development without an API key
# ---------------------------------------------------------------------------

def _stub_hypothesis_response(messages: list[dict]) -> str:
    last = messages[-1]["content"].lower() if messages else ""
    if any(w in last for w in ["momentum", "volume", "breakout", "trend"]):
        return """I can help you test that hypothesis. Let me ask a few questions to make it precise.

1. Which instrument are you thinking about? (e.g., ES futures, NQ futures, a specific stock)
2. What timeframe — daily bars, hourly, or shorter?"""
    return "Tell me about the trading idea you'd like to test. What market behaviour do you think you've spotted?"


def _stub_strategy_code(hypothesis: dict) -> str:
    instrument = hypothesis.get("instrument", "ES")
    return f'''import pandas as pd
import numpy as np

# Strategy: {hypothesis.get("claim", "Momentum strategy")}
# Instrument: {instrument}

DEFAULT_PARAMS = {{
    "lookback": 20,
    "volume_threshold": 1.5,
}}


def generate_signals(df: pd.DataFrame, params: dict) -> pd.Series:
    """
    Entry: close above N-day SMA AND volume > threshold * average volume.
    Exit: close below N-day SMA.
    """
    lookback = int(params.get("lookback", 20))
    vol_thresh = float(params.get("volume_threshold", 1.5))

    sma = df["close"].rolling(lookback).mean()
    avg_vol = df["volume"].rolling(lookback).mean()

    long_entry = (df["close"] > sma) & (df["volume"] > avg_vol * vol_thresh)
    long_exit = df["close"] < sma

    pos = pd.Series(0.0, index=df.index)
    in_trade = False
    for i in range(lookback, len(df)):
        if not in_trade and long_entry.iloc[i]:
            in_trade = True
        elif in_trade and long_exit.iloc[i]:
            in_trade = False
        pos.iloc[i] = 1.0 if in_trade else 0.0

    # Enter next bar — avoid lookahead
    return pos.shift(1).fillna(0.0)
'''
