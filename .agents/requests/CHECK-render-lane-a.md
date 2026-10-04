# CHECK: Render lane A (DeepSeek)

Branch `slice/render-lane-a`. Spec: `.agents/requests/BUILD-render-lane-a.md`. Read-only; scratch work
goes in /tmp. Write `.agents/deepseek/VERDICT-render-lane-a.md` (===VERDICT START/END===, Status).

1. **`requirements-render.txt`.**
   - Are the pins mutually compatible, and installable for Python 3.12? Check pydantic 2.13.5 with
     fastapi 0.115.6.
   - Is anything `api.main` imports at startup missing? Claude verified `import api.main` in a clean
     uv venv from this file alone. Find runtime imports at request time that would fail.
2. **`render.yaml`.**
   - Matches §7 of `docs/RENDER_DEPLOY_PLAN.md`.
   - Has no secrets.
   - `$PORT` is bound.
   - `autoDeploy: false`.
   - Would the build fail if Node is missing from Render's Python build image? Flag it as a risk
     for the first deploy.
3. **`docs/DEPLOYMENT.md`.** Is the Render section accurate and consistent with the Blueprint?
4. **Tests.**
   - Do they verify behaviour, or just mirror the files?
   - Mutation check: add `langchain` to `requirements-render.txt` → a test fails; add a secret env
     var to `render.yaml` → a test fails.
   - No network access in the default test path, except the marked install test.

Run `python3 -m pytest -q -p no:cacheprovider tests/render`.
