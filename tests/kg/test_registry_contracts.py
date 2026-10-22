"""Registry contracts: join matrix (S8 / R2-3) and edges (S12 / S14).

Anchored to the SQL that stores each availability column, so the registry
cannot drift into re-deriving what the warehouse already stores.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from config import data_sources
from sec_kg.contracts import instruments, publication, registry

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════
# S8 / R2-3 — business time, stored availability, cardinality
# ═══════════════════════════════════════════════════════════════════════════════

def test_join_registry_business_time_availability_and_cardinality():
    tables = registry.table_names()
    assert "gold_ohlcv_features" in tables
    for table in tables:
        contract = registry.get_contract(table)
        assert contract.business_time
        assert contract.availability
        assert contract.grain
        assert contract.cardinality in registry.CARDINALITIES
        assert contract.namespace in registry.NAMESPACES
        # Every table declares the provider(s) whose rows it carries.
        assert contract.data_sources, table
        assert set(contract.data_sources) <= data_sources.DATA_SOURCES, table
        # Every stored availability column must be anchored by evidence in the
        # SQL that produces it — no invented columns.
        if contract.availability_kind == registry.AVAILABILITY_VIA_JOIN:
            assert contract.availability_evidence is None, table
        elif contract.table.startswith(("gold_", "silver_")):
            assert contract.stored_availability, table
            assert contract.availability_evidence, table
        if contract.stored_availability and contract.availability_evidence:
            path = os.path.join(REPO_ROOT, contract.availability_evidence)
            with open(path, "r", encoding="utf-8") as handle:
                sql = handle.read()
            assert contract.availability in sql, (
                f"{table}: {contract.availability!r} is not stored by "
                f"{contract.availability_evidence}"
            )

    # OHLCV uses its stored information_available_ts, not feature_ts.
    ohlcv = registry.get_contract("gold_ohlcv_features")
    assert ohlcv.availability == "information_available_ts"
    assert ohlcv.availability_kind == registry.AVAILABILITY_STORED
    assert registry.business_time_column("gold_ohlcv_features") == "feature_ts"
    assert ohlcv.availability != ohlcv.business_time
    assert (
        registry.as_of_predicate("gold_ohlcv_features", "query_time")
        == "information_available_ts <= query_time"
    )

    # PIT eligibility is availability-based, and unknown availability is never
    # eligible.
    assert registry.is_available(
        "gold_ohlcv_features", dt(2024, 1, 2, 14, 31), dt(2024, 1, 2, 14, 31)
    )
    assert not registry.is_available(
        "gold_ohlcv_features", dt(2024, 1, 2, 14, 31), dt(2024, 1, 2, 14, 30)
    )
    assert not registry.is_available("gold_ohlcv_features", None, dt(2025, 1, 1))

    # A different business-time column per table, as declared.
    assert registry.business_time_column("gold_tradable_universe") == "trade_date"
    assert registry.availability_column("gold_tradable_universe") == (
        "information_available_ts"
    )
    assert registry.business_time_column("gold_model_features") == "prediction_ts"
    assert (
        registry.get_contract("gold_model_features").availability_kind
        == registry.AVAILABILITY_STORED_SAME_AS_BUSINESS
    )
    assert registry.business_time_column("perps_bars") == "bar_ts"
    perps = registry.get_contract("perps_bars")
    assert perps.availability_kind == registry.AVAILABILITY_DERIVED_BAR_CLOSE
    assert perps.availability == "bar_close"
    assert registry.as_of_predicate("perps_bars") == "bar_close <= T"
    # Derived availability is only allowed where no column exists to store it.
    for table in tables:
        contract = registry.get_contract(table)
        if contract.availability_kind == registry.AVAILABILITY_DERIVED_BAR_CLOSE:
            assert contract.table == "perps_bars"

    # Unknown table is an error, not a silent default.
    with pytest.raises(registry.UnknownTableError):
        registry.get_contract("gold_not_a_table")

    # Grain is enforced.
    rows = [
        {"symbol": "NVDA", "feature_ts": dt(2024, 1, 2, 14, 30)},
        {"symbol": "NVDA", "feature_ts": dt(2024, 1, 2, 14, 31)},
    ]
    assert registry.check_grain("gold_ohlcv_features", rows) == 2
    with pytest.raises(registry.GrainViolation):
        registry.check_grain(
            "gold_ohlcv_features",
            [
                {"symbol": "NVDA", "feature_ts": dt(2024, 1, 2, 14, 30)},
                {"symbol": "NVDA", "feature_ts": dt(2024, 1, 2, 14, 30)},
            ],
        )
    with pytest.raises(registry.GrainViolation):
        registry.check_grain("gold_ohlcv_features", [{"symbol": "NVDA"}])
    with pytest.raises(registry.GrainViolation):
        registry.check_grain(
            "gold_ohlcv_features", [{"symbol": None, "feature_ts": dt(2024, 1, 2)}]
        )

    # Cardinality to a security is n:1: many bars per symbol, never two
    # securities for one symbol.
    security_one = "sec-1"
    security_two = "sec-2"
    many_to_one = [
        {"symbol": "AAA", "security_id": security_one},
        {"symbol": "AAA", "security_id": security_one},
        {"symbol": "BBB", "security_id": security_two},
    ]
    registry.check_cardinality(
        "gold_ohlcv_features", many_to_one, left_column="symbol",
        right_column="security_id",
    )
    with pytest.raises(registry.CardinalityViolation):
        registry.check_cardinality(
            "gold_ohlcv_features",
            [
                {"symbol": "AAA", "security_id": security_one},
                {"symbol": "AAA", "security_id": security_two},
            ],
            left_column="symbol",
            right_column="security_id",
        )

    # ── Ticker changes between business time and query time ────────────────
    old_security = "sec-old"
    new_security = "sec-new"
    bridges = [
        registry.SecuritySymbolBridge(
            provider="massive",
            symbol="AAPL",
            security_id=old_security,
            valid_from=dt(2019, 1, 1),
            valid_to=dt(2021, 6, 1),
            observed_at=dt(2021, 6, 1),
            data_source=data_sources.CONFIG,
        ),
        registry.SecuritySymbolBridge(
            provider="massive",
            symbol="AAPL",
            security_id=new_security,
            valid_from=dt(2021, 6, 1),
            valid_to=None,
            observed_at=dt(2021, 6, 1),
            data_source=data_sources.CONFIG,
        ),
    ]
    registry.validate_bridge_rows(bridges)
    # The bridge row is chosen by business time, so a later ticker reuse does
    # not rewrite history.
    assert registry.resolve_security_symbol(
        bridges,
        provider="massive",
        symbol="AAPL",
        business_time=dt(2020, 1, 2),
        query_time=dt(2024, 1, 2),
    ) == old_security
    assert registry.resolve_security_symbol(
        bridges,
        provider="massive",
        symbol="AAPL",
        business_time=dt(2022, 1, 2),
        query_time=dt(2024, 1, 2),
    ) == new_security
    assert registry.resolve_security_symbol(
        bridges,
        provider="massive",
        symbol="AAPL",
        business_time=dt(2018, 6, 1),
        query_time=dt(2024, 1, 2),
    ) is None
    # Half-open boundaries.
    assert registry.resolve_security_symbol(
        bridges,
        provider="massive",
        symbol="AAPL",
        business_time=dt(2021, 6, 1),
        query_time=dt(2024, 1, 2),
    ) == new_security
    # A bridge observed after the query time is not usable.
    assert registry.resolve_security_symbol(
        bridges,
        provider="massive",
        symbol="AAPL",
        business_time=dt(2022, 1, 2),
        query_time=dt(2021, 1, 1),
    ) is None
    # Overlapping intervals per (provider, symbol) are rejected.
    with pytest.raises(registry.BridgeViolation):
        registry.validate_bridge_rows(
            [
                registry.SecuritySymbolBridge(
                    provider="massive", symbol="AAPL", security_id=old_security,
                    valid_from=dt(2019, 1, 1), valid_to=None,
                    observed_at=dt(2019, 1, 1),
                    data_source=data_sources.CONFIG,
                ),
                registry.SecuritySymbolBridge(
                    provider="massive", symbol="AAPL", security_id=new_security,
                    valid_from=dt(2021, 6, 1), valid_to=None,
                    observed_at=dt(2021, 6, 1),
                    data_source=data_sources.CONFIG,
                ),
            ]
        )


# ═══════════════════════════════════════════════════════════════════════════════
# S12 / S14 — edge endpoints, identity, symmetric storage, serialization
# ═══════════════════════════════════════════════════════════════════════════════

def _edge_row(**overrides) -> dict:
    row = {
        "edge_id": "edge-1",
        "src_id": "c1",
        "edge_type": "FILED",
        "dst_id": "f1",
        "data_source": "sec_edgar",
        "valid_from": dt(2024, 1, 2),
        "valid_to": None,
        "system_from": dt(2024, 1, 2),
        "system_to": None,
        "public_available_at": dt(2024, 1, 2),
        "system_observed_at": dt(2024, 1, 2),
        "confidence": Decimal("1.50"),
        "extraction_method": "structural",
        "evidence_count": 1,
        "build_generation_id": "gen-1",
        "evidence": [
            {"kind": "filing", "evidence_id": "ev-1", "data_source": "sec_edgar"}
        ],
        "identity": {"company_id": "c1", "filing_id": "f1"},
        "properties": {"b": 1, "a": Decimal("0.10"), "c": None},
    }
    row.update(overrides)
    return row


def _instrument_fixture(company_id="c1", **overrides) -> dict:
    """A Hyperliquid perpetual-future node row (perps are derivatives, v4 §J)."""
    values = {
        "venue": "hyperliquid",
        "dex_or_market": "xyz",
        "contract_symbol": "NVDA-USD",
        "instrument_type": "perpetual_future",
        "underlying_type": "equity",
        "underlying": "NVDA",
        "data_source": "hyperliquid",
    }
    values.update(overrides)
    return instruments.Instrument(**values).as_node_row(company_id=company_id)


def test_edge_registry_endpoints_identity_and_serialization():
    # Every v1 edge type is covered by exactly one contract.
    assert registry.unregistered_v1_edge_types() == ()
    for edge_type, contract in registry.EDGE_CONTRACTS.items():
        assert contract.edge_type == edge_type
        assert contract.src_types and contract.dst_types
        assert contract.identity and contract.evidence
        assert contract.scope in registry.SCOPES
        assert set(contract.src_types + contract.dst_types) <= (
            registry.CONTRACT_NODE_KINDS
        )
        # Every edge declares provider codes that its evidence kinds can carry.
        assert contract.data_sources, edge_type
        assert set(contract.data_sources) <= data_sources.DATA_SOURCES
        evidence_sources = set()
        for kind in contract.evidence:
            evidence_sources.update(registry.EVIDENCE_DATA_SOURCES[kind])
        assert set(contract.data_sources) & evidence_sources, edge_type

    # Mention edges have explicit endpoints; peers are symmetric and stored
    # once; amendment edges are Filing -> Filing only.
    assert registry.get_edge_contract("DISCLOSED_RISK").src_types == ("Filing",)
    assert registry.get_edge_contract("DISCLOSED_RISK").dst_types == ("RiskFactor",)
    assert registry.get_edge_contract("REPORTED_EVENT").dst_types == ("Event",)
    assert registry.get_edge_contract("HAS_SEGMENT").dst_types == ("Segment",)
    assert registry.get_edge_contract("HAS_PRODUCT").dst_types == ("Product",)
    assert registry.get_edge_contract("HAS_CUSTOMER").dst_types == ("Customer",)
    assert registry.get_edge_contract("AMENDS").src_types == ("Filing",)
    assert registry.get_edge_contract("AMENDS").dst_types == ("Filing",)
    assert registry.get_edge_contract("INFERRED_PEER").symmetric is True
    assert registry.get_edge_contract("INFERRED_PEER").scope == (
        registry.SCOPE_CROSS_COMPANY
    )
    assert registry.get_edge_contract("INFERRED_PEER").data_sources == ("derived",)
    # Perpetual futures are Instrument nodes linked to the equity, never merged.
    assert registry.get_edge_contract("LISTED_AS").src_types == ("Security",)
    assert registry.get_edge_contract("LISTED_AS").dst_types == ("Instrument",)
    assert registry.get_edge_contract("UNDERLIES").src_types == ("CryptoAsset",)
    assert registry.get_edge_contract("UNDERLIES").dst_types == ("Instrument",)
    with pytest.raises(registry.UnknownEdgeTypeError):
        registry.get_edge_contract("NOT_AN_EDGE")

    # Instrument fixtures: one equity-underlying perp and one crypto perp.
    perp = _instrument_fixture()
    crypto_perp = _instrument_fixture(
        company_id=None,
        venue="binance_um",
        dex_or_market=None,
        contract_symbol="BTCUSDT",
        underlying_type="crypto",
        underlying="BTC",
        data_source="binance_um",
    )
    assert perp["node_type"] == "Instrument"
    assert perp["instrument_type"] == "perpetual_future"
    assert perp["underlying_type"] == "equity"
    assert crypto_perp["underlying_kind"] == "CryptoAsset"
    endpoints = {
        "c1": "Company",
        "c2": "Company",
        "f1": "Filing",
        "r1": "RiskFactor",
        "s1": "Security",
        "s2": "Security",
        perp["node_id"]: "Instrument",
        crypto_perp["node_id"]: "Instrument",
    }
    good = _edge_row()
    contract = registry.validate_edge(good, endpoints)
    assert contract.edge_type == "FILED"
    assert registry.edge_identity_values(good, contract) == ("c1", "f1")

    # A perp is reachable only through LISTED_AS / UNDERLIES, never as a Security.
    listed = {
        "edge_type": "LISTED_AS",
        "src_id": "s1",
        "dst_id": perp["node_id"],
        "data_source": "config",
        "evidence": [
            {"kind": "mapping_observation", "evidence_id": "ev-map",
             "data_source": "config"}
        ],
        "identity": {"security_id": "s1", "instrument_id": perp["node_id"]},
        "valid_from": dt(2024, 1, 2),
        "system_from": dt(2024, 1, 2),
    }
    registry.validate_edge(listed, endpoints)
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(
            dict(listed, dst_id="s2",
                 identity={"security_id": "s1", "instrument_id": "s2"}),
            endpoints,
        )
    second_perp = _instrument_fixture(contract_symbol="NVDA-USD-2")
    endpoints[second_perp["node_id"]] = "Instrument"
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(
            dict(listed, src_id=perp["node_id"],
                 dst_id=second_perp["node_id"],
                 identity={"security_id": perp["node_id"],
                           "instrument_id": second_perp["node_id"]}),
            endpoints,
        )
    underlies = {
        "edge_type": "UNDERLIES",
        "src_id": "ca1",
        "dst_id": crypto_perp["node_id"],
        "data_source": "config",
        "evidence": [
            {"kind": "mapping_observation", "evidence_id": "ev-map",
             "data_source": "config"}
        ],
        "identity": {"asset_id": "ca1", "instrument_id": crypto_perp["node_id"]},
        "valid_from": dt(2024, 1, 2),
        "system_from": dt(2024, 1, 2),
    }
    endpoints["ca1"] = "CryptoAsset"
    registry.validate_edge(underlies, endpoints)
    # A Security on the Instrument end of UNDERLIES is rejected.
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(
            dict(underlies, dst_id="s1",
                 identity={"asset_id": "ca1", "instrument_id": "s1"}),
            endpoints,
        )
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(
            dict(underlies, src_id=crypto_perp["node_id"],
                 dst_id=perp["node_id"],
                 identity={"asset_id": crypto_perp["node_id"],
                           "instrument_id": perp["node_id"]}),
            endpoints,
        )

    # Wrong destination type.
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(_edge_row(dst_id="r1"), endpoints)
    # Unknown endpoint.
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(_edge_row(dst_id="missing"), endpoints)
    # Missing evidence, wrong evidence kind, missing identity, missing time.
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(_edge_row(evidence=[]), endpoints)
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(
            _edge_row(
                evidence=[
                    {"kind": "chunk", "evidence_id": "ev-1",
                     "data_source": "sec_edgar"}
                ]
            ),
            endpoints,
        )
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(_edge_row(identity={"company_id": "c1"}), endpoints)
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(_edge_row(valid_from=None), endpoints)

    # Symmetric peers are stored once with the lower id first; the registry
    # rejects the reversed direction and accepts the canonical one.
    peer = {
        "edge_type": "INFERRED_PEER",
        "src_id": "c1",
        "dst_id": "c2",
        "data_source": "derived",
        "evidence": [
            {"kind": "classification", "evidence_id": "ev-cls",
             "data_source": "derived"}
        ],
        "identity": {
            "pair": "c1|c2",
            "taxonomy": "sic",
            "code": "3674",
            "basis_date": "2024-01-02",
        },
        "valid_from": dt(2024, 1, 2),
        "system_from": dt(2024, 1, 2),
    }
    registry.validate_edge(peer, endpoints)
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(dict(peer, src_id="c2", dst_id="c1"), endpoints)

    # Canonical serialization: sorted keys, decimals as strings, explicit nulls,
    # and identical bytes regardless of input mapping order.
    row = _edge_row()
    first = registry.serialize_edge(row)
    second = registry.serialize_edge(dict(reversed(list(row.items()))))
    assert first == second
    payload = json.loads(first)
    assert list(payload) == sorted(payload)
    assert payload["confidence"] == "1.50"
    assert "valid_to" in payload and payload["valid_to"] is None
    assert "system_to" in payload and payload["system_to"] is None
    assert payload["public_available_at"] == dt(2024, 1, 2).isoformat()
    assert payload["properties"] == {"a": "0.10", "b": 1, "c": None}
    assert payload["edge_type"] == "FILED"
    assert payload["data_source"] == "sec_edgar"
    # A missing (or unknown) required field is a contract violation, not an
    # implicit null.
    for missing in (
        "valid_to",
        "confidence",
        "system_to",
        "build_generation_id",
        "data_source",
    ):
        broken = dict(row)
        broken.pop(missing)
        with pytest.raises(registry.EdgeContractError):
            registry.serialize_edge(broken)
    with pytest.raises(registry.EdgeContractError):
        registry.serialize_edge(dict(row, data_source="polygon"))

    # The registry agrees with the publication ownership scope for edges.
    assert publication.row_owner({"edge_type": "FILED", "company_id": "c1"}) == (
        "company:c1"
    )
    assert publication.row_owner({"edge_type": "INFERRED_PEER"}) == "cross-company"


# ═══════════════════════════════════════════════════════════════════════════════
# R4 — unregistered tables, per-time cardinality, bridge data_source
# ═══════════════════════════════════════════════════════════════════════════════

def test_is_available_rejects_unregistered_tables():
    with pytest.raises(registry.UnknownTableError):
        registry.is_available("gold_not_a_table", dt(2024, 1, 2), dt(2024, 1, 3))
    with pytest.raises(registry.UnknownTableError):
        registry.is_available("gold_not_a_table", None, dt(2024, 1, 3))
    # A registered table still answers by its declared availability.
    assert registry.is_available(
        "bridge_security_symbol", dt(2024, 1, 2), dt(2024, 1, 2)
    )
    assert not registry.is_available(
        "bridge_security_symbol", dt(2024, 1, 3), dt(2024, 1, 2)
    )


def test_cardinality_is_evaluated_per_time():
    columns = dict(
        left_column="symbol",
        right_column="security_id",
        interval_columns=("valid_from", "valid_to"),
    )
    reused = [
        {
            "symbol": "AAPL",
            "security_id": "sec-old",
            "valid_from": dt(2019, 1, 1),
            "valid_to": dt(2021, 6, 1),
        },
        {
            "symbol": "AAPL",
            "security_id": "sec-new",
            "valid_from": dt(2021, 6, 1),
            "valid_to": None,
        },
    ]
    # A ticker reused at non-overlapping times maps to one security per instant.
    registry.check_cardinality("bridge_security_symbol", reused, **columns)

    # Overlapping windows are still a violation, with the same rows.
    overlapping = [reused[0], dict(reused[1], valid_from=dt(2021, 1, 1))]
    with pytest.raises(registry.CardinalityViolation):
        registry.check_cardinality("bridge_security_symbol", overlapping, **columns)

    # An open-ended first window overlaps everything that follows.
    open_first = [dict(reused[0], valid_to=None), reused[1]]
    with pytest.raises(registry.CardinalityViolation):
        registry.check_cardinality("bridge_security_symbol", open_first, **columns)

    # Without interval columns every row is treated as concurrent (strict n:1).
    with pytest.raises(registry.CardinalityViolation):
        registry.check_cardinality(
            "bridge_security_symbol",
            reused,
            left_column="symbol",
            right_column="security_id",
        )

    # One security across both windows is never a cardinality violation.
    same_security = [reused[0], dict(reused[1], security_id="sec-old")]
    registry.check_cardinality("bridge_security_symbol", same_security, **columns)

    # The interval columns are required once per-time evaluation is requested.
    with pytest.raises(registry.CardinalityViolation):
        registry.check_cardinality(
            "bridge_security_symbol",
            [
                {"symbol": "AAPL", "security_id": "sec-old"},
                {"symbol": "AAPL", "security_id": "sec-new"},
            ],
            **columns,
        )


def test_one_to_one_cardinality_is_evaluated_per_time():
    columns = dict(
        left_column="chunk_id",
        right_column="document_id",
        interval_columns=("valid_from", "valid_to"),
    )
    # Both directions allow a value to be reused at non-overlapping times.
    sequential = [
        {
            "chunk_id": "chunk-1",
            "document_id": "doc-1",
            "valid_from": dt(2019, 1, 1),
            "valid_to": dt(2021, 1, 1),
        },
        {
            "chunk_id": "chunk-1",
            "document_id": "doc-2",
            "valid_from": dt(2021, 1, 1),
            "valid_to": None,
        },
    ]
    registry.check_cardinality("silver_sec_sections", sequential, **columns)

    reattached = [
        sequential[0],
        {
            "chunk_id": "chunk-2",
            "document_id": "doc-1",
            "valid_from": dt(2021, 1, 1),
            "valid_to": None,
        },
    ]
    registry.check_cardinality("silver_sec_sections", reattached, **columns)

    # The reverse (one document -> two chunks) overlap is caught too.
    with pytest.raises(registry.CardinalityViolation):
        registry.check_cardinality(
            "silver_sec_sections",
            [sequential[0], dict(reattached[1], valid_from=dt(2020, 6, 1))],
            **columns,
        )

    # An invalid interval is reported, never silently treated as open-ended.
    with pytest.raises(registry.CardinalityViolation):
        registry.check_cardinality(
            "silver_sec_sections",
            [dict(sequential[0], valid_to=dt(2018, 1, 1))],
            **columns,
        )


def test_symbol_bridge_rows_require_a_validated_data_source():
    values = dict(
        provider="massive",
        symbol="AAPL",
        security_id="sec-1",
        valid_from=dt(2020, 1, 1),
        valid_to=None,
        observed_at=dt(2020, 1, 1),
    )
    with pytest.raises(TypeError):
        registry.SecuritySymbolBridge(**values)
    # '' / None / an unknown spelling / a provider the bridge table does not
    # declare are all rejected; the bridge is hand-maintained config.
    for broken in (None, "", "Massive", "massive"):
        with pytest.raises(registry.BridgeViolation):
            registry.SecuritySymbolBridge(data_source=broken, **values)
    good = registry.SecuritySymbolBridge(
        data_source=data_sources.CONFIG, **values
    )
    assert good.data_source == data_sources.CONFIG
    assert registry.get_contract("bridge_security_symbol").data_sources == (
        data_sources.CONFIG,
    )
