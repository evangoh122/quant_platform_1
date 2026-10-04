# BUILD: CI/CD CodeRabbit findings (MiMo), branch ci/github-actions-dab

These are CodeRabbit findings on PR #18, which includes this branch. Claude verified them. Fix:

1. **Pin every third-party action to a full commit SHA**, with the tag in a comment, e.g.
   `uses: actions/checkout@<40-char sha> # v4.2.2`. This applies to all workflows in
   `.github/workflows/`. Add `persist-credentials: false` to every `actions/checkout` step.
   Look the SHAs up from the action repos' release tags. You may use `git ls-remote
   https://github.com/<owner>/<repo> refs/tags/<tag>`. For an annotated tag, use the peeled
   `^{}` commit. Write every SHA you used, and the command that produced it, in the verdict.
2. **`ci.yml` bundle validation runs without credentials.** Only run `databricks bundle validate`
   when the complete auth is present: host AND (client id with OIDC, or a token). Otherwise skip
   with a notice. Keep it from failing on forks.
3. **`cd.yml` doesn't restart the app.** After `bundle deploy`, add a separate step gated by a
   workflow_dispatch boolean input `start_app` (default false) that runs
   `databricks bundle run <app resource key> -t <target>`. Document it in `docs/CICD.md`. Jobs and
   pipelines must still never run from CD.
4. **`databricks.yml` prod schema isn't used.** Pass `${var.schema}` to the app (an env var in
   `resources/app.yml` / `app.yaml` config) and to the job tasks (a parameter). Make
   `pipelines/run_silver_gold.py` and `api/config.py` read the schema from that env var/arg, with the
   default unchanged (`evangoh_capstone`). Add a test that the env var overrides the default.

Not in scope: the Node 20 claim. CI currently passes with `@v4`. Pinning to the latest v4 SHA is fine.

Validate:
- `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase` passes.
- `python3 -c "import yaml,glob;[yaml.safe_load(open(f)) for f in glob.glob('.github/workflows/*.yml')]"` passes.

LF line endings only. Don't touch `.agents/dispatch.sh`. Commit. Write
`.agents/mimo/VERDICT-ci-coderabbit.md`.
