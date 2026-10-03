# BUILD: RAG golden set round 2, question QUALITY (MiMo)

Claude's review: v1 passes the structural validator, but the items are templated and the gold
answers are often boilerplate, so retrieval scored against them would be meaningless. Examples:
- rag-v1-033 LRCX risk_factor: "What key risk factor does LRCX disclose related to its business
  operations?" → "Item 1A and elsewhere in this report and other documents we file from…"
  (boilerplate, not a fact);
- rag-v1-073 TER: same template, same boilerplate;
- rag-v1-018 AVGO: "What market risk sensitivity does AVGO disclose…?" → "56%" (no
  metric/period/unit context);
- rag-v1-009 AMAT: "How do AMAT's item7 mda disclosures compare…?" (uses the internal section ID,
  and has no specific fact).

## Quality rules (each enforced in `validate.py` unless marked as a reviewer check)
1. **Specific facts only.** `gold_answer` must be a concrete fact:
   - a number with unit AND period (e.g. "$12.3 billion revenue in fiscal Q2 2026");
   - a named entity (customer, product, facility, competitor, regulation);
   - or a dated event.

   Reject these answer fragments:
   - Item references ("Item 1A", "Part I", "Item 7");
   - forward-looking boilerplate ("forward-looking statements", "risks and uncertainties",
     "other documents we file");
   - answers under 3 tokens without a unit.

   Keep a deny-list in `validate.py`.
2. **Distinctive.** The normalised `gold_answer` (or its key number) appears in at most 3 chunks of
   that ticker's corpus. Compute this from `sec_corpus.jsonl`. That makes the gold chunk(s) genuinely
   identifiable.
3. **No templates.**
   - After removing ticker/company names, no two questions share > 0.6 token Jaccard.
   - No question may contain an internal section id (`item7_mda` etc.).
   - Questions must read like an analyst's question, naming the metric and period, e.g. "What was
     NVDA's data center revenue in the quarter ended July 2025?", or "Which customer accounted for
     more than 10% of AMAT's revenue in fiscal 2025?".
4. **Evidence span.** `notes` must contain the exact quoted evidence sentence. `validate.py` checks
   that the sentence is a substring of the gold chunk text, and that `gold_answer` (or its number)
   is inside that sentence.
5. **Point-in-time traps** must name a fact that CHANGES between filings (e.g. a quarterly revenue
   figure).
   - `as_of` falls between the older and newer filing.
   - Gold = the OLDER filing's value, with both chunk ids recorded: the allowed one and the
     forbidden newer one.
   - The validator checks that the allowed chunk was accepted ≤ as_of < the forbidden chunk.
6. **Unanswerable** questions must be plausible and specific (e.g. a metric that company doesn't
   report). The validator checks that no chunk of that ticker contains the key term.
7. **Coverage stays:** about 80 items, all 16 tickers, the same type mix. At least 30 items must
   include a number with unit and period.

## Process
- Regenerate `golden_v2.jsonl`. Keep v1 for history, marked deprecated.
- Write each question by reading the chunk, not from a template.
- Update `verify_report.md` with one line per item, citing the quoted evidence.
- Tests:
  - the new validator rules reject the v1 examples above (prove it);
  - v2 passes;
  - `tests` stay green, ignoring `tests/lakebase`.
- LF line endings. Don't touch `.agents/dispatch.sh`. Leave no scratch files. Commit with a
  descriptive message. Write `.agents/mimo/VERDICT-rag-golden-set-round2.md`.
