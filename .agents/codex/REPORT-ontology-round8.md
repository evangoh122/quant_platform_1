===REPORT START===
Status: COMPLETE

Implemented all round-8 ontology findings and added the requested regression tests and SEC CIK status snapshot.

Validation:

- `python3 -m pytest tests/test_ontology.py -q`
- Result: `34 passed, 35 skipped`
- M-C, M-D, and M-E mutations each failed as required.
- `git diff --check` passed.
- Corporate-actions section was untouched.
- No commit or push performed.
===REPORT END===
