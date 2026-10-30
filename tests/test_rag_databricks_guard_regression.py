"""Regression tests for the databricks.connect sys.modules pollution guard.

``tests/rag/test_zz_isolation.py`` must reject a leaked MagicMock for
``databricks.connect`` without raising when a real (or absent) module is
restored.  The original guard evaluated ``__import__("unittest.mock").MagicMock``,
which resolves to the top-level ``unittest`` package and therefore raises
``AttributeError`` as soon as the real module is present.

Each case installs the module in ``sys.modules`` temporarily and restores the
previous entry (or removes the entry again when it was absent) so other tests
and fixtures keep the modules they registered.
"""
import sys
import types
from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from tests.rag.test_zz_isolation import test_databricks_connect_not_polluted as guard_check

_MODULE = "databricks.connect"
_MISSING = object()


@contextmanager
def _temporary_module(name, module):
    """Install ``module`` under ``name`` and restore the previous state."""
    previous = sys.modules.get(name, _MISSING)
    if module is None:
        sys.modules.pop(name, None)
    else:
        sys.modules[name] = module
    try:
        yield
    finally:
        if previous is _MISSING:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous


def test_guard_accepts_absent_module():
    """No databricks.connect in sys.modules must not raise."""
    with _temporary_module(_MODULE, None):
        assert _MODULE not in sys.modules
        guard_check()
        assert _MODULE not in sys.modules


def test_guard_accepts_real_module():
    """A real databricks.connect module must not raise AttributeError."""
    real = types.ModuleType(_MODULE)
    with _temporary_module(_MODULE, real):
        assert sys.modules[_MODULE] is real
        guard_check()
    assert sys.modules.get(_MODULE) is not real


def test_guard_rejects_magicmock_module():
    """A leaked MagicMock databricks.connect must still fail the guard."""
    leaked = MagicMock()
    with _temporary_module(_MODULE, leaked):
        assert sys.modules[_MODULE] is leaked
        with pytest.raises(AssertionError, match="still a MagicMock"):
            guard_check()
    assert sys.modules.get(_MODULE) is not leaked


def test_guard_preserves_preexisting_real_module():
    """A previously registered real module must survive the temporary swap."""
    previous = types.ModuleType(_MODULE)
    with _temporary_module(_MODULE, previous):
        replacement = types.ModuleType(_MODULE)
        with _temporary_module(_MODULE, replacement):
            assert sys.modules[_MODULE] is replacement
            guard_check()
        assert sys.modules[_MODULE] is previous
    assert sys.modules.get(_MODULE) is not previous
