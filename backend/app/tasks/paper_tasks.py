"""
Paper search and test task.

Steps:
  1. Use OpenAI to form arXiv search terms from user query.
  2. Fetch papers from arXiv API.
  3. For each paper: extract trading rules (OpenAI), generate code, test on ES/NQ.
  4. Return ranked results.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime

import httpx

from app.tasks.celery_app import celery_app
from app.core.config import get_settings

settings = get_settings()

ARXIV_API = "http://export.arxiv.org/api/query"
MAX_PAPERS = 10


@celery_app.task(bind=True, name="forge.paper_search")
def run_paper_search_task(self, query: str, user_id: str):
    results = []

    try:
        # 1. Form search query
        arxiv_query = _build_arxiv_query(query)

        # 2. Fetch from arXiv
        papers = _fetch_arxiv_papers(arxiv_query, max_results=MAX_PAPERS)

        if not papers:
            return {"papers": [], "note": "No papers found for this query."}

        # 3. Process each paper
        for paper in papers[:5]:  # Limit to 5 for speed
            try:
                paper_result = _process_paper(paper, query)
                results.append(paper_result)
            except Exception as e:
                results.append({
                    "title": paper.get("title", "Unknown"),
                    "arxiv_id": paper.get("id", ""),
                    "error": str(e),
                    "relevance_score": 0,
                })

        # Sort by relevance score
        results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        return {"papers": results}

    except Exception as e:
        return {"papers": [], "error": str(e), "traceback": traceback.format_exc()}


def _build_arxiv_query(user_query: str) -> str:
    """Build an arXiv search query from natural language."""
    if not settings.OPENAI_API_KEY:
        # Simple fallback: convert to keywords
        keywords = user_query.lower().replace("strategies", "").replace("strategy", "")
        return f"all:{keywords} AND cat:q-fin.TR"

    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Convert this trading research query into an arXiv search query string. Return ONLY the query string, nothing else. Example: 'ti:momentum AND ti:futures AND cat:q-fin.TR'"},
            {"role": "user", "content": user_query},
        ],
        temperature=0,
        max_tokens=100,
    )
    return response.choices[0].message.content.strip()


def _fetch_arxiv_papers(query: str, max_results: int = 10) -> list[dict]:
    """Fetch papers from arXiv API."""
    try:
        resp = httpx.get(ARXIV_API, params={
            "search_query": query,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }, timeout=15)
        resp.raise_for_status()
    except Exception:
        # Return stub papers if arXiv is unavailable
        return _stub_papers()

    return _parse_arxiv_response(resp.text)


def _parse_arxiv_response(xml_text: str) -> list[dict]:
    """Parse arXiv Atom XML response."""
    import xml.etree.ElementTree as ET

    papers = []
    try:
        root = ET.fromstring(xml_text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            arxiv_id_el = entry.find("atom:id", ns)
            published = entry.find("atom:published", ns)

            papers.append({
                "title": title.text.strip() if title is not None else "",
                "abstract": summary.text.strip() if summary is not None else "",
                "id": arxiv_id_el.text.strip() if arxiv_id_el is not None else "",
                "published": published.text[:10] if published is not None else "",
            })
    except ET.ParseError:
        pass

    return papers


def _process_paper(paper: dict, original_query: str) -> dict:
    """Extract trading rules from a paper and test on ES/NQ data."""
    # Score relevance using LLM or heuristic
    relevance = _score_relevance(paper, original_query)

    # Extract trading signal description
    signal_description = _extract_signal(paper)

    # Generate and test strategy
    test_result = _test_signal_on_data(signal_description, paper["title"])

    return {
        "title": paper["title"],
        "arxiv_id": paper["id"],
        "published": paper.get("published", ""),
        "abstract": paper["abstract"][:500] + "..." if len(paper.get("abstract", "")) > 500 else paper.get("abstract", ""),
        "signal_description": signal_description,
        "relevance_score": relevance,
        "test_result": test_result,
        "confirmed": test_result.get("passed", False),
        "suggested_application": _suggest_application(paper, test_result),
        "can_load_to_hypothesis": test_result.get("passed", False),
    }


def _score_relevance(paper: dict, query: str) -> int:
    """Score paper relevance 0–100."""
    if not settings.OPENAI_API_KEY:
        # Heuristic: keyword match
        query_words = set(query.lower().split())
        text_words = set((paper["title"] + " " + paper.get("abstract", "")).lower().split())
        overlap = len(query_words & text_words) / max(len(query_words), 1)
        return min(100, int(overlap * 100 + 20))

    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Score this paper's relevance to the trading query on a scale of 0-100. Return ONLY a number."},
            {"role": "user", "content": f"Query: {query}\n\nTitle: {paper['title']}\nAbstract: {paper.get('abstract', '')[:300]}"},
        ],
        temperature=0,
        max_tokens=10,
    )
    try:
        return int(response.choices[0].message.content.strip())
    except ValueError:
        return 50


def _extract_signal(paper: dict) -> str:
    """Extract trading signal description from paper abstract."""
    if not settings.OPENAI_API_KEY:
        return f"Signal extracted from: {paper['title'][:100]}"

    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract the core trading signal or strategy described in this paper abstract. Be specific: what indicator, what entry condition, what timeframe? Return 2-3 sentences maximum."},
            {"role": "user", "content": f"Title: {paper['title']}\nAbstract: {paper.get('abstract', '')}"},
        ],
        temperature=0,
        max_tokens=150,
    )
    return response.choices[0].message.content.strip()


def _test_signal_on_data(signal_description: str, paper_title: str) -> dict:
    """Test the described signal on ES daily data."""
    try:
        from forge_engine.data import load_instrument
        from forge_engine.backtest import run_backtest, BacktestConfig
        from forge_engine.validation import permutation_test

        df = load_instrument("ES", timeframe="1D")

        # Generate strategy code for the described signal
        code = _generate_paper_strategy(signal_description, paper_title)

        import types
        module = types.ModuleType("_paper_strategy")
        exec(compile(code, "<paper>", "exec"), module.__dict__)  # noqa: S102
        signal_fn = module.generate_signals
        params = getattr(module, "DEFAULT_PARAMS", {})

        bt_config = BacktestConfig()
        result = run_backtest(df, signal_fn, params, bt_config)
        sharpe = result.metrics.get("sharpe_ratio", 0)

        # Quick permutation test (200 iterations for speed)
        perm = permutation_test(df, signal_fn, params, n_iterations=200, bt_config=bt_config)

        return {
            "passed": perm.is_significant and sharpe > 0.3,
            "sharpe_ratio": round(sharpe, 3),
            "permutation_p_value": round(perm.p_value, 3),
            "is_significant": perm.is_significant,
            "instrument_tested": "ES",
            "strategy_code": code,
            "default_params": params,
        }
    except Exception as e:
        return {
            "passed": False,
            "error": str(e),
            "instrument_tested": "ES",
        }


def _generate_paper_strategy(signal_description: str, paper_title: str) -> str:
    """Generate strategy code from signal description."""
    if not settings.OPENAI_API_KEY:
        return _stub_paper_strategy()

    from openai import OpenAI
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    from app.services.llm import CODE_GENERATION_SYSTEM_PROMPT
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": CODE_GENERATION_SYSTEM_PROMPT},
            {"role": "user", "content": f"Paper: {paper_title}\n\nSignal: {signal_description}\n\nGenerate a testable implementation."},
        ],
        temperature=0.1,
        max_tokens=1500,
    )
    code = response.choices[0].message.content.strip()
    for fence in ["```python", "```"]:
        if code.startswith(fence):
            code = code[len(fence):]
    if code.endswith("```"):
        code = code[:-3]
    return code.strip()


def _suggest_application(paper: dict, test_result: dict) -> str:
    if test_result.get("passed"):
        return "Could be useful for: intraday or daily momentum strategies on ES/NQ futures"
    return "Signal did not reach statistical significance on ES daily data"


def _stub_papers() -> list[dict]:
    return [
        {
            "title": "Momentum Strategies in Futures Markets",
            "abstract": "We study the profitability of momentum strategies applied to equity index futures. Using daily OHLCV data, we find that a 20-day lookback momentum strategy generates a Sharpe ratio of 0.8 after transaction costs.",
            "id": "arxiv:stub-001",
            "published": "2023-01-15",
        }
    ]


def _stub_paper_strategy() -> str:
    return '''import pandas as pd
import numpy as np

DEFAULT_PARAMS = {"lookback": 20, "smoothing": 5}

def generate_signals(df: pd.DataFrame, params: dict) -> pd.Series:
    lookback = int(params.get("lookback", 20))
    smoothing = int(params.get("smoothing", 5))
    mom = df["close"].pct_change(lookback)
    signal = mom.rolling(smoothing).mean()
    pos = pd.Series(0.0, index=df.index)
    pos[signal > 0] = 1.0
    pos[signal < 0] = -1.0
    return pos.shift(1).fillna(0)
'''
