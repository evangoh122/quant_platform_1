"""Contract tests for the P0 flat-file perps history design (docs-only).

The owner decision of 2026-10-22 replaced API forward capture with **flat-file
backfill**: Hyperliquid requester-pays S3 fills/asset contexts/funding events
(plus Binance Vision for the controls). These tests keep the plan, README,
schema doc and ontology from drifting back to the superseded
"1h/15m forward capture is time-critical" framing, and pin the safety rules the
P1 reader must implement (dry-run cost print, explicit ``--live``, credentials
by profile name only).

They are offline, stdlib + PyYAML only, and do not import the P1 module (it does
not exist in P0).
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "docs" / "data" / "PERPS_WEEKEND_PLAN.md"
README = ROOT / "README.md"
SCHEMAS = ROOT / "docs" / "DATA_SCHEMAS.md"
ONTOLOGY = ROOT / "ontology" / "business_terms.yaml"
ONTOLOGY_README = ROOT / "ontology" / "README.md"
FLAT_FILE_MODULE = ROOT / "scripts" / "perps" / "hl_flat_files.py"

DERIVATIVE_COLUMNS = (
    "instrument_type",
    "underlying_type",
    "underlying_symbol",
    "venue",
    "contract_symbol",
    "data_source",
)


def _plan() -> str:
    return PLAN.read_text(encoding="utf-8")


def test_plan_names_every_hyperliquid_flat_file_dataset():
    text = _plan()
    for prefix in (
        "node_fills_by_block",
        "node_fills",
        "node_trades",
        "s3://hyperliquid-archive/asset_ctxs/",
        "misc_events_by_block",
        "l2Book",
        "data.binance.vision",
    ):
        assert prefix in text, prefix


def test_plan_quotes_the_archive_caveats_and_marks_hip3_unverified():
    text = _plan()
    assert "no guarantee of timely updates and data may be missing" in text
    assert "HIP-3 coverage" in text
    assert "UNVERIFIED" in text
    assert "requester-pays" in text.lower()


def test_plan_has_the_p1_flat_file_ingestion_design():
    text = _plan()
    assert "P1 flat-file ingestion" in text
    assert "scripts/perps/hl_flat_files.py" in text
    assert "--dry-run" in text
    assert "Required to download" in text
    assert "Never implied by any other flag" in text
    assert "AWS_PROFILE" in text
    assert "ListObjectsV2" in text
    assert "no object downloads" in text
    assert "streaming" in text.lower()
    assert "no full-file loads" in text.lower()


def test_plan_requires_trade_time_bucketing_dedupe_and_append_only_corrections():
    text = _plan()
    assert "trade time in UTC" in text
    assert "floor(trade_ts / interval)" in text
    # Fill dedupe is by trade id because a trade may appear once per counterparty.
    assert "trade id" in text
    assert "tid" in text
    assert "counterparty" in text
    assert "fill_hash" in text
    assert "reconcile" in text.lower()
    assert "candleSnapshot" in text
    assert "append-only correction" in text
    assert "information_available_ts = max(bar_end_ts, availability of the archive object or" in text
    assert "No interpolation, no forward fill" in text


def test_bronze_targets_carry_the_derivative_column_set():
    sections = {}
    for part in _plan().split("\n#### ")[1:]:
        name = part.split("\n", 1)[0].strip().strip("`")
        sections[name] = part
    for table in ("bronze_perp_fills", "bronze_perp_candles", "bronze_perp_asset_ctxs"):
        assert table in sections, table
        body = sections[table]
        for column in DERIVATIVE_COLUMNS:
            assert column in body, (table, column)
        assert "perpetual_future" in body, table


def test_panel_keeps_the_api_only_lower_bound_and_states_the_upper_bound():
    text = _plan()
    assert "API-only lower bound" in text
    assert "1,538" in text
    assert "1,871" in text
    assert "upper bound" in text.lower()
    assert "49" in text


def test_no_forward_capture_p1_claim_survives_in_the_docs():
    plan = _plan()
    readme = README.read_text(encoding="utf-8")
    schemas = SCHEMAS.read_text(encoding="utf-8")
    for document in (plan, readme, schemas):
        assert "time-critical" not in document.lower()
    assert "No API forward-capture job exists" in plan
    assert "no api forward-capture job" in readme.lower()
    assert "not from an api forward-capture" in schemas.lower()


def test_ontology_has_the_flat_file_vocabulary():
    terms = yaml.safe_load(ONTOLOGY.read_text(encoding="utf-8"))["terms"]
    for name in (
        "flat_file_archive",
        "append_only_fill_bar",
        "requester_pays",
        "perpetual_future",
        "open_interest",
    ):
        assert name in terms, name
    assert "requester-pays" in terms["flat_file_archive"]["definition"].lower()
    assert "never the mark" in terms["append_only_fill_bar"]["critical_rule"].lower()


def test_late_fill_corrections_are_stamped_when_their_contents_become_observable():
    """A late-fill correction is not available at ``bar_end``.

    The bar end is the interval boundary; the correction's
    ``information_available_ts`` is when the correcting contents became
    observable (the latest arrival/ingest timestamp of the late fills). Stamping
    it at ``bar_end`` would let a point-in-time join use the correction before it
    existed. The same rule must be stated in DATA_SCHEMAS, the ontology README,
    the ``append_only_fill_bar`` term and the plan.
    """
    term = yaml.safe_load(ONTOLOGY.read_text(encoding="utf-8"))["terms"][
        "append_only_fill_bar"
    ]
    documents = {
        "docs/DATA_SCHEMAS.md": SCHEMAS.read_text(encoding="utf-8"),
        "ontology/README.md": ONTOLOGY_README.read_text(encoding="utf-8"),
        "ontology/business_terms.yaml:append_only_fill_bar": " ".join(
            [term["definition"], term["critical_rule"]]
        ),
        "docs/data/PERPS_WEEKEND_PLAN.md": PLAN.read_text(encoding="utf-8"),
    }
    for name, text in documents.items():
        normalised = re.sub(r"\s+", " ", text.replace("`", "")).lower()
        assert "append-only correction" in normalised, name
        assert "became observable" in normalised, name
        assert "arrival/ingest" in normalised, name
        assert "interval boundary" in normalised, name
        assert re.search(r"(not|never) bar_end", normalised), name
        # The superseded wording stamped every bar (corrections included) at
        # bar_end; it must not come back.
        assert (
            "the bar carries information_available_ts = bar_end_ts" not in normalised
        ), name
        # Superseded first-bar stampings must not survive anywhere (MiMo r12).
        for stale in (
            "bar_end_ts for a first bar",
            "equals bar close for a first bar",
            "first bar's information_available_ts = bar_end_ts",
            "first bar carries information_available_ts = bar_end_ts",
            "1h bar is available at its bar_end_ts",
        ):
            assert stale not in normalised, (name, stale)
        # A first (backfilled) bar is never usable before its source archive or
        # fills were observable (CodeRabbit on PR #80).
        assert re.search(
            r"first bar carries information_available_ts = max\(bar_end(_ts)?, availability of the archive object",
            normalised,
        ) or "first bar's information_available_ts = max(bar_end_ts, availability of the archive object" in normalised, name


def test_flat_file_reader_is_design_only_in_p0():
    # P1 adds scripts/perps/hl_flat_files.py; that round replaces this guard with
    # the reader's own dry-run/streaming tests instead of deleting the contract.
    assert not FLAT_FILE_MODULE.exists(), (
        "scripts/perps/hl_flat_files.py does not exist in P0: the P1 flat-file "
        "reader is design-only here (docs/data/PERPS_WEEKEND_PLAN.md §4.4)"
    )


def test_architecture_diagram_uses_the_first_bar_availability_rule():
    """The perps architecture diagram must not stamp Silver bars at bar_end alone
    (Codex Sol on PR #80): a backfilled bar is not usable before its source archive."""
    html = (ROOT / "docs" / "data" / "perps_architecture.html").read_text(encoding="utf-8")
    assert "info_available = bar_end_ts<" not in html
    assert "info_available = max(bar_end, source avail.)" in html
