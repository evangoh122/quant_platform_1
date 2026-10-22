"""Part A of BUILD-evidently-drift-cleanup: dead-code reference check.

``api/services/drift_detection.py`` imported a non-existent ``api.db.review_queue``
(no ``api/db/`` exists), its ``check_drift``/``log_drift_alert`` had no callers,
and OWNER_PLAN forbids review-queue APIs — so the module and its test/doc
references were deleted.  These tests pin that deletion:

  * restoring the module must fail the first test ("removing the deletion makes
    the reference-check test fail");
  * any surviving test/doc/code reference must fail the second test.

The file lives under ``tests/ml/`` because the build request only permits test
additions for ``ml/``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEAD_MODULE = REPO_ROOT / "api" / "services" / "drift_detection.py"

# Public surface of the deleted module (``DriftStatus`` is bounded so the
# unrelated ``DriftStatusOut`` name from the removed review schemas is not
# matched).
DEAD_SYMBOLS = (
    re.compile(r"drift_detection"),
    re.compile(r"check_drift"),
    re.compile(r"log_drift_alert"),
    re.compile(r"DriftStatus\b"),
)

SCAN_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".toml", ".txt", ".cfg", ".ini", ".json", ".ipynb", ".sh"}
SKIP_DIRS = {"__pycache__", "node_modules", "dist", "build", "mlruns", "checkpoints"}


def _iter_repo_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SCAN_SUFFIXES:
            continue
        rel = path.relative_to(REPO_ROOT)
        if any(part.startswith(".") for part in rel.parts[:-1]) or rel.parts[0].startswith("."):
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if path == Path(__file__).resolve():
            continue
        yield rel, path


def test_dead_drift_module_is_deleted():
    """The unused review-queue drift module must stay deleted."""
    assert not DEAD_MODULE.exists(), (
        f"{DEAD_MODULE.relative_to(REPO_ROOT)} is dead code (imports the non-existent "
        "api.db.review_queue, no callers, review-queue APIs forbidden) and must not return"
    )


def test_no_remaining_references_to_dead_drift_module():
    """No test/doc/code reference to the deleted module may survive."""
    hits = []
    for rel, path in _iter_repo_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pattern in DEAD_SYMBOLS:
                if pattern.search(line):
                    hits.append(f"{rel}:{lineno}: {line.strip()[:120]}")
    assert not hits, "references to the deleted api/services/drift_detection.py remain:\n" + "\n".join(hits)
