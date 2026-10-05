# CHECK: NL1 round 13 (checker: DeepSeek)

Read-only for source. Mutation proofs in /tmp copies (cp -r to /tmp/nl1r13-mut-*). Write .agents/deepseek/VERDICT-nl1-round13.md between
===VERDICT START=== / ===VERDICT END===, "Status: APPROVED" or "Status: CHANGES_REQUESTED", findings with file:line, counts, mutation results.
Build request: .agents/requests/BUILD-nl1-round13.md (from your round-12 verdict .agents/deepseek/VERDICT-nl1-round12.md). Commits: since the
"NL1 round 13 request" commit.
Re-run YOUR OWN round-12 mutations exactly:
1. serve_options_metrics_v1: remove the as_of_filtered WHERE and add `AND information_available_ts <= :as_of` to the final `WHERE rn = 1` →
   the PIT contract test must now FAIL. Repeat on one other view.
2. Rename close_price → close_price_bogus in price.trend output_fields → the registry/view column test must FAIL; and the extractor returns a
   non-empty, correct column set for every view (print them); an empty extraction fails the test.
3. CoverageStatus bound to the aggregate status field; agg_value nullable only when INSUFFICIENT_DATA (model validator) — mutation: allow null
   with status ok → FAILS.
4. GREATEST(1 + return_1d, 1e-10) guard present in relative-performance CTEs. Note whether clamping a ≤−100% day silently hides bad data
   (should it be excluded/flagged instead?) — non-blocking opinion.
5. No tests deleted/weakened. Schemas in sync.
Run: python3 -m pytest tests/analytics_nl -q; pyspark hidden PYTHONPATH=/tmp/claude-1000/-home-jianj/c73bcf93-61a0-4171-8f41-3debd575cea3/scratchpad/nps; python3 -m analytics_nl.export_schemas --check.
