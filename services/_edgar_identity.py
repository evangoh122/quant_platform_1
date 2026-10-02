import os
from loguru import logger

_identity_set = False


def ensure_edgar_identity() -> None:
    global _identity_set
    if _identity_set:
        return
    user_agent = os.getenv("EDGAR_USER_AGENT")
    if not user_agent:
        logger.warning("EDGAR_USER_AGENT not set. SEC API calls may fail.")
        return
    try:
        import edgar
        edgar.set_identity(user_agent)
        _identity_set = True
    except ImportError:
        pass
    except Exception:
        logger.warning("Failed to set EdgarTools identity")
