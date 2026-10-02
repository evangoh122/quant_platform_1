"""
evals/run_eval.py ? Golden-set evaluation runner for RAG Workbench.

Scores the /api/chat/auditable-rag endpoint on four axes:
  1. correctness   ? answer matches expected (fuzzy numeric or keyword)
  2. xbrl_verified ? XBRL cross-check passed (uses verification.status)
  3. has_sources   ? at least one source chunk was returned
  4. abstention    ? model correctly refused when expected == ABSTAIN*

Usage:
    python evals/run_eval.py                          # runs against localhost:8000
    python evals/run_eval.py --api-url http://...     # custom API URL
    python evals/run_eval.py --dry-run                # validate golden set, no API calls
    python evals/run_eval.py --id 5                   # run a single question by ID
    python evals/run_eval.py --mode gaap_vs_nongaap   # filter by failure mode
    EVAL_API_URL=http://... python evals/run_eval.py  # via env var
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

# Make the repo root importable so `from api...` works when run as a script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

GOLDEN_SET_PATH = Path(__file__).parent / "golden_set.csv"
RESULTS_DIR = Path(__file__).parent / "results"


def _git_sha() -> Optional[str]:
    """Best-effort short commit SHA for run provenance."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def persist_to_duckdb(
    data: dict,
    *,
    api_url: str,
    filter_id: Optional[str] = None,
    filter_mode: Optional[str] = None,
) -> Optional[str]:
    """Persist the run to the review/runtime DuckDB. Best-effort.

    Returns the run_id on success, or None if persistence was skipped (e.g. the
    review DB is locked by a running API server, or deps are unavailable). Never
    raises — a failed write must not fail the eval run.
    """
    try:
        from api.db.database import db_manager
        from api.db.review_queue import persist_eval_run

        conn = db_manager.get_review_connection()
        run_id = persist_eval_run(
            conn, data,
            api_url=api_url,
            git_sha=_git_sha(),
            filter_id=filter_id,
            filter_mode=filter_mode,
        )
        return run_id
    except Exception as e:  # noqa: BLE001 — intentional best-effort guard
        print(f"  [db] skipped DuckDB persistence: {str(e)[:120]}")
        return None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ABSTENTION_PHRASES = [
    "not disclosed", "can't verify", "cannot verify", "unable to",
    "insufficient", "not available", "abstain", "no data", "not reported",
    "don't have", "do not have", "not found", "no information",
    "not in the filing", "not mentioned",
]

_SCALES = {
    "trillion": 1e12, "T": 1e12,
    "billion": 1e9,   "B": 1e9,
    "million": 1e6,   "M": 1e6,
    "thousand": 1e3,  "K": 1e3,
}

# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _extract_number(text: str) -> Optional[float]:
    """Extract the first dollar-value or scaled number from text."""
    for pattern, group_scale in [
        (r"\$?([\d,]+(?:\.\d+)?)\s*(trillion|T|billion|B|million|M|thousand|K)\b", True),
        (r"\$?([\d,]+(?:\.\d+)?)", False),
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = float(m.group(1).replace(",", ""))
            scale = _SCALES.get(m.group(2), 1.0) if group_scale and len(m.groups()) > 1 else 1.0
            return raw * scale
    return None


def score_correctness(expected: str, answer: str) -> tuple[float, str]:
    """Score answer correctness. Returns (score 0.0?1.0, reason)."""
    exp = expected.strip()
    ans_lower = answer.lower()
    exp_lower = exp.lower()

    # -- Abstention questions -----------------------------------------------
    if exp_lower.startswith("abstain"):
        if any(phrase in ans_lower for phrase in ABSTENTION_PHRASES):
            return 1.0, "correctly abstained"
        return 0.0, "should have abstained but gave a confident answer"

    # -- Percentage --------------------------------------------------------
    if "%" in exp:
        exp_pct = _extract_number(exp.replace("%", ""))
        ans_pct = _extract_number(answer.replace("%", ""))
        if exp_pct is not None and ans_pct is not None:
            delta = abs(exp_pct - ans_pct)
            return (1.0, f"% match (?={delta:.2f}pp)") if delta <= 0.5 else (0.0, f"% mismatch: expected {exp_pct}%, got {ans_pct}%")

    # -- Numeric -----------------------------------------------------------
    exp_num = _extract_number(exp)
    ans_num = _extract_number(answer)
    if exp_num is not None and ans_num is not None and exp_num != 0:
        delta = abs(exp_num - ans_num) / abs(exp_num)
        if delta <= 0.02:
            return 1.0, f"numeric match (?={delta:.1%})"
        return 0.0, f"numeric mismatch: expected {exp_num:,.0f}, got {ans_num:,.0f} (?={delta:.1%})"

    # -- Keyword fallback --------------------------------------------------
    stop = {"was", "is", "the", "a", "an", "for", "in", "of", "and", "or",
            "usd", "billion", "million", "its", "that", "at", "had"}
    keywords = [w for w in re.findall(r"\w+", exp_lower) if w not in stop and len(w) > 3]
    if keywords:
        matched = sum(1 for w in keywords if w in ans_lower)
        score = matched / len(keywords)
        return round(min(score, 1.0), 2), f"{matched}/{len(keywords)} keywords matched"

    return 0.5, "unable to score automatically"


def score_xbrl(response: dict, xbrl_concept: str) -> tuple[float, str]:
    """Score XBRL verification. N/A concepts always pass."""
    if xbrl_concept in ("N/A", "", None):
        return 1.0, "N/A ? non-GAAP or non-financial metric"

    verification = response.get("verification") or {}
    status = verification.get("status", "not_checked")

    if status == "verified":
        return 1.0, "XBRL verified OK"
    if status == "mismatch":
        c = verification.get("claimed_value")
        x = verification.get("xbrl_value")
        return 0.0, f"XBRL mismatch: claimed={c:,.0f}, xbrl={x:,.0f}" if c and x else "XBRL mismatch"
    if status == "unverifiable":
        return 0.5, "unverifiable (no XBRL fact found for period/concept)"
    return 0.5, f"not checked (status={status})"


def score_has_sources(response: dict) -> tuple[float, str]:
    """Score whether the response includes source chunks."""
    sources = response.get("sources") or []
    if sources:
        accessions = {s.get("accession", "") for s in sources if isinstance(s, dict)}
        return 1.0, f"{len(sources)} source(s), {len(accessions)} filing(s)"
    return 0.0, "no sources returned"


def score_abstention(expected: str, response: dict) -> tuple[float, str]:
    """Only scored when expected starts with ABSTAIN. Otherwise N/A ? 1.0."""
    if not expected.lower().startswith("abstain"):
        return 1.0, "N/A"
    answer = (response.get("answer") or "").lower()
    if any(phrase in answer for phrase in ABSTENTION_PHRASES):
        return 1.0, "model correctly declined to answer"
    return 0.0, "model gave a confident answer when abstention was expected"


# ---------------------------------------------------------------------------
# API call
# ---------------------------------------------------------------------------

def call_api(api_url: str, question: str, ticker: str, timeout: int = 45) -> dict:
    try:
        resp = requests.post(
            f"{api_url}/api/chat/auditable-rag",
            json={"message": question, "ticker": ticker},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        return {"answer": f"[API ERROR: {e}]", "sources": [], "verification": {}, "error": str(e)}


# ---------------------------------------------------------------------------
# Golden set loader
# ---------------------------------------------------------------------------

def load_golden_set(
    filter_id: Optional[str] = None,
    filter_mode: Optional[str] = None,
) -> list[dict]:
    rows = []
    with open(GOLDEN_SET_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if filter_id and row["id"] != filter_id:
                continue
            if filter_mode and row["failure_mode"] != filter_mode:
                continue
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Main eval loop
# ---------------------------------------------------------------------------

def run(
    api_url: str,
    dry_run: bool = False,
    delay: float = 1.0,
    filter_id: Optional[str] = None,
    filter_mode: Optional[str] = None,
) -> dict:
    questions = load_golden_set(filter_id=filter_id, filter_mode=filter_mode)
    if not questions:
        print("No questions matched the filter.")
        sys.exit(1)

    print(f"\n{'='*68}")
    print(f"  RAG Workbench Eval Runner")
    print(f"  {len(questions)} question(s)  |  API: {api_url}  |  dry_run={dry_run}")
    print(f"{'='*68}\n")

    results = []
    for q in questions:
        qid      = q["id"]
        ticker   = q["ticker"]
        question = q["question"]
        expected = q["expected_answer"]
        concept  = q.get("xbrl_concept", "N/A")
        mode     = q.get("failure_mode", "unknown")
        diff     = q.get("difficulty", "?")

        if dry_run:
            response: dict = {"answer": "", "sources": [], "verification": {}}
        else:
            response = call_api(api_url, question, ticker)
            time.sleep(delay)

        answer = response.get("answer", "")

        c_score, c_reason = score_correctness(expected, answer)
        x_score, x_reason = score_xbrl(response, concept)
        s_score, s_reason = score_has_sources(response)
        a_score, a_reason = score_abstention(expected, response)

        # Abstention N/A rows excluded from overall so they don't inflate scores
        scored_axes = [c_score, x_score, s_score]
        if not expected.lower().startswith("abstain"):
            scored_axes.append(a_score)
        overall = round(sum(scored_axes) / len(scored_axes), 3)

        icon = "OK" if overall >= 0.75 else ("~" if overall >= 0.5 else "FAIL")
        print(f"  [{icon}] #{qid:>2} [{mode:<22}] {ticker} [{diff:<6}]  "
              f"overall={overall:.0%}  correct={c_score:.0%}  "
              f"xbrl={x_score:.0%}  src={s_score:.0%}")
        if overall < 0.75 and not dry_run:
            print(f"       correctness: {c_reason}")
            if x_score < 1.0:
                print(f"       xbrl:        {x_reason}")

        results.append({
            "id": qid, "ticker": ticker, "company": q.get("company", ""),
            "failure_mode": mode, "difficulty": diff,
            "question": question,
            "expected": expected,
            "answer_snippet": answer[:200] if answer else "",
            "correctness": c_score, "correctness_reason": c_reason,
            "xbrl": x_score, "xbrl_reason": x_reason,
            "sources": s_score, "sources_reason": s_reason,
            "abstention": a_score, "abstention_reason": a_reason,
            "overall": overall,
            "has_error": bool(response.get("error")),
        })

    return _summarise(results)


# ---------------------------------------------------------------------------
# Summary + taxonomy
# ---------------------------------------------------------------------------

def _summarise(results: list[dict]) -> dict:
    n = len(results)
    axes = ["correctness", "xbrl", "sources", "overall"]
    summary = {ax: round(sum(r[ax] for r in results) / n, 3) for ax in axes}
    pass_rate = sum(1 for r in results if r["overall"] >= 0.75) / n

    print(f"\n{'='*68}")
    print(f"  Summary ({n} questions)")
    print(f"{'='*68}")
    for ax in axes:
        bar = "#" * int(summary[ax] * 30) + "-" * (30 - int(summary[ax] * 30))
        print(f"  {ax:<14}  {bar}  {summary[ax]:.0%}")
    print(f"\n  Pass rate (?75%): {pass_rate:.0%}  ({sum(1 for r in results if r['overall'] >= 0.75)}/{n})")

    # Failure mode breakdown
    by_mode: dict[str, list[float]] = {}
    for r in results:
        by_mode.setdefault(r["failure_mode"], []).append(r["overall"])

    print(f"\n{'='*68}")
    print("  Failure mode breakdown:")
    print(f"  {'Mode':<24} {'Score':>6}  {'n':>4}  Bar")
    print(f"  {'-'*24} {'-'*6}  {'-'*4}  {'-'*20}")
    for mode, scores in sorted(by_mode.items(), key=lambda x: sum(x[1]) / len(x[1])):
        avg = sum(scores) / len(scores)
        bar = "#" * int(avg * 20)
        print(f"  {mode:<24} {avg:>5.0%}  {len(scores):>4}  {bar}")

    # Worst questions
    worst = sorted(results, key=lambda r: r["overall"])[:5]
    print(f"\n{'='*68}")
    print("  Lowest scoring questions:")
    for r in worst:
        print(f"  #{r['id']:>2} [{r['failure_mode']:<22}] {r['ticker']}  "
              f"{r['overall']:.0%}  ? {r['correctness_reason'][:60]}")

    print(f"\n{'='*68}\n")

    return {
        "summary": summary,
        "pass_rate": round(pass_rate, 3),
        "n": n,
        "results": results,
        "by_failure_mode": {k: round(sum(v) / len(v), 3) for k, v in by_mode.items()},
        "run_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Persist results
# ---------------------------------------------------------------------------

def save_results(data: dict, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    json_path = out_dir / f"eval_{ts}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)

    csv_path = out_dir / f"eval_{ts}.csv"
    if data["results"]:
        keys = [k for k in data["results"][0] if k != "answer_snippet"]
        keys.append("answer_snippet")
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
            w.writeheader()
            w.writerows(data["results"])

    return json_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="RAG Workbench golden-set eval runner"
    )
    parser.add_argument(
        "--api-url",
        default=os.getenv("EVAL_API_URL", "http://localhost:8000"),
        help="Base URL of the running RAG Workbench API",
    )
    parser.add_argument(
        "--out",
        default=str(RESULTS_DIR),
        help="Directory for result JSON/CSV output",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate golden set structure without calling the API",
    )
    parser.add_argument(
        "--id",
        dest="filter_id",
        default=None,
        help="Run a single question by its ID (e.g. --id 5)",
    )
    parser.add_argument(
        "--mode",
        dest="filter_mode",
        default=None,
        help="Filter by failure_mode (e.g. --mode gaap_vs_nongaap)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between API calls (default: 1.0)",
    )
    parser.add_argument(
        "--no-db",
        action="store_true",
        help="Do not persist the run to the review/runtime DuckDB",
    )
    args = parser.parse_args()

    data = run(
        api_url=args.api_url,
        dry_run=args.dry_run,
        delay=args.delay,
        filter_id=args.filter_id,
        filter_mode=args.filter_mode,
    )

    if not args.dry_run:
        out_path = save_results(data, Path(args.out))
        print(f"  Results saved ? {out_path}")

        if not args.no_db:
            run_id = persist_to_duckdb(
                data,
                api_url=args.api_url,
                filter_id=args.filter_id,
                filter_mode=args.filter_mode,
            )
            if run_id:
                print(f"  Persisted to DuckDB (eval_runs/eval_results) ? run_id={run_id}")

    failed = [r for r in data["results"] if r["overall"] < 0.5]
    if failed:
        print(f"  {len(failed)} question(s) below 50% ? see results for taxonomy\n")
        sys.exit(1)
    sys.exit(0)
