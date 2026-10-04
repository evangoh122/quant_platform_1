"""tests/rag/_netguard.py — Extracted network guard helper for testability."""
import ipaddress
import socket


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


def install_default_timeout(add_finalizer, seconds=10):
    """Set the socket default timeout and register a finalizer that restores the previous value.

    Scoped so the guard's timeout cannot leak to tests outside the fixture.
    """
    prev = socket.getdefaulttimeout()
    socket.setdefaulttimeout(seconds)
    add_finalizer(lambda: socket.setdefaulttimeout(prev))
