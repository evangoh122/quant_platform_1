# BUILD — Render lane C (R5 + R6), gated on Lane B

## Gate, scope, and ownership

Do not start until Lane B is merged and its DeepSeek verdict is APPROVED. Lane C may assume exactly:
`api.demo.is_public_demo() -> bool` and
`api.deps.read_delta(fn, *, snapshot_key: str | None = None) -> (rows, state, detail)`, where demo
mode lazily calls `api.demo_data.read_snapshot(snapshot_key)` without executing `fn`.

Lane C owns new `api/demo_data.py`, `scripts/export_demo_data.py`, committed `demo_data/*.json`,
the read-only route modules `api/routes/signals.py`, `api/routes/market.py`, and
`api/routes/analytics.py`, plus new `tests/api/test_demo_snapshots.py` and
`tests/test_export_demo_data.py`. It must not edit `api/deps.py`, `api/main.py`, `api/demo.py`,
`agent/`, or Lane A/B files/tests. Section 7 at `docs/RENDER_DEPLOY_PLAN.md:260-364` is authoritative.

## Numbered changes

1. Add `api/demo_data.py` with `SNAPSHOT_DIR` defaulting to repository `demo_data/`, immutable
   `SNAPSHOT_SCHEMAS`, and `read_snapshot(snapshot_key: str | None) -> tuple[list[dict], str, str]`.
   Permit only hard-coded keys `signals`, `market_ohlcv`, `market_options`, and the four analytics
   sections (`analytics_model_performance`, `analytics_agent_activity`, `analytics_latency`,
   `analytics_stream_freshness`) used by API rows. Resolve keys to fixed filenames—never accept a
   path. Validate UTF-8 JSON, top-level object metadata (`schema_version`, `generated_at`, `data`),
   exact allowed row fields/types, ISO timestamps, maximum rows, maximum file bytes, and optional
   symbol equality/filter metadata. Return `(rows, "fresh", "N rows")`, `([], "empty", "0 rows")`,
   or `([], "unavailable", sanitized_reason)`; missing, corrupt, traversal-like, oversized, or
   schema-invalid input never raises and never reveals filesystem paths or raw content. Cache only
   by `(resolved fixed file, mtime_ns, size)` so fixture replacement invalidates safely.
2. At `api/routes/signals.py:19-53`, cap `limit` at 100 and call
   `read_delta(_read, snapshot_key="signals")`; apply requested normalized symbol and limit again
   after snapshot loading so fixtures cannot bypass request bounds. At `api/routes/market.py:25-80`,
   bound the accepted date window and result rows, pass keys `market_ohlcv` and `market_options`,
   and filter returned rows to the normalized path symbol/time window. At
   `api/routes/analytics.py:25-44`, replace demo placeholder generation with per-section snapshot
   calls using the four exact keys while preserving response schemas; outside demo retain current
   behavior. These routes remain anonymous through Lane B's fixed demo viewer and must never import
   Spark/Lakebase in demo.
3. Add reviewed fixtures under `demo_data/`: `signals.json`, `market_ohlcv.json`,
   `market_options.json`, `analytics_model_performance.json`, `analytics_agent_activity.json`,
   `analytics_latency.json`, `analytics_stream_freshness.json`, `results.json`, `freshness.json`,
   `ablation.json`, and `rag_samples.json`. Every file uses a versioned envelope with generation and
   provenance metadata. Keep data small and deterministic. Allowlisted content only: no emails,
   user/account/order/approval/position identifiers, prompts, credentials, hostnames, or unrestricted
   filing text. `results.json` must state exactly `conclusion: "no demonstrated edge"` and numeric
   `deflated_sharpe_ratio: 0`. `ablation.json` must carry an unmistakable `synthetic: true` and
   `evidence_class: "pipeline validation only"`. Each RAG sample has reviewed question, answer,
   citations/source IDs, `as_of`, snapshot generation time, and later-events-excluded note.
4. Add executable-owner CLI `scripts/export_demo_data.py` with `main(argv=None) -> int`, explicit
   `EXPORT_SCHEMAS`, per-artifact column allowlists and row caps, and pure functions
   `validate_export_bundle(bundle)`, `scan_for_sensitive_data(bundle)`, and
   `write_bundle_atomically(bundle, output_dir)`. It may read owner-supplied local JSON inputs but
   must not embed credentials, contact live services, import PySpark at module load, or infer columns.
   Reject unknown/missing fields, nested extras, cap violations, emails, credential/token patterns,
   order/account/approval/position IDs, absolute paths, and secret-like values. Enforce the exact r4
   conclusion/DSR and synthetic ablation labels. Validate the complete bundle before writing to a
   temporary sibling directory; atomically replace individual files only after validation, leave the
   previous good bundle on failure, emit deterministic sorted JSON with LF newline, and print only
   filenames/counts/checksums (never row content). `--check demo_data` validates committed fixtures
   without rewriting them.
5. Add 6 test functions to `tests/api/test_demo_snapshots.py`: all registered demo GET routes return
   schema-valid fixture data with PySpark hidden; live reader callbacks are never invoked; symbol,
   time, and row bounds hold; missing fixture degrades to unavailable; corrupt/schema-invalid JSON
   degrades to unavailable; traversal/oversize/cache-replacement behavior is fail-closed. Add 6 test
   functions to `tests/test_export_demo_data.py`: valid deterministic bundle; disallowed field;
   row-cap violation; parameterized sensitive email/order/secret scan; mandatory negative r4 result
   and DSR zero; mandatory synthetic ablation plus atomic no-partial-write. Count: **12 test
   functions**.

## Tests must fail on the current code

Use `git archive HEAD` to create a clean `/tmp` pre-change copy, copy only the two new Lane C test
files into it, and run them with Lane B present (the gate means HEAD must include B). They fail because
`api.demo_data`, the exporter, fixtures, snapshot keys/filtering, and validations do not exist. For
each security validation, also demonstrate mutation against a second `/tmp` copy of a valid bundle
(unknown field, email/order ID/secret, corrupt JSON, false synthetic label, nonzero DSR) and show the
specific test turns red. Never alter committed fixtures for failure proof.

## Acceptance commands

```bash
PUBLIC_DEMO=1 python -m pytest -q tests/api/test_demo_snapshots.py tests/test_export_demo_data.py
python scripts/export_demo_data.py --check demo_data
python -m pytest -q tests/api
```

Run the relevant suite with PySpark hidden using these exact four `sys.modules` assignments:

```bash
hide="$(mktemp -d)"; printf '%s\n' 'import sys' 'for m in ("pyspark", "pyspark.sql", "pyspark.sql.functions", "pyspark.sql.types"):' '    sys.modules[m] = None' > "$hide/sitecustomize.py"
PYTHONPATH="$hide${PYTHONPATH:+:$PYTHONPATH}" PUBLIC_DEMO=1 python -m pytest -q tests/api/test_public_demo_security.py tests/api/test_demo_snapshots.py tests/test_export_demo_data.py
```

Also run an empty-secret demo smoke pass over `/api/health`, `/api/signals`, an allowlisted
`/api/market/{symbol}`, and `/api/analytics`; all return 200/well-formed envelopes, and inspection of
`sys.modules` plus mocks proves no PySpark, Lakebase, Databricks CLI, or broker access. Run a recursive
sensitive-data scan over `demo_data/` and verify exporter output is byte-for-byte deterministic.

## DeepSeek must check

- The B interface is consumed exactly; C does not reopen `deps.py`/`main.py` or create lane overlap.
- Snapshot keys map to fixed paths; traversal, symlink escape, TOCTOU/cache staleness, oversized
  input, invalid types/timestamps, and exception-detail leakage fail closed.
- Routes reapply symbol/date/row bounds after loading trusted-looking fixtures and never evaluate
  live callbacks in demo.
- Export allowlists are per artifact and recursively reject extras/sensitive identifiers; scans avoid
  both obvious bypasses and logging sensitive values.
- Atomic writing preserves the last good bundle on every validation/write failure.
- Scientific honesty is machine-enforced: r4 says no demonstrated edge with DSR numeric zero, and
  ablation is explicitly synthetic pipeline validation; RAG records contain `as_of` and citations.
- Committed fixtures contain no identity, operational trading, raw prompt, credential, or proprietary
  text fields and are small enough for public source control.

## Delivery constraints

No secrets in any file. Use LF line endings. Do not touch `.agents/dispatch.sh`. Do not edit files
outside this lane's ownership. Commit the lane. Write `.agents/mimo/VERDICT-render-lane-c.md` with
changed files, commands/results, old-code and mutation failure proof, and commit SHA.
