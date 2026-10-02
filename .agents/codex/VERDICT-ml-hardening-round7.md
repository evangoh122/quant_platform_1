# VERDICT: ml-hardening round 7 — Codex
APPROVED

No blocking findings.

- HEAD suite: `37 passed` using the requested command.
- Historical reproduction at `147c696`: all three tests failed with the intended assertions:
  - Current-bar beta leakage: [test_hardening.py:411](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:411)
  - Sparse feature misclassified as market-wide: [test_hardening.py:457](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:457)
  - Fold-0 predictions affected by future data: [test_hardening.py:555](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:555)
- The tests are robust:
  - Beta perturbation is deterministic, isolated to one generated return, and produced a large historical difference (`0.656` versus `18.280`), while also checking propagation at `t+1`: [test_hardening.py:342](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:342), [test_hardening.py:415](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:415).
  - Sparse coverage is deterministic and deliberately exceeds the detector threshold: 23/25 timestamps are all-NaN, while observed timestamps vary cross-sectionally: [test_hardening.py:432](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:432).
  - Fold-local testing uses deterministic constructed data and changes only rows strictly after fold 0 validation: [test_hardening.py:518](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:518), [test_hardening.py:527](/home/jianj/code/qp1-ml/tests/ml/test_hardening.py:527).
- `git diff 3a80765..HEAD -- ml` contains only the two approved cleanups:
  - Corrected warning text: [features.py:562](/home/jianj/code/qp1-ml/ml/features.py:562)
  - Removed unused `X_full`; the surrounding fold-local implementation is unchanged: [train.py:278](/home/jianj/code/qp1-ml/ml/train.py:278)
- CodeRabbit was triggered previously, but its review attempt was rate-limited; it produced no findings.
- Worktree was not modified.
