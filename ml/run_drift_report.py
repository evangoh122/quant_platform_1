"""CLI: run the Evidently drift report for the baseline-signal lane.

Pipeline demonstration; baseline signals, no edge claimed.

Offline by default: the reference/current windows come from the deterministic
synthetic frame in ``ml/synthetic_data.py`` (the same path the ML tests use), so
the runner needs neither Spark/Databricks nor network access.  Evidently is an
optional dev dependency (``requirements-dev.txt``); ``--help`` works without it.

Writes (gitignored, see ``ml/results/.gitignore``):
  * ``ml/results/drift_report.html``  — Evidently HTML report;
  * ``ml/results/drift_summary.json`` — per-feature drift flags + shares.

Examples:
    python ml/run_drift_report.py --help
    python ml/run_drift_report.py --output-dir ml/results
    python ml/run_drift_report.py --reference ref.csv --current cur.csv
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Allow `python ml/run_drift_report.py` from any cwd (same bootstrap as ml/run_ablation.py).
_p = globals().get("__file__") or sys.argv[0]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(_p))))

from ml.monitoring import (  # noqa: E402
    DEFAULT_DRIFT_SHARE_THRESHOLD,
    DEFAULT_STATTEST_THRESHOLD,
    DRIFT_LABEL,
    load_feature_frame,
    run_drift_report,
    split_windows,
)

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "results"


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the Evidently drift report (feature drift + prediction drift) "
            "for the baseline-signal lane.\n" + DRIFT_LABEL
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--source",
        default="synthetic",
        help='Feature-frame source: "synthetic" (offline default) or a .csv/.parquet snapshot path.',
    )
    parser.add_argument(
        "--reference",
        default=None,
        help="Explicit reference window (.csv/.parquet); must be given together with --current.",
    )
    parser.add_argument(
        "--current",
        default=None,
        help="Explicit current window (.csv/.parquet); must be given together with --reference.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for drift_report.html + drift_summary.json (default: ml/results).",
    )
    parser.add_argument("--name", default="drift", help="Artifact name prefix (default: drift).")
    parser.add_argument("--seed", type=int, default=42, help="Seed for synthetic data and the baseline model.")
    parser.add_argument("--n-symbols", type=int, default=18, help="Synthetic source only: symbols in the frame.")
    parser.add_argument("--n-bars", type=int, default=400, help="Synthetic source only: bars per symbol.")
    parser.add_argument(
        "--label-method",
        choices=["fixed", "triple_barrier"],
        default="fixed",
        help="Synthetic source only: labelling scheme for the frame.",
    )
    parser.add_argument(
        "--reference-frac",
        type=float,
        default=0.6,
        help="Share of timestamps used as the reference window when one frame is split (default: 0.6).",
    )
    parser.add_argument(
        "--drift-share-threshold",
        type=float,
        default=DEFAULT_DRIFT_SHARE_THRESHOLD,
        help="dataset_drift fires when share_of_drifted_features >= this value (default: 0.5).",
    )
    parser.add_argument(
        "--stattest-threshold",
        type=float,
        default=DEFAULT_STATTEST_THRESHOLD,
        help="Per-feature statistical-test threshold handed to Evidently (default: 0.05).",
    )
    args = parser.parse_args(argv)

    if (args.reference is None) != (args.current is None):
        parser.error("--reference and --current must be given together")

    if args.reference is not None:
        reference = load_feature_frame(args.reference)
        current = load_feature_frame(args.current)
        source = f"explicit windows: {args.reference} + {args.current}"
    else:
        frame = load_feature_frame(
            args.source,
            seed=args.seed,
            n_symbols=args.n_symbols,
            n_bars=args.n_bars,
            label_method=args.label_method,
        )
        reference, current = split_windows(frame, reference_frac=args.reference_frac)
        source = f"{args.source} window split (reference_frac={args.reference_frac})"

    drift = run_drift_report(
        reference,
        current,
        drift_share_threshold=args.drift_share_threshold,
        stattest_threshold=args.stattest_threshold,
        seed=args.seed,
        source=source,
    )
    paths = drift.write(args.output_dir, name=args.name)

    print(json.dumps(drift.summary, indent=2))
    print(DRIFT_LABEL)
    print(f"Wrote {paths['html']}")
    print(f"Wrote {paths['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
