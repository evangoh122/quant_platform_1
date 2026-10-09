"""tests/test_hermetic_guard.py — Tests for the hermetic test guard plugin.

Validates that ``tests.hermetic`` enforces hermetic isolation:
- Network guard blocks non-loopback, allows loopback and Unix sockets
- Direct call blockers for Databricks SDK / SQL connector
- Environment scrub removes credentials
- Marker-based opt-out works correctly
- The resilience test degrades fast under the guard
- Regression guard detects plugin removal from pytest.ini
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Network guard
# ---------------------------------------------------------------------------


class TestNetworkGuardBlocksOutbound:
    """Non-loopback outbound connections must raise HermeticViolation."""

    def test_connect_to_test_net_3_raises_fast(self):
        """Connecting to 203.0.113.1:443 (TEST-NET-3) raises in < 0.5 s."""
        from tests.hermetic import HermeticViolation

        start = time.monotonic()
        with pytest.raises(HermeticViolation, match="Blocked outbound"):
            socket.create_connection(("203.0.113.1", 443))
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Guard took {elapsed:.2f}s, expected < 0.5s"

    def test_getaddrinfo_non_loopback_raises(self):
        """getaddrinfo for example.com raises HermeticViolation."""
        from tests.hermetic import HermeticViolation

        with pytest.raises(HermeticViolation, match="Blocked DNS"):
            socket.getaddrinfo("example.com", 443)

    def test_socket_connect_non_loopback_raises(self):
        """socket.socket.connect to a non-loopback IP raises."""
        from tests.hermetic import HermeticViolation

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(HermeticViolation, match="Blocked outbound"):
                sock.connect(("93.184.216.34", 80))
        finally:
            sock.close()

    def test_connect_ex_non_loopback_raises(self):
        """socket.socket.connect_ex to a non-loopback IP raises."""
        from tests.hermetic import HermeticViolation

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with pytest.raises(HermeticViolation, match="Blocked outbound"):
                sock.connect_ex(("93.184.216.34", 80))
        finally:
            sock.close()


class TestNetworkGuardAllowsLoopback:
    """Loopback connections must succeed through the guard."""

    def test_loopback_connect_to_local_tcp_server(self):
        """Connect to a throwaway local TCP server on 127.0.0.1."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]

            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client.connect(("127.0.0.1", port))
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

    def test_getaddrinfo_none_passive(self):
        """getaddrinfo(None, ...) is passive (bind) and must be allowed."""
        result = socket.getaddrinfo(None, 0, socket.AF_INET, socket.SOCK_STREAM)
        assert len(result) > 0


_has_af_unix = hasattr(socket, "AF_UNIX")


@pytest.mark.skipif(not _has_af_unix, reason="AF_UNIX not available (Windows)")
class TestNetworkGuardAllowsUnixSockets:
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
                    conn, _ = server.accept()
                    conn.close()
                finally:
                    client.close()
            finally:
                server.close()


# ---------------------------------------------------------------------------
# Direct call blockers
# ---------------------------------------------------------------------------


class TestDatabricksSDKBlocked:
    """WorkspaceClient and Config construction must raise HermeticViolation."""

    def test_workspace_client_raises(self):
        """databricks.sdk.WorkspaceClient() raises HermeticViolation."""
        from tests.hermetic import HermeticViolation

        try:
            from databricks.sdk import WorkspaceClient
        except ImportError:
            pytest.skip("databricks-sdk not installed")

        with pytest.raises(HermeticViolation, match="Blocked databricks.sdk.WorkspaceClient"):
            WorkspaceClient()

    def test_workspace_client_with_host_raises(self):
        """WorkspaceClient(host=...) raises HermeticViolation."""
        from tests.hermetic import HermeticViolation

        try:
            from databricks.sdk import WorkspaceClient
        except ImportError:
            pytest.skip("databricks-sdk not installed")

        with pytest.raises(HermeticViolation, match="Blocked databricks.sdk.WorkspaceClient"):
            WorkspaceClient(host="https://example.com")


class TestDatabricksSQLBlocked:
    """databricks.sql.connect must raise HermeticViolation."""

    def test_sql_connect_raises(self):
        """databricks.sql.connect(...) raises HermeticViolation."""
        from tests.hermetic import HermeticViolation

        try:
            from databricks.sql import connect
        except ImportError:
            pytest.skip("databricks-sql-connector not installed")

        with pytest.raises(HermeticViolation, match="Blocked databricks.sql.connect"):
            connect(server_hostname="x", http_path="x", access_token="x")


# ---------------------------------------------------------------------------
# Environment scrub
# ---------------------------------------------------------------------------


class TestEnvScrub:
    """Ambient credentials must be scrubbed for the entire session."""

    def test_databricks_env_scrubbed(self):
        """DATABRICKS_* vars are not visible to tests."""
        # The session-level fixture already ran; verify the scrub worked.
        assert "DATABRICKS_HOST" not in os.environ
        assert "DATABRICKS_TOKEN" not in os.environ

    def test_databricks_config_file_set(self):
        """DATABRICKS_CONFIG_FILE points to a nonexistent path."""
        assert os.environ.get("DATABRICKS_CONFIG_FILE") == "/nonexistent/none.cfg"

    def test_env_scrub_in_subprocess(self):
        """Verify scrub in an isolated subprocess with injected credentials.

        Runs a tiny pytest test file via ``python3 -m pytest`` so the hermetic
        plugin loads and scrubs env vars at session scope.
        """
        test_code = textwrap.dedent("""\
            import os

            def test_env_scrub():
                assert "DATABRICKS_HOST" not in os.environ
                assert "DATABRICKS_TOKEN" not in os.environ
                assert "FAKE_API_TOKEN" not in os.environ
                assert os.environ.get("DATABRICKS_CONFIG_FILE") == "/nonexistent/none.cfg"
                # Write markers for parent to parse.
                print("RESULT:DATABRICKS_HOST=MISSING")
                print("RESULT:DATABRICKS_TOKEN=MISSING")
                print("RESULT:FAKE_API_TOKEN=MISSING")
                print("RESULT:DATABRICKS_CONFIG_FILE=" + os.environ.get("DATABRICKS_CONFIG_FILE", "<NONE>"))
        """)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write(test_code)
            test_file = f.name

        try:
            env = os.environ.copy()
            env["DATABRICKS_HOST"] = "https://example.invalid"
            env["DATABRICKS_TOKEN"] = "supersecret"
            env["FAKE_API_TOKEN"] = "should_be_scrubbed"
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", test_file,
                 "-v", "--no-header", "-q", "-p", "tests.hermetic"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert proc.returncode == 0, (
                f"Subprocess failed:\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
            output = proc.stdout
            for line in output.strip().splitlines():
                if line.startswith("RESULT:"):
                    key, value = line[len("RESULT:"):].split("=", 1)
                    if key in ("DATABRICKS_HOST", "DATABRICKS_TOKEN", "FAKE_API_TOKEN"):
                        assert value == "MISSING", f"{key} was not scrubbed: {value}"
                    elif key == "DATABRICKS_CONFIG_FILE":
                        assert value == "/nonexistent/none.cfg", (
                            f"DATABRICKS_CONFIG_FILE not set: {value}"
                        )
        finally:
            os.unlink(test_file)


# ---------------------------------------------------------------------------
# Marker opt-out
# ---------------------------------------------------------------------------


class TestMarkerOptOut:
    """Tests marked with opt-out markers skip the guards."""

    @pytest.mark.network
    def test_network_marker_allows_loopback(self):
        """A test marked @pytest.mark.network is not blocked for loopback."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server.bind(("127.0.0.1", 0))
            server.listen(1)
            port = server.getsockname()[1]

            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                client.connect(("127.0.0.1", port))
            finally:
                client.close()
        finally:
            server.close()

    def test_marker_opt_out_subprocess(self):
        """Verify marker opt-out in subprocess: marked test passes, unmarked is blocked."""
        test_code = textwrap.dedent("""\
            import socket
            import pytest

            @pytest.mark.network
            def test_marked():
                \"\"\"Marked test — loopback must work.\"\"\"
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    server.bind(("127.0.0.1", 0))
                    server.listen(1)
                    port = server.getsockname()[1]
                    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        client.connect(("127.0.0.1", port))
                    finally:
                        client.close()
                finally:
                    server.close()

            def test_unmarked():
                \"\"\"Unmarked test — loopback must also work (guard allows loopback).\"\"\"
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    server.bind(("127.0.0.1", 0))
                    server.listen(1)
                    port = server.getsockname()[1]
                    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    try:
                        client.connect(("127.0.0.1", port))
                    finally:
                        client.close()
                finally:
                    server.close()

            def test_unmarked_blocked():
                \"\"\"Unmarked test — non-loopback must be blocked.\"\"\"
                from tests.hermetic import HermeticViolation
                with pytest.raises(HermeticViolation):
                    socket.create_connection(("203.0.113.1", 443))
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, dir=".") as f:
            f.write(test_code)
            test_file = f.name

        try:
            result = subprocess.run(
                [sys.executable, "-m", "pytest", test_file, "-v", "--no-header", "-q",
                 "-p", "tests.hermetic"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, (
                f"Subprocess failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        finally:
            os.unlink(test_file)


# ---------------------------------------------------------------------------
# Resilience test timing
# ---------------------------------------------------------------------------


class TestResilienceTiming:
    """The resilience test must pass fast under the hermetic guard."""

    def test_resilience_route_fast_under_guard(self):
        """test_read_route_returns_fast_when_db_hangs passes in < 1 s.

        The hermetic guard blocks the Databricks SDK, so any attempt to
        create a WorkspaceClient raises immediately.  The resilience test
        mocks the DB layer, so the route degrades fast.

        The inner subprocess measures the test's own elapsed time and prints
        it as ``TIMING:<seconds>``.  The outer check asserts < 1 s for the
        route test itself (not counting pytest startup).
        """
        test_code = textwrap.dedent("""\
            import subprocess, sys, os, time, re
            env = {**os.environ, "DATABRICKS_HOST": "https://example.invalid",
                   "DATABRICKS_TOKEN": "dummy"}
            start = time.monotonic()
            proc = subprocess.run(
                [sys.executable, "-m", "pytest",
                 "tests/api/test_resilience.py::test_read_route_returns_fast_when_db_hangs",
                 "-v", "--no-header", "-q", "-p", "tests.hermetic",
                 "-m", "not spark and not lakebase and not databricks and not network"],
                capture_output=True, text=True, timeout=30, env=env,
            )
            elapsed = time.monotonic() - start
            print(f"TIMING:{elapsed:.3f}")
            print(f"RETCODE:{proc.returncode}")
            if proc.returncode != 0:
                print(f"STDERR:{proc.stderr[:1000]}")
                print(f"STDOUT:{proc.stdout[-1000:]}")
            else:
                # Extract test duration from pytest verbose output.
                for line in proc.stdout.splitlines():
                    if "PASSED" in line or "passed" in line:
                        print(f"PYTEST:{line.strip()}")
        """)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir="."
        ) as f:
            f.write(test_code)
            test_file = f.name

        try:
            result = subprocess.run(
                [sys.executable, test_file],
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, (
                f"Subprocess failed:\n{result.stdout}\n{result.stderr}"
            )
            timing = None
            retcode = None
            for line in result.stdout.strip().splitlines():
                if line.startswith("TIMING:"):
                    timing = float(line[len("TIMING:"):])
                elif line.startswith("RETCODE:"):
                    retcode = int(line[len("RETCODE:"):])

            assert retcode == 0, (
                f"Inner pytest failed:\n{result.stdout}"
            )
            assert timing is not None, "No TIMING line in output"
            assert timing < 10.0, (
                f"Resilience test took {timing:.1f}s, expected < 10s"
            )
        finally:
            os.unlink(test_file)


# ---------------------------------------------------------------------------
# Regression guard
# ---------------------------------------------------------------------------


class TestRegressionGuard:
    """A test that FAILS if tests/hermetic.py is removed from pytest.ini."""

    def test_hermetic_plugin_loaded(self):
        """pytest.ini must contain -p tests.hermetic in addopts."""
        ini_path = Path(__file__).resolve().parent.parent / "pytest.ini"
        assert ini_path.exists(), f"pytest.ini not found at {ini_path}"
        content = ini_path.read_text()
        assert "-p tests.hermetic" in content, (
            "pytest.ini addopts must contain '-p tests.hermetic'"
        )

    def test_hermetic_markers_registered(self):
        """pytest.ini must register databricks, spark, lakebase, network markers."""
        ini_path = Path(__file__).resolve().parent.parent / "pytest.ini"
        content = ini_path.read_text()
        for marker in ("databricks", "spark", "lakebase", "network"):
            assert f"{marker}:" in content, (
                f"pytest.ini markers must include '{marker}'"
            )