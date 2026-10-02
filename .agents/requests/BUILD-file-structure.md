# BUILD-REQUEST: file-structure

**Round:** 1
**Branch:** `refactor/file-structure` (you are in worktree `/home/jianj/code/qp1-struct`)
**Agent:** Codex — for this request you are the **BUILDER**, not the validator.
**Goal:** Fix the file structure of this project so the Databricks workspace
folder is coherent. Structure only — **no behaviour changes.**

---

## Why the structure is broken (root cause — read this first)

This repo was formed by merging two repos into one. `Rag_workbench` kept its
code under `api/services/` and `api/models/`. The merge **flattened** those to
`services/` and `services/models/` but **never updated the imports**.

Consequences, all verified:

- `tests/rag/*` still import `api.services.xbrl_relevance`, `api.services.verifier`,
  `api.services.sentiment`, `api.services.peer_comparison`, and
  `api.models.eval_types`. **No `api/` package exists**, so these fail at
  collection — a large share of the ~25 collection errors in this repo.
- `services/` is **orphaned**: `grep` finds **zero** `from services.*` importers.
- The rubric requires a backend `api/` package for the FastAPI routes
  (`GET /api/signals`, `POST /api/agent/chat`, …). There isn't one.

So the single highest-value fix is to **restore the `api/` package**. Done right
it fixes the broken imports *without editing a single test file*.

---

## Scope — in priority order

### 1. Restore the `api/` package (highest value)

- `services/` → `api/services/`
- `services/models/` → `api/models/`

Use `git mv` so history is preserved. After the move, the existing
`api.services.*` and `api.models.*` imports in `tests/rag/` must resolve
**with no edits to those test files**. Add `api/__init__.py`.

If anything imports the old `services.*` path after the move, leave a thin
backward-compatible shim at the old path rather than editing a forbidden file.
Verify with real commands, e.g.
`python3 -c "import api.services.verifier"`, and report the output.

### 2. Delete the junk notebook

`New Notebook 2026-09-05 22:26:32.py` — 1 line, 0 cells, spaces in the
filename. Delete it.

### 3. Create the missing layer packages

The Silver and Gold transformation layer **does not exist** — I verified that
every `saveAsTable` target in this repo is a `bronze_*` table, and all six
`silver_*` and all six `gold_*` Delta tables are **empty (0 rows)** while bronze
holds 232M rows. Another slice will implement the transforms; your job is only
to create the packages so there is an obvious home for them:

- `silver/__init__.py`
- `gold/__init__.py`
- `api/routes/__init__.py`

Each with a short module docstring stating what belongs there. **Do not
implement any transform logic.** Empty, documented packages only.

### 4. Decompose the monolithic notebooks — carefully

`00_project_setup.py` (3,524 lines, 18 cells) and `02_ingest_sec_edgar.py`
(3,669 lines, 9 cells) are **genuine Databricks notebooks** — first line
`# Databricks notebook source`, cells delimited by `# COMMAND ----`.

**Constraints:**
- Any file that stays a notebook MUST keep the `# Databricks notebook source`
  header and `# COMMAND ----` cell markers, or it breaks in the workspace.
- Extract reusable logic into plain importable modules; leave the notebook as a
  thin orchestrator that imports them.
- **Assess before splitting.** Per `MERGE_PLAN.md`, `00_project_setup.py` is a
  one-time scaffolding notebook that *writes out* `db/delta_adapter.py`, the
  ontology YAMLs and `app.yaml` and copies files between repos. Those outputs
  **already exist in the repo**, so much of that notebook is now dead
  scaffolding. Prefer moving it to `notebooks/archive/` with a note over
  lovingly refactoring obsolete code. Say what you concluded and why.
- If decomposing a notebook cannot be done safely without touching forbidden
  paths, **skip it and say so.** A partial, correct result beats a broken one.

### 5. Documentation tidy

- `MERGE_PLAN.md` is duplicated — identical copy sits in the parent `Capstone/`
  folder. Move this repo's copy to `docs/MERGE_PLAN.md`.
- Create `docs/` and put the architecture/planning docs there.
- Add `docs/STRUCTURE.md`: a short map of the final layout, one line per
  top-level package, stating what belongs in each.

---

## Forbidden paths — three other lanes are live in this repo right now

**Do not create, modify, move or delete anything under:**

- `db/`, `agent/` — Lane A (Lakebase + agent tools) has active changes
- `ml/`, `tests/ml/` — Lane B (ML ablation) has active changes
- `pipelines/`
- `tests/` — **including `tests/rag/`**. The whole point of §1 is that you fix
  the imports by moving source, not by editing tests.
- `conftest.py`, `pytest.ini`, `requirements.txt`, `requirements-dev.txt`,
  `README.md` — the F0 lane owns these
- `.agents/`

If a change you believe is correct requires touching a forbidden path, **stop,
do the rest, and write the need into your report.** Do not edit it.

---

## Acceptance criteria

1. `python3 -c "import api.services.verifier"` (and the other three
   `api.services.*` modules plus `api.models.eval_types`) succeed. Paste real
   output.
2. `python3 -m pytest tests/rag --co -q` collects **strictly more** tests than
   before your change. Record the before and after numbers honestly — if some
   still fail for unrelated reasons, list them rather than claiming success.
3. The junk notebook is gone.
4. `silver/`, `gold/`, `api/routes/` exist as documented empty packages.
5. Every remaining notebook still begins with `# Databricks notebook source`
   and retains its `# COMMAND ----` markers. Verify with grep and paste it.
6. No forbidden path appears in `git diff --name-only main..HEAD`. Check this
   yourself before finishing and paste the file list.
7. **No behaviour changes.** This is a move-and-document refactor. No logic edits.
8. Commits on `refactor/file-structure` only. **Never push. Never touch `main`.**

## Reporting

`.agents/` is read-only in your sandbox, so **do not try to write a verdict
file**. Instead print your complete report to stdout starting with the line
`===REPORT START===`, covering: what you moved, what you concluded about
`00_project_setup.py`, the before/after collection counts, the full changed-file
list, and anything you refused to do and why. Understate rather than overstate.
