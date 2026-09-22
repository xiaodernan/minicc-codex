"""Minimal async-test fallback for environments without pytest-asyncio."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
from typing import Any

import pytest


_HAS_PYTEST_ASYNCIO = importlib.util.find_spec("pytest_asyncio") is not None


def suite_python() -> str:
    """The interpreter running this suite, quoted for use inside a shell command.

    Tests that author a verification command (``.minicc/verification.json``, a
    bash tool call, a ``VerificationCommand``) must not write a bare ``python``:
    that resolves to whatever the *ambient* PATH offers, which is not
    necessarily the interpreter running the tests. On a machine where the
    ambient ``python`` has no pytest, the agent's verification step fails for an
    environment reason and the test looks like a product regression (observed
    live: ``python -m pytest -q`` exited 1, the loop fell into repair, and the
    task died with "最大模型轮次已用尽"). CI and an activated venv both hide
    this, which is exactly why it is worth pinning here.
    """
    return f'"{sys.executable}"'


@pytest.fixture(scope="session")
def suite_python_bin() -> str:
    """Fixture form of :func:`suite_python` for tests that take fixtures."""
    return suite_python()


def pytest_configure(config: pytest.Config) -> None:
    if not _HAS_PYTEST_ASYNCIO:
        config.addinivalue_line("markers", "asyncio: run an async test function")


def pytest_pyfunc_call(pyfuncitem: pytest.Function) -> bool | None:
    if _HAS_PYTEST_ASYNCIO or not inspect.iscoroutinefunction(pyfuncitem.obj):
        return None
    signature = inspect.signature(pyfuncitem.obj)
    kwargs: dict[str, Any] = {
        name: pyfuncitem.funcargs[name]
        for name in signature.parameters
        if name in pyfuncitem.funcargs
    }
    asyncio.run(pyfuncitem.obj(**kwargs))
    return True
