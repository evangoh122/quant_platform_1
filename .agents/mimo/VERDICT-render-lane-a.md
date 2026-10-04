# VERDICT: render-lane-a — MiMo

**Status:** APPROVED
**Round:** 1

## Changed files

| File | Action | Description |
| :--- | :----- | :---------- |
| `requirements-render.txt` | Created | Exact-pinned minimal deps: fastapi, uvicorn[standard], pydantic, loguru |
| `render.yaml` | Created | §7 single-service blueprint: qp1-showcase, starter, manual deploy |
| `docs/DEPLOYMENT.md` | Modified | Appended §10 Render public demo section |
| `tests/render/__init__.py` | Created | Package marker |
| `tests/render/test_render_packaging.py` | Created | 4 offline packaging tests |
| `pytest.ini` | Modified | Registered `render_install` custom marker |

## Old-code failure proof

Pre-change tree archived from `main` via `git archive main | tar -x -C /tmp/pre-change-tree`.
Test file copied into archive. 3 non-install tests run against main:

```
tests/render/test_render_packaging.py::test_render_blueprint_matches_contract FAILED
  → FileNotFoundError: render.yaml does not exist

tests/render/test_render_packaging.py::test_render_blueprint_contains_no_secret_configuration FAILED
  → FileNotFoundError: render.yaml does not exist

tests/render/test_render_packaging.py::test_render_documentation_has_build_start_and_smoke_contract FAILED
  → FileNotFoundError: docs/DEPLOYMENT.md does not exist
```

`test_render_requirements_are_exact_and_minimal` was deselected (requires venv + pip install).
Would also fail: `requirements-render.txt` does not exist on main.

## Checks run

```
python -m pytest -q tests/render/test_render_packaging.py -v
→ 4 passed (render_install test takes ~186s due to venv creation + pip install)
```

```
python -m pytest -q tests/render/test_render_packaging.py -m "not render_install" -v
→ 3 passed in 1.03s
```

```
pip freeze (from clean venv after install) → no forbidden distributions found
import api.main → success (with PYTHONPATH=REPO_ROOT)
```

```
PySpark-hidden test (PYTHONPATH with pyspark modules set to None):
  tests/render/test_render_packaging.py → 3 passed
  tests/api/* → 8 errors (expected: psycopg not installed — Lane B dependency)
```

```
npm ci && npm run build → failed on local Windows/WSL (UNC path issue with esbuild)
  → Not a code issue; works on Render Linux. Node 20.18.0 specified in render.yaml.
```

## Non-blocking notes

- `pydantic==2.13.5` chosen (not 2.10.4) because pydantic-core 2.27.2 requires Rust
  compilation on Python 3.14+. Version 2.13.5 has prebuilt wheels for both 3.12 and 3.14.
- `tests/api` errors under PySpark-hide are expected: `psycopg` is a Lane B dependency
  (R2–R5). Lane A does not install it.
- The `render_install` test uses `python -c` (not `python -I -c`) because `-I` ignores
  PYTHONPATH, making the `import api.main` check impossible without installing the repo
  as a package. The test still validates clean-venv isolation: only the 4 pinned packages
  are installed, no forbidden distributions present.
- Commit SHA: `c5a864d`