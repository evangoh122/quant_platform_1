"""agent/guardrails.py — deterministic pre-trade risk service.

The LLM can *propose* orders but can never *execute* them. Every paper order
must pass every check here before the execution bridge is called. Failures carry
a stable, machine-readable ``code`` so the orchestrator and audit trail can act
on them programmatically. When any check fails, the bridge is never invoked.

No check performs I/O to the broker. The only state inputs (open orders,
buying power, positions) are supplied by the caller from the operational store,
so this module is pure and deterministic given its inputs.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Iterable, Optional, Sequence
from zoneinfo import ZoneInfo

# ── machine-readable violation codes ─────────────────────────────────────────
SYMBOL_NOT_ALLOWED = "SYMBOL_NOT_ALLOWED"
NOT_PAPER_MODE = "NOT_PAPER_MODE"
NON_POSITIVE_QUANTITY = "NON_POSITIVE_QUANTITY"
NON_POSITIVE_NOTIONAL = "NON_POSITIVE_NOTIONAL"
NOTIONAL_EXCEEDS_MAX = "NOTIONAL_EXCEEDS_MAX"
CONCENTRATION_EXCEEDS_MAX = "CONCENTRATION_EXCEEDS_MAX"
INSUFFICIENT_BUYING_POWER = "INSUFFICIENT_BUYING_POWER"
DUPLICATE_OPEN_ORDER = "DUPLICATE_OPEN_ORDER"
MARKET_CLOSED = "MARKET_CLOSED"
STALE_SIGNAL = "STALE_SIGNAL"
MISSING_IDEMPOTENCY_KEY = "MISSING_IDEMPOTENCY_KEY"
DUPLICATE_IDEMPOTENCY_KEY = "DUPLICATE_IDEMPOTENCY_KEY"
MISSING_APPROVAL = "MISSING_APPROVAL"
ACCOUNT_NOT_FOUND = "ACCOUNT_NOT_FOUND"
SIGNAL_NOT_FOUND = "SIGNAL_NOT_FOUND"

# Market session (US equities), America/New_York, deterministic.
_MARKET_TZ = ZoneInfo("America/New_York")
_MARKET_OPEN = time(9, 30)
_MARKET_CLOSE = time(16, 0)

# Conservative symbol shape: 1-10 chars, letters/digits/dot/dash. Rejects any
# quote, semicolon, whitespace, or comment token before it reaches SQL.
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9.\-]{1,10}$")


def normalize_symbol(symbol) -> str:
    """Validate and canonicalise a ticker; raises ValueError on injection-shaped input."""
    s = (symbol or "").strip().upper()
    if not _SYMBOL_RE.match(s):
        raise ValueError(f"Invalid symbol: {symbol!r}")
    return s


@dataclass(frozen=True)
class RiskViolation:
    code: str
    message: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class RiskResult:
    """Structured result of running the risk engine. Iterable of violations."""

    def __init__(self, violations: Sequence[RiskViolation] = ()):
        self.violations = list(violations)

    @property
    def passed(self) -> bool:
        return not self.violations

    @property
    def blocked(self) -> bool:
        return not self.passed

    def __bool__(self) -> bool:
        return self.passed

    def __iter__(self):
        return iter(self.violations)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "violations": [v.to_dict() for v in self.violations],
        }


@dataclass
class OrderContext:
    symbol: str
    side: str
    quantity: float
    notional: float
    order_type: str = "MARKET"
    limit_price: Optional[float] = None
    signal_prediction_ts: Optional[datetime] = None
    current_position_notional: float = 0.0
    buying_power: float = 100000.0
    open_orders: Sequence[dict] = field(default_factory=tuple)
    idempotency_key: str = ""
    idempotency_key_seen: bool = False
    is_paper: bool = True
    market_session_open: bool = True
    now: Optional[datetime] = None


def load_allow_list() -> set:
    """Load the ticker allow-list from config/tickers.yaml (lazy, no I/O on import).

    Fails closed: any load error (import failure, malformed YAML, I/O error)
    raises instead of returning ``None``, so a broken config can never degrade
    to "admit every syntactically valid symbol". An empty-but-loadable list is a
    legitimate list that rejects everything.
    """
    from config.tickers import get_all_ticker_symbols

    return set(get_all_ticker_symbols())


class RiskEngine:
    """Deterministic, dependency-injectable pre-trade risk checker."""

    def __init__(
        self,
        *,
        max_order_notional: Optional[float] = None,
        max_position_notional: Optional[float] = None,
        stale_signal_minutes: Optional[int] = None,
        allowed_symbols: Optional[set] = None,
        load_allowlist: bool = False,
    ):
        self.max_order_notional = (
            max_order_notional
            if max_order_notional is not None
            else float(os.getenv("MAX_ORDER_NOTIONAL", "25000"))
        )
        self.max_position_notional = (
            max_position_notional
            if max_position_notional is not None
            else float(os.getenv("MAX_POSITION_NOTIONAL", "50000"))
        )
        self.stale_signal_minutes = (
            stale_signal_minutes
            if stale_signal_minutes is not None
            else int(os.getenv("STALE_SIGNAL_MINUTES", "5"))
        )
        self._allowed_symbols = allowed_symbols
        if self._allowed_symbols is None and load_allowlist:
            self._allowed_symbols = load_allow_list()

    def check(self, ctx: OrderContext) -> RiskResult:
        violations = [v for v in self._iter_checks(ctx) if v is not None]
        return RiskResult(violations)

    def _iter_checks(self, ctx: OrderContext) -> Iterable[Optional[RiskViolation]]:
        yield self._check_symbol(ctx)
        yield self._check_paper_mode(ctx)
        yield self._check_positive_qty(ctx)
        yield self._check_notional_limit(ctx)
        yield self._check_concentration(ctx)
        yield self._check_buying_power(ctx)
        yield self._check_duplicate(ctx)
        yield self._check_market_session(ctx)
        yield self._check_stale_signal(ctx)
        yield self._check_idempotency(ctx)

    # ── individual checks ─────────────────────────────────────────────────────
    def _check_symbol(self, ctx: OrderContext) -> Optional[RiskViolation]:
        if not _SYMBOL_RE.match(ctx.symbol or ""):
            return RiskViolation(
                SYMBOL_NOT_ALLOWED,
                f"Symbol {ctx.symbol!r} is not a valid ticker",
                {"symbol": ctx.symbol},
            )
        if self._allowed_symbols is not None and ctx.symbol not in self._allowed_symbols:
            return RiskViolation(
                SYMBOL_NOT_ALLOWED,
                f"Symbol {ctx.symbol} not in allow-list",
                {"symbol": ctx.symbol},
            )
        return None

    def _check_paper_mode(self, ctx: OrderContext) -> Optional[RiskViolation]:
        if not ctx.is_paper:
            return RiskViolation(
                NOT_PAPER_MODE,
                "Only paper-account trading is allowed",
                {"is_paper": ctx.is_paper},
            )
        return None

    def _check_positive_qty(self, ctx: OrderContext) -> Optional[RiskViolation]:
        if ctx.quantity is None or ctx.quantity <= 0:
            return RiskViolation(
                NON_POSITIVE_QUANTITY,
                f"Quantity must be positive, got {ctx.quantity}",
                {"quantity": ctx.quantity},
            )
        if ctx.notional is None or ctx.notional <= 0:
            return RiskViolation(
                NON_POSITIVE_NOTIONAL,
                f"Notional must be positive, got {ctx.notional}",
                {"notional": ctx.notional},
            )
        return None

    def _check_notional_limit(self, ctx: OrderContext) -> Optional[RiskViolation]:
        if ctx.notional > self.max_order_notional:
            return RiskViolation(
                NOTIONAL_EXCEEDS_MAX,
                f"Notional ${ctx.notional:,.2f} exceeds per-order max "
                f"${self.max_order_notional:,.2f}",
                {"notional": ctx.notional, "limit": self.max_order_notional},
            )
        return None

    def _check_concentration(self, ctx: OrderContext) -> Optional[RiskViolation]:
        side = (ctx.side or "").upper()
        # A SELL reduces exposure (risk-reducing), so it must not be treated as
        # adding notional. Concentration is assessed on absolute exposure.
        delta = ctx.notional if side != "SELL" else -ctx.notional
        projected = ctx.current_position_notional + delta
        if abs(projected) > self.max_position_notional:
            return RiskViolation(
                CONCENTRATION_EXCEEDS_MAX,
                f"Position exposure would reach ${abs(projected):,.2f}, exceeding "
                f"${self.max_position_notional:,.2f} concentration cap",
                {"projected": projected, "limit": self.max_position_notional},
            )
        return None

    def _check_buying_power(self, ctx: OrderContext) -> Optional[RiskViolation]:
        if ctx.notional > ctx.buying_power:
            return RiskViolation(
                INSUFFICIENT_BUYING_POWER,
                f"Notional ${ctx.notional:,.2f} exceeds buying power "
                f"${ctx.buying_power:,.2f}",
                {"notional": ctx.notional, "buying_power": ctx.buying_power},
            )
        return None

    def _check_duplicate(self, ctx: OrderContext) -> Optional[RiskViolation]:
        for order in ctx.open_orders:
            if order.get("symbol") == ctx.symbol:
                return RiskViolation(
                    DUPLICATE_OPEN_ORDER,
                    f"Conflicting open {order.get('side', '')} order for {ctx.symbol}",
                    {"order_id": order.get("order_id")},
                )
        return None

    def _check_market_session(self, ctx: OrderContext) -> Optional[RiskViolation]:
        if not ctx.market_session_open:
            return RiskViolation(
                MARKET_CLOSED,
                "Market session is closed",
                {},
            )
        return None

    def _check_stale_signal(self, ctx: OrderContext) -> Optional[RiskViolation]:
        ts = ctx.signal_prediction_ts
        if ts is None:
            return None
        now = ctx.now or datetime.now(timezone.utc)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = now - ts
        if age > timedelta(minutes=self.stale_signal_minutes):
            return RiskViolation(
                STALE_SIGNAL,
                f"Signal is {age.total_seconds() / 60:.1f} min old "
                f"(max {self.stale_signal_minutes} min)",
                {"age_minutes": age.total_seconds() / 60},
            )
        return None

    def _check_idempotency(self, ctx: OrderContext) -> Optional[RiskViolation]:
        if not ctx.idempotency_key:
            return RiskViolation(
                MISSING_IDEMPOTENCY_KEY,
                "idempotency_key is required",
                {},
            )
        if ctx.idempotency_key_seen:
            return RiskViolation(
                DUPLICATE_IDEMPOTENCY_KEY,
                "idempotency_key already used",
                {"idempotency_key": ctx.idempotency_key},
            )
        return None


def is_market_session_open(now: Optional[datetime] = None) -> bool:
    """Deterministic US-equity session check (Mon-Fri, 09:30-16:00 ET).

    Holiday calendar is intentionally not modelled; documented limitation.
    """
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(_MARKET_TZ)
    if local.weekday() >= 5:  # Sat/Sun
        return False
    return _MARKET_OPEN <= local.time() < _MARKET_CLOSE


def validate_order(
    ctx: OrderContext,
    *,
    engine: Optional[RiskEngine] = None,
) -> RiskResult:
    """Convenience entry point returning a structured RiskResult."""
    engine = engine or RiskEngine()
    return engine.check(ctx)
