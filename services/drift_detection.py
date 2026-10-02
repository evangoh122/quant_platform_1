from dataclasses import dataclass
from datetime import datetime, timezone
from loguru import logger

# MiMo delivers this
try:
    from api.db.review_queue import compute_agreement_rate, count_unrecognized_concepts
except ImportError:  # pragma: no cover
    compute_agreement_rate = None        # MiMo delivers this
    count_unrecognized_concepts = None   # MiMo delivers this



@dataclass
class DriftStatus:
    agreement_rate: float
    agreement_floor: float
    agreement_alert: bool          # True when agreement_rate < agreement_floor
    unrecognized_concept_count: int
    concept_spike_threshold: int
    concept_alert: bool            # True when count > threshold
    window_size: int
    last_updated: datetime


def check_drift(
    conn,
    agreement_floor: float,
    concept_spike_threshold: int,
    window: int = 100,
) -> DriftStatus:
    """
    Checks both drift signals. Never alerts on escalation rate alone (REQ-RQ-05).

    Signals evaluated:
      1. agreement_rate  — fires alert when rate drops below agreement_floor (REQ-RQ-03/04)
      2. unrecognized_concept_count — fires alert when count exceeds concept_spike_threshold (REQ-RQ-04)

    # REQ-RQ-05: escalation-rate is intentionally excluded as a trigger signal
    """
    if compute_agreement_rate is None or count_unrecognized_concepts is None:
        raise RuntimeError(
            "api.db.review_queue is not yet available — MiMo delivers this module."
        )

    # Signal 1: human-agreement rate (REQ-RQ-03)
    agreement_rate: float = compute_agreement_rate(conn, window=window)
    agreement_alert: bool = agreement_rate < agreement_floor

    # Signal 2: unrecognized concept spike (REQ-RQ-04)
    # REQ-RQ-05: escalation-rate is intentionally excluded as a trigger signal
    unrecognized_concept_count: int = count_unrecognized_concepts(conn, window_hours=window)
    concept_alert: bool = unrecognized_concept_count > concept_spike_threshold

    return DriftStatus(
        agreement_rate=agreement_rate,
        agreement_floor=agreement_floor,
        agreement_alert=agreement_alert,
        unrecognized_concept_count=unrecognized_concept_count,
        concept_spike_threshold=concept_spike_threshold,
        concept_alert=concept_alert,
        window_size=window,
        last_updated=datetime.now(timezone.utc),
    )


def log_drift_alert(status: DriftStatus) -> None:
    """Logs a structured alert entry when any drift signal fires. Uses Python logging."""
    if status.agreement_alert:
        logger.warning(
            "DRIFT ALERT — agreement_rate below floor: "
            "agreement_rate={:.4f} floor={:.4f} window={}",
            status.agreement_rate,
            status.agreement_floor,
            status.window_size,
        )
    if status.concept_alert:
        logger.warning(
            "DRIFT ALERT — unrecognized concept spike: "
            "count={} threshold={} window={}",
            status.unrecognized_concept_count,
            status.concept_spike_threshold,
            status.window_size,
        )
    # REQ-RQ-05: escalation-rate is intentionally excluded as a trigger signal
