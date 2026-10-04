# BUILD: corporate actions round 3 (MiMo)

> **IMPLEMENT NOW.** No confirmation questions. Commit when done. Flipping the one test named below
> is required; do not otherwise weaken tests.

Checker (`.agents/deepseek/VERDICT-corporate-actions-check2.md`): everything verified EXCEPT one
blocking issue. Do these together with the three dry-run follow-ups from
`.agents/requests/NOTES-claude-dryrun.md`:

1. **[Blocking] Unknown flags are silently accepted.**
   `notebooks/refresh_bronze_corporate_actions.py:~147` uses `parse_known_args`, and `allow_abbrev`
   is on. So `--mdoe write` runs dry-run, writes 0 rows and exits green.
   - Use `ArgumentParser(allow_abbrev=False).parse_args()`.
   - Flip `test_unknown_flag_does_not_raise` (`tests/bronze/test_corporate_actions.py:~553`) to
     expect `SystemExit`.
   - Add a test that `--mod write` (an abbreviation) is rejected.
   - In a Databricks notebook context with no CLI args, fall back to widgets. Detect this by "no
     argv flags", not by ignoring unknowns.
2. **Parse args BEFORE `SparkSession.builder.getOrCreate()`**, so `--help` and bad flags fail fast
   without Spark. Test: `--help` exits 0, and `--bogus` exits non-zero, without creating Spark (spy
   or patch the builder to raise if called).
3. **sys.path:** insert the repo root (`Path(__file__).resolve().parents[1]`) at the top, so running
   from `notebooks/` or as a Databricks job can import `etl`. Test it via a subprocess run from
   `notebooks/` with `--help`.
4. Replace `dt.datetime.utcnow()` with `dt.datetime.now(dt.timezone.utc)`.

Run `python3 -m pytest -q -p no:cacheprovider --ignore=tests/lakebase`, and the same with pyspark
hidden. LF line endings only. Don't touch `.agents/dispatch.sh`. Write
`.agents/mimo/VERDICT-corporate-actions-round3.md`.
