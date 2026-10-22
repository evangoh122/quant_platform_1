"""sec_kg/contracts/instruments.py — venue contracts are derivatives.

Design of record: ``KG_DATA_MODEL_v4`` §J (owner, 2026-10-22) and
``.agents/requests/RULE-perps-are-derivatives.md``.

Hyperliquid and Binance USD-M listings are **perpetual futures**: they track an
equity, ETF, fund, preferred or crypto asset but are never that asset.  An
``Instrument`` node therefore carries three typing attributes —:

``instrument_type``
    only ``perpetual_future`` is accepted for now; in particular ``equity`` is
    rejected, not silently tolerated;
``underlying_type``
    one of ``equity``, ``etf``, ``fund``, ``preferred``, ``commodity``,
    ``crypto``;
``underlying``
    the ticker/asset code the contract tracks.

Those three are **attributes, not identity**.  Identity stays
``(venue, dex_or_market, contract_symbol)`` (``identity.instrument_key``) so
re-typing or re-labelling a contract never mints a second id, and no attribute
can ever make an Instrument resolve as, or merge into, a Security: the id
prefix/kind differs, ``as_node_row`` refuses Security identity fields, and the
publication contract re-derives the id from the venue key.

A perpetual future is only produced by a perpetual venue, so ``data_source``
is restricted to ``hyperliquid`` / ``binance_um`` (``RULE-data-source-column``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from config.data_sources import BINANCE_UM, HYPERLIQUID, validate_data_source
from sec_kg.contracts import identity
from sec_kg.model import normalize_unicode

# ── Vocabulary ──────────────────────────────────────────────────────────────

INSTRUMENT_TYPE_PERPETUAL_FUTURE = "perpetual_future"

#: Accepted instrument types.  Only perpetual futures exist in the graph today;
#: anything else (``equity`` above all) is a contract violation.
ACCEPTED_INSTRUMENT_TYPES: tuple[str, ...] = (INSTRUMENT_TYPE_PERPETUAL_FUTURE,)

UNDERLYING_TYPE_EQUITY = "equity"
UNDERLYING_TYPE_ETF = "etf"
UNDERLYING_TYPE_FUND = "fund"
UNDERLYING_TYPE_PREFERRED = "preferred"
UNDERLYING_TYPE_COMMODITY = "commodity"
UNDERLYING_TYPE_CRYPTO = "crypto"

#: ``KG_DATA_MODEL_v4`` §J underlying taxonomy.
UNDERLYING_TYPES: tuple[str, ...] = (
    UNDERLYING_TYPE_EQUITY,
    UNDERLYING_TYPE_ETF,
    UNDERLYING_TYPE_FUND,
    UNDERLYING_TYPE_PREFERRED,
    UNDERLYING_TYPE_COMMODITY,
    UNDERLYING_TYPE_CRYPTO,
)

#: Underlying types that are themselves an equity ``Security`` node.
SECURITY_UNDERLYING_TYPES: tuple[str, ...] = (
    UNDERLYING_TYPE_EQUITY,
    UNDERLYING_TYPE_ETF,
    UNDERLYING_TYPE_FUND,
    UNDERLYING_TYPE_PREFERRED,
)

#: Underlying node kinds a perp contract can point at.
UNDERLYING_KIND_SECURITY = "Security"
UNDERLYING_KIND_CRYPTO_ASSET = "CryptoAsset"
UNDERLYING_KIND_COMMODITY = "Commodity"

#: Perpetual futures come from perpetual venues only.
PERP_DATA_SOURCES: tuple[str, ...] = (HYPERLIQUID, BINANCE_UM)

NODE_TYPE_INSTRUMENT = "Instrument"

#: Fields that belong to a ``Security`` row and must never appear on an
#: Instrument row (a perp is not the equity it tracks).
SECURITY_ONLY_NODE_FIELDS: tuple[str, ...] = (
    "issuer_company_id",
    "share_class_code",
)

#: Fields that only an Instrument row may carry (the reverse guard).
INSTRUMENT_ONLY_NODE_FIELDS: tuple[str, ...] = (
    "instrument_type",
    "underlying_type",
    "underlying",
    "underlying_kind",
    "venue",
    "dex_or_market",
    "contract_symbol",
)


class InstrumentError(ValueError):
    """An Instrument row violates the perps-are-derivatives contract."""


def _text(value: Any) -> str:
    return normalize_unicode(str(value)) if value is not None else ""


def _required(label: str, value: Any) -> str:
    text = _text(value)
    if not text:
        raise InstrumentError(f"{label} must not be blank")
    return text


def underlying_kind(underlying_type: str) -> str:
    """Map an ``underlying_type`` to the node kind it points at."""
    text = _text(underlying_type).lower()
    if text in SECURITY_UNDERLYING_TYPES:
        return UNDERLYING_KIND_SECURITY
    if text == UNDERLYING_TYPE_CRYPTO:
        return UNDERLYING_KIND_CRYPTO_ASSET
    if text == UNDERLYING_TYPE_COMMODITY:
        return UNDERLYING_KIND_COMMODITY
    raise InstrumentError(
        f"underlying_type must be one of {list(UNDERLYING_TYPES)}, got "
        f"{underlying_type!r}"
    )


# ── Instrument ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Instrument:
    """One venue contract (a perpetual future), typed as a derivative."""

    venue: str
    dex_or_market: Optional[str]
    contract_symbol: str
    instrument_type: str
    underlying_type: str
    underlying: str
    data_source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "venue", _required("venue", self.venue).lower())
        dex = _text(self.dex_or_market)
        object.__setattr__(self, "dex_or_market", dex or None)
        object.__setattr__(
            self,
            "contract_symbol",
            _required("contract_symbol", self.contract_symbol).upper(),
        )
        instrument_type = _required(
            "instrument_type", self.instrument_type
        ).lower()
        if instrument_type not in ACCEPTED_INSTRUMENT_TYPES:
            raise InstrumentError(
                "instrument_type must be one of "
                f"{list(ACCEPTED_INSTRUMENT_TYPES)} (perpetual futures are "
                f"derivatives, never equities); got {self.instrument_type!r}"
            )
        object.__setattr__(self, "instrument_type", instrument_type)
        underlying_type_value = _required(
            "underlying_type", self.underlying_type
        ).lower()
        # Validates membership and raises the same message as the public helper.
        underlying_kind(underlying_type_value)
        object.__setattr__(self, "underlying_type", underlying_type_value)
        object.__setattr__(self, "underlying", _required("underlying", self.underlying))
        source = validate_data_source(self.data_source)
        if source not in PERP_DATA_SOURCES:
            raise InstrumentError(
                "perpetual futures are venue products: data_source must be one "
                f"of {list(PERP_DATA_SOURCES)}, got {source!r}"
            )
        object.__setattr__(self, "data_source", source)

    # ── Identity (attributes are deliberately excluded) ────────────────────

    @property
    def natural_key(self) -> identity.NaturalKey:
        return identity.instrument_key(
            self.venue, self.dex_or_market, self.contract_symbol
        )

    @property
    def node_id(self) -> str:
        return identity.entity_id(self.natural_key)

    @property
    def identity_version(self) -> str:
        return identity.identity_version(identity.KIND_INSTRUMENT)

    @property
    def underlying_kind(self) -> str:
        return underlying_kind(self.underlying_type)

    @property
    def is_perpetual_future(self) -> bool:
        return self.instrument_type == INSTRUMENT_TYPE_PERPETUAL_FUTURE

    def attributes(self) -> Dict[str, str]:
        """The typing attributes carried by the row, never by the identity."""
        return {
            "instrument_type": self.instrument_type,
            "underlying_type": self.underlying_type,
            "underlying": self.underlying,
        }

    def as_node_row(self, company_id: Optional[str] = None) -> Dict[str, Any]:
        """Build the graph node row for this contract.

        ``company_id`` is the company that owns the **underlying Security** and
        is required exactly when the underlying is a Security: publication then
        treats the Instrument as company-owned, while crypto-underlying
        contracts stay global (``KG_DATA_MODEL_v4`` §G, O3).
        """
        row: Dict[str, Any] = {
            "node_type": NODE_TYPE_INSTRUMENT,
            "node_id": self.node_id,
            "identity_version": self.identity_version,
            "venue": self.venue,
            "dex_or_market": self.dex_or_market,
            "contract_symbol": self.contract_symbol,
            "underlying_kind": self.underlying_kind,
            "data_source": self.data_source,
        }
        row.update(self.attributes())
        if self.underlying_kind == UNDERLYING_KIND_SECURITY:
            row["company_id"] = _required("company_id", company_id)
        elif self.underlying_kind == UNDERLYING_KIND_CRYPTO_ASSET:
            if company_id is not None:
                raise InstrumentError(
                    "a crypto-underlying contract is global; it must not name a "
                    "company_id"
                )
        elif company_id is not None:
            # No company owns a spot commodity today; an explicit owner keeps
            # the row publishable without inventing a commodity node.
            row["owner_company_id"] = _required("company_id", company_id)
        return row
