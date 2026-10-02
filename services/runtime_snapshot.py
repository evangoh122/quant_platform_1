"""
runtime_snapshot.py — Persist the runtime/review DuckDB to the private HF dataset.

WHY: the HF Space runs on `cpu-basic` with no persistent volume (`storage: None`),
so `review_queue.duckdb` — audit_runs, HITL review_decisions/reviewer_verdicts,
calibration_history, eval_runs/eval_results, analytics_events — lives on the
ephemeral container disk and is wiped on every restart. To make it durable
WITHOUT paying for Space persistent storage, we persist it to the private HF
dataset `egoh33/app_data` as a single DuckDB container (`review_queue.duckdb`)
and restore it on boot.

The container is rebuilt from a Parquet export of the live tables rather than
copied from the open DB file: that gives a consistent snapshot (no WAL/lock
races) and writes it in the *runtime's own* DuckDB storage format, so the Space
(DuckDB 1.0.x) always reads back exactly what it wrote. See memory
`ops-duckdb-storage-format-mismatch`.

Cadence: the daily CI/CD cron (.github/workflows/snapshot.yml) wakes the Space
and calls POST /api/admin/snapshot, which extracts + uploads. A best-effort
snapshot also runs on graceful shutdown.

Safety: snapshot/restore only run on the Space (SPACE_ID set) or when forced, so
local dev never auto-pushes its review DB.

Env:
  RUNTIME_SNAPSHOT_REPO     dataset repo id        (default: egoh33/app_data)
  RUNTIME_SNAPSHOT_ENABLED  force on/off           (default: on iff running on a Space)
  APP_DATA_HF_TOKEN         dedicated WRITE token for the private dataset (preferred)
  HF_TOKEN / HUGGING_FACE_HUB_TOKEN   fallback token if APP_DATA_HF_TOKEN is unset
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

from loguru import logger

from api.config import config

REPO = os.getenv("RUNTIME_SNAPSHOT_REPO", "egoh33/app_data")
CONTAINER = "review_queue.duckdb"  # the DuckDB container file inside the dataset
# A freshly-created review DB is tiny; treat anything above this as "already has data".
_MIN_POPULATED_BYTES = 50_000


def _token() -> str | None:
    # Prefer a dedicated write-scoped token for app_data; fall back to the generic
    # HF token (which may be read-only / used only for the public corpus + git push).
    return (
        os.getenv("APP_DATA_HF_TOKEN")
        or os.getenv("HF_TOKEN")
        or os.getenv("HUGGING_FACE_HUB_TOKEN")
        or None
    )


def _on_space() -> bool:
    """True when running inside a HF Space (or explicitly forced)."""
    forced = os.getenv("RUNTIME_SNAPSHOT_ENABLED")
    if forced is not None:
        return forced.strip().lower() in ("1", "true", "yes", "on")
    return bool(os.getenv("SPACE_ID") or os.getenv("SPACE_HOST"))


def snapshot_enabled() -> bool:
    """Whether shutdown snapshots should run in this process."""
    return _on_space() and _token() is not None


_snap_lock = threading.Lock()
_last_snap_monotonic = 0.0
_snap_in_flight = False
# Coalesce write-triggered snapshots: at most one upload per this many seconds.
# Floored at 60s so a misconfigured env can't turn the throttle off and let
# sustained writes drive back-to-back whole-DB re-export+upload.
def _min_write_snapshot_interval_s() -> int:
    try:
        return max(60, int(os.getenv("RUNTIME_SNAPSHOT_MIN_INTERVAL_S", "300")))
    except (TypeError, ValueError):
        return 300


def maybe_snapshot_async(*, reason: str = "write") -> bool:
    """Fire-and-forget, throttled snapshot after a durable write.

    The daily cron + shutdown snapshot can lose everything written since the last
    snapshot if the Space hard-restarts (cpu-basic Spaces flap). For low-traffic,
    high-value data — e.g. the conjoint experiment responses — calling this right
    after a write captures it promptly while the Space is awake. Throttled so a
    burst of writes triggers at most one upload per RUNTIME_SNAPSHOT_MIN_INTERVAL_S
    (default 300s), with never more than one snapshot in flight.

    Returns True if a snapshot thread was started, else False (throttled/disabled).
    Never raises; a no-op off-Space so local dev never uploads.

    Note: the throttle window starts at snapshot *start*, so writes landing during
    an in-flight snapshot are captured by the next eligible snapshot (>= interval
    later) or the cron/shutdown path — this is best-effort durability, not a
    guarantee that every individual write is uploaded immediately.
    """
    if not snapshot_enabled():
        return False
    global _last_snap_monotonic, _snap_in_flight
    now = time.monotonic()
    with _snap_lock:
        if _snap_in_flight or (now - _last_snap_monotonic) < _min_write_snapshot_interval_s():
            return False
        _snap_in_flight = True
        _last_snap_monotonic = now

    def _run() -> None:
        global _snap_in_flight
        try:
            snapshot_review_db(reason=reason)
        finally:
            with _snap_lock:
                _snap_in_flight = False

    try:
        threading.Thread(target=_run, name="runtime-snapshot-write", daemon=True).start()
    except Exception as e:  # noqa: BLE001 — must never raise into the caller's request path
        with _snap_lock:
            _snap_in_flight = False  # release so future writes can retry
        logger.error("[snapshot] could not start write-triggered snapshot thread: {}", e)
        return False
    return True


def snapshot_review_db(*, reason: str = "periodic", force: bool = False) -> bool:
    """Extract every review table and upload them as a DuckDB container to the dataset.

    Best-effort: logs and returns False on any failure; never raises. Safe to call
    from a worker thread — it uses a fresh DuckDB cursor for the export so it does
    not contend with request-handler writes.

    `force=True` bypasses the on-Space guard (used by the admin/cron trigger, where
    the snapshot is explicitly requested) but still requires an HF token.
    """
    if not force and not _on_space():
        logger.info("[snapshot] not on a Space (and not forced) — skipping review-DB snapshot")
        return False
    token = _token()
    if not token:
        logger.info("[snapshot] no HF token — skipping review-DB snapshot")
        return False
    try:
        import duckdb
        from huggingface_hub import HfApi

        from api.db.database import db_manager

        # cursor() shares the database but is an independent connection, so the
        # read-only COPY does not clash with concurrent audit writes.
        cur = db_manager.get_review_connection().cursor()
        tables = [r[0] for r in cur.execute("SHOW TABLES").fetchall()]
        if not tables:
            logger.info("[snapshot] review DB has no tables — nothing to snapshot")
            return False

        with tempfile.TemporaryDirectory() as td:
            # 1) consistent Parquet export of each table from the live DB
            for t in tables:
                pq = Path(td) / f"{t}.parquet"
                cur.execute(f'COPY (SELECT * FROM "{t}") TO \'{pq.as_posix()}\' (FORMAT PARQUET)')
            # 2) rebuild a clean DuckDB container in the runtime's native format
            container = Path(td) / CONTAINER
            builder = duckdb.connect(str(container))
            try:
                for t in tables:
                    pq = Path(td) / f"{t}.parquet"
                    builder.execute(
                        f'CREATE TABLE "{t}" AS SELECT * FROM read_parquet(\'{pq.as_posix()}\')'
                    )
            finally:
                builder.close()
            # 3) upload the single container file to the private dataset
            HfApi(token=token).upload_file(
                path_or_fileobj=str(container),
                path_in_repo=CONTAINER,
                repo_id=REPO,
                repo_type="dataset",
                commit_message=f"runtime snapshot ({reason}): {len(tables)} tables",
            )
        logger.info(
            "[snapshot] uploaded {} table(s) as {}/{} (reason={})",
            len(tables), REPO, CONTAINER, reason,
        )
        return True
    except Exception as e:  # noqa: BLE001 — durability snapshot must never crash the app
        logger.error("[snapshot] review-DB snapshot failed (non-fatal): {}", e)
        return False


def restore_review_db() -> bool:
    """Restore the review DB from the dataset's DuckDB container on boot.

    Skips if the review DB is already populated (warm restart) so a stale snapshot
    never clobbers newer in-container data. Best-effort: never raises.
    """
    if not _on_space():
        logger.info("[restore] not on a Space (and not forced) — skipping review-DB restore")
        return False
    token = _token()
    if not token:
        logger.info("[restore] no HF token — skipping review-DB restore")
        return False

    db_path = config.REVIEW_DB_PATH
    if os.path.exists(db_path) and os.path.getsize(db_path) > _MIN_POPULATED_BYTES:
        logger.info(
            "[restore] review DB already populated at {} ({:.0f} KB) — skipping restore",
            db_path, os.path.getsize(db_path) / 1e3,
        )
        return False

    try:
        from huggingface_hub import hf_hub_download

        try:
            local = hf_hub_download(
                repo_id=REPO, filename=CONTAINER, repo_type="dataset", token=token,
            )
        except Exception as e:  # noqa: BLE001
            # "no container yet" (first run) is expected and not an error — match by
            # name to avoid the EntryNotFoundError import moving across hub versions.
            if e.__class__.__name__ in ("EntryNotFoundError", "RepositoryNotFoundError"):
                logger.info("[restore] no container {}/{} yet — starting fresh", REPO, CONTAINER)
                return False
            raise

        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        shutil.copyfile(local, db_path)
        logger.info(
            "[restore] restored review DB from {}/{} ({:.0f} KB)",
            REPO, CONTAINER, os.path.getsize(db_path) / 1e3,
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.error("[restore] review-DB restore failed (non-fatal): {}", e)
        return False


if __name__ == "__main__":
    # Entry used by the container boot step (scripts.restore_review_db).
    restore_review_db()
