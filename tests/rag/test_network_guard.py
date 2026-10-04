"""tests/rag/test_network_guard.py — Tests for the network guard in conftest.py.

Verifies that the _block_network fixture:
1. Blocks outbound connections to non-loopback addresses
2. Allows loopback (127.0.0.0/8, ::1, localhost)
3. Allows AF_UNIX sockets
4. Allows getaddrinfo(None, ...) for passive/bind calls
"""
from __future__ import annotations

import socket
import sys
import tempfile
from pathlib import Path

import pytest


# The guard raises ConnectionRefusedError with this message prefix
GUARD_MSG_PREFIX = "Network access blocked in tests"


class TestGuardBlocksOutbound:
    """Outbound connections to non-loopback addresses must raise ConnectionRefusedError."""

    def test_create_connection_blocked(self):
        """socket.create_connection to a non-loopback IP raises the guard error."""
        with pytest.raises(ConnectionRefusedError, match=GUARD_MSG_PREFIX):
            socket.create_connection(("93.184.216.34", 80))

    def test_socket_connect_blocked(self):
        """socket.socket().connect to a non-loopback IP raises the guard error."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(ConnectionRefusedError, match=GUARD_MSG_PREFIX):
                sock.connect(("93.184.216.34", 80))
        finally:
            sock.close()

    def test_socket_connect_ex_blocked(self):
        """socket.socket().connect_ex to a non-loopback IP raises the guard error."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(ConnectionRefusedError, match=GUARD_MSG_PREFIX):
                sock.connect_ex(("93.184.216.34", 80))
        finally:
            sock.close()

    def test_getaddrinfo_blocked(self):
        """socket.getaddrinfo for a non-loopback host raises the guard error."""
        with pytest.raises(ConnectionRefusedError, match=GUARD_MSG_PREFIX):
            socket.getaddrinfo("example.com", 80)


class TestGuardAllowsLoopback:
    """Loopback connections must succeed through the guard."""

    def test_loopback_connect(self):
        """Connect to a listening socket on 127.0.0.1 (port 0 = auto-assign)."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]

            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client.connect(("127.0.0.1", port))
                # If we get here, the connection succeeded
            finally:
                client.close()
        finally:
            server.close()

    def test_loopback_create_connection(self):
        """create_connection to 127.0.0.1 works."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]

            conn = socket.create_connection(("127.0.0.1", port))
            conn.close()
        finally:
            server.close()

    def test_localhost_connect(self):
        """Connect to 'localhost' works."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]

            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client.connect(("localhost", port))
            finally:
                client.close()
        finally:
            server.close()

    def test_ipv6_loopback_connect(self):
        """Connect to ::1 if IPv6 is available, skip otherwise."""
        try:
            server = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        except OSError:
            pytest.skip("IPv6 not available")
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("::1", 0))
            server.listen(1)
            port = server.getsockname()[1]

            client = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            try:
                client.connect(("::1", port))
            finally:
                client.close()
        finally:
            server.close()

    def test_getaddrinfo_none_passive(self):
        """getaddrinfo(None, ...) is passive (bind) and must be allowed."""
        result = socket.getaddrinfo(None, 0, socket.AF_INET, socket.SOCK_STREAM)
        assert len(result) > 0


_has_af_unix = hasattr(socket, "AF_UNIX")


@pytest.mark.skipif(not _has_af_unix, reason="AF_UNIX not available (Windows)")
class TestGuardAllowsUnixSockets:
    """AF_UNIX sockets must always work (local IPC, no network)."""

    def test_unix_socketpair(self):
        """socket.socketpair(AF_UNIX) works through the guard."""
        s1, s2 = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            s1.sendall(b"hello")
            assert s2.recv(5) == b"hello"
        finally:
            s1.close()
            s2.close()

    def test_unix_socket_connect(self):
        """Connect to a temp AF_UNIX socket works through the guard."""
        with tempfile.TemporaryDirectory() as tmpdir:
            sock_path = str(Path(tmpdir) / "test.sock")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                server.bind(sock_path)
                server.listen(1)

                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    client.connect(sock_path)
                    # accept on server side to complete handshake
                    conn, _ = server.accept()
                    conn.close()
                finally:
                    client.close()
            finally:
                server.close()


class TestIsLoopbackValidation:
    """_is_loopback must use ipaddress.ip_address for numeric validation."""

    def test_loopback_127_0_0_2_allowed(self):
        """127.0.0.2 is in 127.0.0.0/8 — must be allowed."""
        from tests.rag._netguard import _is_loopback

        assert _is_loopback("127.0.0.2") is True

    def test_loopback_ipv6_allowed(self):
        """::1 is IPv6 loopback — must be allowed."""
        from tests.rag._netguard import _is_loopback

        assert _is_loopback("::1") is True

    def test_subdomain_127_blocked(self):
        """127.1.evil.com is NOT a valid IP — must be blocked."""
        from tests.rag._netguard import _is_loopback

        assert _is_loopback("127.1.evil.com") is False

    def test_guard_blocks_127_subdomain(self):
        """127.1.evil.com must be blocked by the actual conftest guard."""
        with pytest.raises(ConnectionRefusedError, match=GUARD_MSG_PREFIX):
            socket.create_connection(("127.1.evil.com", 80))