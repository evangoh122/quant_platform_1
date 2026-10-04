# VERDICT: rag-eval-harness-round8 — MiMo
**Status:** APPROVED
**Round:** 8

## Blocking findings
- None. All blocking issues from round 7 have been resolved.

## Non-blocking notes
- 2 pre-existing test failures in `test_rag_eval_retrieval.py` (dense/hybrid_rerank modes try to load HuggingFace models, blocked by network guard). Not related to round 8 changes.
- AF_UNIX tests skipped on Windows (no AF_UNIX support). Guard correctly handles this with `hasattr` check.

## Checks run
- `python -m pytest tests/rag/test_network_guard.py -v` → 9 passed, 2 skipped (AF_UNIX on Windows)
- `python -m pytest tests/rag/test_rag_eval_report.py -v` → 25 passed
- `python -m pytest tests/rag/test_rag_eval_round5.py -q` → 4 passed
- `python -m pytest tests/rag/test_rag_eval_corpus.py -q` → passed
- `python -m pytest tests/rag/test_rag_eval_metrics.py -q` → passed
- `python -m pytest tests/rag/test_network_guard.py tests/rag/test_rag_eval_report.py tests/rag/test_rag_eval_round5.py tests/rag/test_rag_eval_corpus.py tests/rag/test_rag_eval_metrics.py -q` → 69 passed, 2 skipped
- Mutation proof script `tests/rag/test_guard_mutation_proofs.py` → both mutations confirmed

## Changes made

### 1. Fixed network guard address unpack bug
**File:** `tests/rag/conftest.py:112-148`
- `_fail_socket_connect` and `_fail_socket_connect_ex` now use `self.family` to determine address format
- AF_INET: `(host, port)` — AF_INET6: `(host, port, flow, scope)` — AF_UNIX: `str/bytes` path
- AF_UNIX sockets always allowed (local IPC, no network)
- Added `_extract_host_port` helper for family-aware address parsing
- Added `_has_af_unix` guard for Windows compatibility

### 2. Added network guard tests
**File:** `tests/rag/test_network_guard.py` (new)
- `TestGuardBlocksOutbound`: 4 tests for `create_connection`, `socket.connect`, `connect_ex`, `getaddrinfo`
- `TestGuardAllowsLoopback`: 5 tests for 127.0.0.1, localhost, ::1, `getaddrinfo(None, ...)`
- `TestGuardAllowsUnixSockets`: 2 tests for `socketpair` and AF_UNIX connect (skipped on Windows)

### 3. Added mutation proof script
**File:** `tests/rag/test_guard_mutation_proofs.py` (new)
- Mutation 1: Remove connect patch → outbound test fails (guard not applied)
- Mutation 2: Reintroduce `address[0]` unpack → loopback test fails (ValueError)
- Both mutations confirmed with return code 1

### 4. Implemented recursive path redaction
**File:** `evals/rag_eval/report.py:39-83`
- `_redact_value`: handles Path, str, os.PathLike objects
- `_redact_recursive`: recurses into list/tuple/set/dict structures
- `_is_absolute_path`: cross-platform detection (Unix `/` and Windows `C:\`)
- `_path_basename`: handles mixed path separators
- Dict keys also redacted if str/PathLike

**File:** `tests/rag/test_rag_eval_report.py:231-328`
- 8 new tests for recursive redaction: list, tuple, set, dict, nested, deeply nested, Path objects, relative paths

### 5. Added CLI end-to-end report test
**File:** `tests/rag/test_rag_eval_report.py:331-375`
- Drives `cli.main` with real absolute Path args (offline adapter, tmp_path output)
- Asserts JSON and Markdown reports contain no `/home`, no `str(tmp_path)`, no `PosixPath`

### 6. Removed unused fixtures
**File:** `tests/rag/conftest.py`
- Deleted `cached_offline_adapter` fixture (defined but never used)
- Deleted `fake_reranker` fixture (defined but never used)

### 7. Updated getaddrinfo guard for passive calls
**File:** `tests/rag/conftest.py:147-153`
- `getaddrinfo(None, ...)` now allowed (passive/bind calls)
- `getaddrinfo` for loopback hosts allowed