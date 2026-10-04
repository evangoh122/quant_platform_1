"""tests/rag/_netguard.py — Extracted network guard helper for testability."""
import ipaddress


def _is_loopback(host: str) -> bool:
    """Check if host is a loopback address.

    Uses ipaddress.ip_address() for numerically correct validation.
    Only the literal string 'localhost' is accepted as loopback by name;
    anything else that isn't a valid IP literal is blocked.
    """
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        # Not a valid IP literal (e.g. "127.1.evil.com") — block it
        return False