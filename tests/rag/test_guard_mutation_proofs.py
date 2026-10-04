"""Mutation proof script for the network guard.

Run from the repo root:
    python tests/rag/test_guard_mutation_proofs.py

Produces output showing:
1. Removing the connect patch -> outbound test fails (guard doesn't block)
2. Reintroducing address[0] unpack -> loopback test fails (ValueError)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
CONFTEST = REPO_ROOT / "tests" / "rag" / "conftest.py"
TEST_FILE = REPO_ROOT / "tests" / "rag" / "test_network_guard.py"


def _run_test(test_name: str, conftest_content: str, tmpdir: Path) -> tuple[int, str]:
    """Write modified conftest and run a single test, returning (returncode, output)."""
    tmp_conf = tmpdir / "conftest.py"
    tmp_conf.write_text(conftest_content, encoding="utf-8")
    tmp_test = tmpdir / "test_network_guard.py"
    shutil.copy(TEST_FILE, tmp_test)

    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(tmp_test) + "::" + test_name, "-v", "--no-header", "-q", "--timeout=30"],
        capture_output=True, text=True, timeout=120,
        cwd=str(tmpdir),
    )
    return result.returncode, result.stdout + result.stderr


def main():
    original = CONFTEST.read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # === Mutation 1: Remove connect patch ===
        print("=" * 60)
        print("MUTATION 1: Remove socket.connect patch (comment out monkeypatch line)")
        print("=" * 60)
        mutated1 = original.replace(
            '    monkeypatch.setattr(socket.socket, "connect", _fail_socket_connect)',
            '    # MUTATION: removed connect patch\n    pass',
        )
        # Also need to keep connect_ex patched but connect unpatched
        # The test_socket_connect_blocked test uses sock.connect(), so removing
        # just that patch should make it fail (the real connect runs, no guard error)
        rc1, out1 = _run_test(
            "TestGuardBlocksOutbound::test_socket_connect_blocked",
            mutated1, tmpdir_path,
        )
        print(f"  Return code: {rc1}")
        if rc1 != 0:
            print("  [OK] CONFIRMED: test FAILS when connect patch is removed (guard not applied)")
        else:
            print("  [!!] UNEXPECTED: test still passes without connect patch")
        # Show the relevant failure line
        for line in out1.splitlines():
            if "FAILED" in line or "PASSED" in line or "Error" in line or "assert" in line.lower():
                print(f"    {line}")

        # === Mutation 2: Reintroduce address[0] unpack ===
        print()
        print("=" * 60)
        print("MUTATION 2: Reintroduce 'host, port = address[0]' unpack bug")
        print("=" * 60)
        mutated2 = original.replace(
            "def _fail_socket_connect(self, address, *args, **kwargs):\n"
            "        # AF_UNIX sockets are always allowed (local IPC, no network)\n"
            "        if _has_af_unix and self.family == socket.AF_UNIX:\n"
            "            return _real_socket_connect(self, address, *args, **kwargs)\n"
            "        host, port = _extract_host_port(address, self.family)",
            "def _fail_socket_connect(self, address, *args, **kwargs):\n"
            "        # MUTATION: reintroduce address[0] unpack bug\n"
            "        host, port = address[0]",
        )
        rc2, out2 = _run_test(
            "TestGuardAllowsLoopback::test_loopback_connect",
            mutated2, tmpdir_path,
        )
        print(f"  Return code: {rc2}")
        if rc2 != 0:
            print("  [OK] CONFIRMED: loopback test FAILS with address[0] unpack bug")
        else:
            print("  [!!] UNEXPECTED: loopback test still passes with address[0] unpack")
        for line in out2.splitlines():
            if "FAILED" in line or "PASSED" in line or "ValueError" in line or "Error" in line:
                print(f"    {line}")

        print()
        print("=" * 60)
        print("MUTATION PROOFS COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    main()