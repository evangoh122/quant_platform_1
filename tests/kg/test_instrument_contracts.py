"""Instrument contracts: perps are derivatives, never equities (v4 §J / O3 / F3).

Covers the three review items this PR fixes:

* **F1** — an Instrument carries ``instrument_type`` (only ``perpetual_future``),
  ``underlying_type`` and ``underlying`` as attributes, and can never resolve
  as, alias into, merge with or be an edge endpoint typed as a Security.
* **O3** — ``publication.row_owner`` derives an Instrument's ownership from its
  underlying: Security -> that security's company, CryptoAsset -> global.
* **F3** — every produced KG row (node, edge, evidence) carries a required,
  validated ``data_source`` from ``config.data_sources``.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from config import data_sources
from sec_kg.contracts import facts, filings, identity, instruments, names, publication
from sec_kg.contracts import registry

DT = datetime(2024, 1, 2, tzinfo=timezone.utc)
COMPANY = identity.company_id("0001045810")
SHARE_CLASS = "common"
SECURITY = identity.security_id(COMPANY, SHARE_CLASS)
FILING = identity.filing_id(COMPANY, "0001045810-24-000001")
CONCEPT = identity.concept_id("us-gaap", "Revenues")
PERIOD = identity.period_id_v2("duration", "2023-01-29", "2024-01-28")


def instrument(**overrides) -> instruments.Instrument:
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
    return instruments.Instrument(**values)


def security_row(share_class: str = SHARE_CLASS) -> dict:
    return {
        "node_type": "Security",
        "node_id": identity.security_id(COMPANY, share_class),
        "identity_version": identity.identity_version("security"),
        "issuer_company_id": COMPANY,
        "share_class_code": share_class,
        "company_id": COMPANY,
        "data_source": "config",
    }


def edge_row(**overrides) -> dict:
    row = {
        "edge_id": "edge-1",
        "src_id": COMPANY,
        "edge_type": "FILED",
        "dst_id": FILING,
        "data_source": "sec_edgar",
        "valid_from": DT,
        "valid_to": None,
        "system_from": DT,
        "system_to": None,
        "public_available_at": DT,
        "system_observed_at": DT,
        "confidence": 1.0,
        "extraction_method": "structural",
        "evidence_count": 1,
        "build_generation_id": "gen-1",
        "evidence": [
            {"kind": "filing", "evidence_id": "ev-1", "data_source": "sec_edgar"}
        ],
        "identity": {"company_id": COMPANY, "filing_id": FILING},
        "properties": {},
    }
    row.update(overrides)
    return row


# ═══════════════════════════════════════════════════════════════════════════════
# F1 — typing is an attribute, identity is the venue contract
# ═══════════════════════════════════════════════════════════════════════════════

def test_instrument_typing_is_an_attribute_not_identity():
    perp = instrument()
    assert perp.instrument_type == "perpetual_future"
    assert perp.is_perpetual_future
    assert perp.underlying_kind == instruments.UNDERLYING_KIND_SECURITY
    # Identity is exactly (venue, dex_or_market, contract_symbol).
    assert perp.natural_key == identity.instrument_key("hyperliquid", "xyz", "NVDA-USD")
    assert perp.node_id == identity.instrument_id("hyperliquid", "xyz", "NVDA-USD")
    assert perp.identity_version == "kgid:v2"
    assert perp.attributes() == {
        "instrument_type": "perpetual_future",
        "underlying_type": "equity",
        "underlying": "NVDA",
    }
    # Re-typing/re-labelling keeps the id: attributes never enter the key.
    relabelled = instrument(
        venue="HYPERLIQUID",
        contract_symbol="nvda-usd",
        underlying_type="etf",
        underlying="QQQ",
    )
    assert relabelled.node_id == perp.node_id
    assert relabelled.attributes() != perp.attributes()


@pytest.mark.parametrize(
    "overrides",
    [
        {"instrument_type": "equity"},
        {"instrument_type": "spot"},
        {"underlying_type": "stock"},
        {"underlying": ""},
        {"data_source": "massive"},   # a perp is a venue product
        {"data_source": "config"},
    ],
)
def test_instrument_rejects_non_derivative_typing(overrides):
    with pytest.raises(instruments.InstrumentError):
        instrument(**overrides)


def test_perpetual_future_is_never_a_security_identity_alias_or_endpoint():
    perp = instrument()
    perp_row = perp.as_node_row(company_id=COMPANY)
    security = security_row()
    other_security = security_row("class_b")

    # ── identity path ──────────────────────────────────────────────────────
    assert perp.node_id != security["node_id"]
    assert publication.validate_node_row(perp_row) == "Instrument"
    assert publication.validate_node_row(security) == "Security"
    # An Instrument row cannot claim the Security's identity ...
    with pytest.raises(publication.PublicationError):
        publication.validate_node_row(dict(perp_row, node_id=security["node_id"]))
    # ... cannot be published as a Security ...
    with pytest.raises(publication.PublicationError):
        publication.validate_node_row(dict(perp_row, node_type="Security"))
    # ... and a Security row cannot wear the contract's attributes.
    with pytest.raises(publication.PublicationError):
        publication.validate_node_row(
            dict(security, instrument_type="perpetual_future")
        )

    # ── merge path: two nodes, one per kind, never collapsed ───────────────
    merged = publication.merge_node_rows([security, perp_row])
    assert len(merged) == 2
    assert {row["node_type"] for row in merged} == {"Security", "Instrument"}
    # An id alias that would fold the contract into the equity is rejected.
    with pytest.raises(publication.PublicationError):
        publication.merge_node_rows(
            [security, perp_row], aliases={perp.node_id: security["node_id"]}
        )
    with pytest.raises(publication.PublicationError):
        publication.merge_node_rows([perp_row, dict(perp_row, node_id=perp.node_id)])

    # ── edge-endpoint path ─────────────────────────────────────────────────
    endpoints = {
        security["node_id"]: "Security",
        other_security["node_id"]: "Security",
        perp.node_id: "Instrument",
    }
    listed = {
        "edge_type": "LISTED_AS",
        "src_id": security["node_id"],
        "dst_id": perp.node_id,
        "data_source": "config",
        "evidence": [
            {"kind": "mapping_observation", "evidence_id": "ev-1",
             "data_source": "config"}
        ],
        "identity": {
            "security_id": security["node_id"],
            "instrument_id": perp.node_id,
        },
        "valid_from": DT,
        "system_from": DT,
    }
    assert registry.validate_edge(listed, endpoints).edge_type == "LISTED_AS"
    # A Security on the Instrument end is rejected ...
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(
            dict(listed, dst_id=other_security["node_id"],
                 identity={"security_id": security["node_id"],
                           "instrument_id": other_security["node_id"]}),
            endpoints,
        )
    # ... and an Instrument on the Security end is rejected too.
    endpoint_instrument = instrument(contract_symbol="NVDA-USD-2").node_id
    endpoints[endpoint_instrument] = "Instrument"
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(
            dict(listed, src_id=perp.node_id, dst_id=endpoint_instrument,
                 identity={"security_id": perp.node_id,
                           "instrument_id": endpoint_instrument}),
            endpoints,
        )

    # UNDERLIES is CryptoAsset -> Instrument; a Security never fits either end.
    crypto = identity.crypto_asset_id("BTC")
    endpoints[crypto] = "CryptoAsset"
    underlies = dict(
        listed,
        edge_type="UNDERLIES",
        src_id=crypto,
        dst_id=perp.node_id,
        identity={"asset_id": crypto, "instrument_id": perp.node_id},
    )
    assert registry.validate_edge(underlies, endpoints).edge_type == "UNDERLIES"
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(
            dict(underlies, dst_id=other_security["node_id"],
                 identity={"asset_id": crypto,
                           "instrument_id": other_security["node_id"]}),
            endpoints,
        )
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(
            dict(underlies, src_id=perp.node_id,
                 identity={"asset_id": perp.node_id,
                           "instrument_id": perp.node_id}),
            endpoints,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# O3 — Instrument ownership follows the underlying
# ═══════════════════════════════════════════════════════════════════════════════

def test_instrument_ownership_follows_the_underlying():
    equity_perp = instrument()
    crypto_perp = instrument(
        venue="binance_um",
        dex_or_market=None,
        contract_symbol="BTCUSDT",
        underlying_type="crypto",
        underlying="BTC",
        data_source="binance_um",
    )
    equity_row = equity_perp.as_node_row(company_id=COMPANY)
    crypto_row = crypto_perp.as_node_row()

    # A contract on a Security is owned by that security's company ...
    assert publication.row_owner(equity_row) == f"company:{COMPANY}"
    # ... a contract on a CryptoAsset is global (v4 §G global union).
    assert publication.row_owner(crypto_row) == "global"

    # A equity-underlying contract cannot be built without its company, and a
    # crypto one must not claim one.
    with pytest.raises(instruments.InstrumentError):
        equity_perp.as_node_row()
    with pytest.raises(instruments.InstrumentError):
        crypto_perp.as_node_row(company_id=COMPANY)

    # A commodity underlying has no node owner yet: never silently global.
    commodity = instrument(
        venue="binance_um", dex_or_market=None, contract_symbol="XAUUSDT",
        underlying_type="commodity", underlying="XAU", data_source="binance_um",
    )
    with pytest.raises(publication.PublicationError):
        publication.row_owner(commodity.as_node_row())
    assert publication.row_owner(
        commodity.as_node_row(company_id=COMPANY)
    ) == f"company:{COMPANY}"

    # A subset build of the member replaces its contract and keeps the global
    # crypto contract (union of references).
    subset = publication.plan_subset([equity_row, crypto_row], [], [COMPANY])
    assert [row["node_id"] for row in subset] == [crypto_perp.node_id]


# ═══════════════════════════════════════════════════════════════════════════════
# F3 — every produced row carries a validated data_source
# ═══════════════════════════════════════════════════════════════════════════════

def test_edge_rows_require_a_valid_data_source():
    good = edge_row()
    assert '"data_source":"sec_edgar"' in registry.serialize_edge(good).replace(
        " ", ""
    )
    missing = dict(good)
    missing.pop("data_source")
    for broken in (missing, dict(good, data_source=None), dict(good, data_source="polygon")):
        with pytest.raises(registry.EdgeContractError):
            registry.serialize_edge(broken)
    # validate_edge also pins the code to what the edge contract allows.
    endpoints = {COMPANY: "Company", FILING: "Filing"}
    with pytest.raises(registry.EdgeContractError):
        registry.validate_edge(dict(good, data_source="derived"), endpoints)


def test_evidence_rows_require_a_valid_data_source():
    assert registry.validate_evidence_row(
        {"kind": "filing", "evidence_id": "ev-1", "data_source": "sec_edgar"}
    ) == "filing"
    assert registry.validate_evidence_row(
        {"kind": "xbrl_observation", "data_source": "sec_companyfacts"}
    ) == "xbrl_observation"
    for broken in (
        {"kind": "filing", "evidence_id": "ev-1"},
        {"kind": "filing", "evidence_id": "ev-1", "data_source": None},
        {"kind": "filing", "evidence_id": "ev-1", "data_source": "derived"},
        {"kind": "not_a_kind", "data_source": "sec_edgar"},
    ):
        with pytest.raises(registry.EdgeContractError):
            registry.validate_evidence_row(broken)
    # An edge cannot carry evidence from a provider it does not declare.
    contract = registry.get_edge_contract("FILED")
    with pytest.raises(registry.EdgeContractError):
        registry.validate_evidence_row(
            {"kind": "chunk", "data_source": "sec_companyfacts"}, contract
        )


def test_node_rows_require_a_valid_data_source():
    row = instrument().as_node_row(company_id=COMPANY)
    for broken in (
        {key: value for key, value in row.items() if key != "data_source"},
        dict(row, data_source=None),
        dict(row, data_source="Massive"),
        dict(security_row(), data_source=""),
    ):
        with pytest.raises(publication.PublicationError):
            publication.validate_node_row(broken)


def test_sec_row_builders_emit_the_validated_source():
    filing = filings.DimFiling(
        accession="0001045810-24-000001",
        record_key="rec-1",
        source_row_count=1,
        data_source="sec_edgar",
    )
    assert filing.as_row()["data_source"] == "sec_edgar"
    # The field is required at construction and validated when supplied.
    with pytest.raises(TypeError):
        filings.DimFiling(
            accession="0001045810-24-000001", record_key="rec-1", source_row_count=1
        )
    with pytest.raises(ValueError):
        filings.DimFiling(
            accession="a", record_key="rec-1", source_row_count=1,
            data_source="polygon",
        )

    issue = filings.QualityIssue(
        accession="0001045810-24-000001", field="cik", kind="missing",
        data_source="sec_edgar",
    )
    assert issue.as_row()["data_source"] == "sec_edgar"
    with pytest.raises(ValueError):
        filings.QualityIssue(
            accession="a", field="cik", kind="missing", data_source=""
        )

    interval = names.NameInterval(
        name="NVIDIA CORP",
        valid_from=DT,
        valid_to=None,
        source=names.NAME_SOURCE_CURRENT,
        rank=names.RANK_CURRENT,
        data_source="sec_edgar",
    )
    assert interval.as_dict()["data_source"] == "sec_edgar"
    with pytest.raises(ValueError):
        names.NameInterval(
            name="NVIDIA CORP",
            valid_from=DT,
            valid_to=None,
            source=names.NAME_SOURCE_CURRENT,
            rank=names.RANK_CURRENT,
            data_source="Massive",
        )

    observation = facts.make_observation(
        facts.assertion_key(
            facts.series_key(COMPANY, CONCEPT, "USD", PERIOD), FILING
        ),
        {
            "value_raw": "100",
            "unit": "USD",
            "start": "2023-01-29",
            "end": "2024-01-28",
            "form": "10-K",
            "accn": "0001045810-24-000001",
        },
        public_available_at=DT,
        system_from=DT,
    )
    assert observation.data_source == "sec_companyfacts"
    assert observation.as_row()["data_source"] == "sec_companyfacts"
    assert data_sources.validate_data_source(observation.as_row()["data_source"])
    # Entity-extracted observations are computed here, not fetched from a vendor.
    extracted = facts.make_observation(
        observation.key.assertion,
        {
            "value_raw": "100",
            "unit": "USD",
            "start": "2023-01-29",
            "end": "2024-01-28",
            "form": "10-K",
            "accn": "0001045810-24-000001",
        },
        source=facts.SOURCE_ENTITY_EXTRACTION,
        public_available_at=DT,
        system_from=DT,
    )
    assert extracted.data_source == "derived"
