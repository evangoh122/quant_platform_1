# BUILD-REQUEST: strategy-residual-reversion — ROUND 2

**Branch:** `slice/strategy-residual-reversion` · **Builder:** DeepSeek · **Validators:** Claude, then Codex
Read `.agents/codex/VERDICT-strategy-residual-reversion.md` (item A). Codex confirmed the
regression window `[t-window, t-1]`, the execution lag, train-only parameter selection with
purge/embargo, honest trial count, gross/net/2× reporting, and short-only borrow. Keep those.

## Four fixes

1. **Universe look-ahead** (`gold/06_gold_tradable_universe.sql:36, 59-62`). Build candidates from
   a **market calendar × symbols** grid, not from each symbol's own bars (today membership on `t`
   requires knowing the symbol traded on `t`). Recency = traded on each of the **last 5 market
   sessions strictly before `t`**, not the symbol's last 5 observations. All inputs strictly
   before `t`. Rebuild `gold_tradable_universe`; paste size per date (min/median/max) before/after.

2. **Industry factors depend on the full-period symbol set**
   (`strategies/run_residual_reversion.py:78,142`, `strategies/residual_reversion.py:57,73`).
   Missing returns must stay **NaN**, never 0. Industry factor on day `t` = mean over symbols that
   are **eligible on `t`** (in that day's universe, with a valid return), excluding the stock
   itself, with a **date-specific** member count. Test: appending a symbol that only exists after
   date `d` leaves every industry factor and residual before `d` unchanged.

3. **ADV cap must constrain execution** (`strategies/backtest.py:138,151,260`). Apply the cap to
   the actual executed weight change; carry the capped position forward; compute P&L and borrow
   on the capped positions. Zero-ADV names cannot be traded. Test: an order over the cap yields a
   capped position and P&L on that capped size.

4. **Caveat the breadth-gated result.** In `strategies/results/residual_reversion_r2.md` state
   plainly that the gated comparison is an in-sample/full-period exploratory ablation, report its
   2×-cost result, note DSR, and say it is **not evidence of an edge**.

## Then
Re-run end to end and write `strategies/results/residual_reversion_r2.md` (keep r1 for
comparison) with a short "what changed vs r1" table. Report honestly whatever the numbers are.

Also: write files with **LF line endings** (not CRLF).

Do not modify `ml/`, existing `gold/0[1-5]*` transforms, `agent/`, `db/`, `api/`, `frontend/`,
`conftest.py`, `pytest.ini`, `.agents/dispatch.sh`. **Commit your work.**
Write `.agents/deepseek/VERDICT-strategy-residual-reversion-round2.md`.
