"""Minimal async-test fallback for environments without pytest-asyncio."""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
from typing import Any

import pytest


_HAS_PYTEST_ASYNCIO = importlib.util.find_spec("pytest_asyncio") is not None


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
