# REVIEW: NL1 contracts (reviewer: Codex gpt-5.6-sol)

You are the independent REVIEWER after the checker approved round 11 (.agents/deepseek/VERDICT-nl1-round11.md).
Do NOT edit repo files. Do mutation proofs in /tmp copies (cp -r the repo to /tmp/nl1-review-*). Print your verdict to stdout
between ===VERDICT START=== and ===VERDICT END=== with "Status: APPROVED" or "Status: CHANGES_REQUESTED" and numbered findings
with file:line evidence, test counts, mutation results.

Scope: branch slice/nl-contracts vs origin/main (package analytics_nl/, tests/analytics_nl/, docs/NL1_PROPOSED_SERVING_VIEWS.md,
source_schemas_v1.yaml). Original plan/spec: .agents/requests/BUILD-nl1-contracts.md and BUILD-nl1-amendment-put-call.md.
Review for:
1. Contract security: can an LLM-produced intent smuggle free text, SQL, or unbounded values into any field? Try your own hostile
   payloads (unicode confusables, NFKC tricks, nested $ref fields, enum case tricks, oversized lists/dates).
2. Point-in-time: relative dates resolve against an as-of; no field allows future data; the 9 metrics map to proposed serving
   views that respect information_available_ts. Note the live finding: put_call_ratio source rows have mixed-case `right`
   (fixed in a separate lane) and implied_volatility (iv_atm) exists for only 12 of 19,390 rows (snapshot-only) — does NL1
   surface "insufficient data" honestly rather than returning a misleading answer?
3. Schema/model sync (export_schemas --check), tests meaningful (run 3 mutations of your own choosing).
Run: python3 -m pytest tests/analytics_nl -q ; python3 -m analytics_nl.export_schemas --check
