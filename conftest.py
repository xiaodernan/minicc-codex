"""Minimal async-test fallback for environments without pytest-asyncio."""

from __future__ import annotations

import asyncio
import faulthandler
import importlib.util
import inspect
import os
import sys
import threading
import time
from typing import Any

import pytest


_HAS_PYTEST_ASYNCIO = importlib.util.find_spec("pytest_asyncio") is not None


# --- M8-T50: a stuck or overrunning test is reported, not silently swallowed --
#
# Measured in this repository: nothing else times a single test (no pytest-timeout, no
# pyproject timeout, the async hook here does not time anything), so a test that stops
# returning stalled the whole run with no information - while the ``elapsed`` bounds
# inside tests were credited with catching that.  They cannot: an assertion never runs
# on a line that is never reached (M8-T45, boundary 3).
#
# A first attempt used ``faulthandler.dump_traceback_later(limit, exit=True)``.  It does
# stop the hang, but under Windows + pytest the process dies as an access violation and
# the run loses its whole report: turning a hang into a crash is not a gate (that
# measurement is recorded under M8-T50).  The two jobs are therefore split - the timer
# only *prints* the stack of a test still running at the bound, and the failure is
# asserted from pytest's own measured duration, so the run keeps its report either way.

DEFAULT_HANG_LIMIT_SECONDS = 900.0


def hang_limit_seconds():
    """Seconds before a test counts as overrunning; ``None`` switches the watchdog off.

    Absent means the default.  Present but empty, unparsable, zero or negative means
    **off**: the switch was touched, so inventing a number for the caller is exactly the
    silent reinterpretation M8-T22 was about.
    """
    raw = os.environ.get("MINICC_TEST_HANG_LIMIT")
    if raw is None:
        return DEFAULT_HANG_LIMIT_SECONDS
    try:
        value = float(raw.strip() or "nan")
    except ValueError:
        return None
    return value if value > 0 else None


def dump_stuck_stack(limit: float, state: dict) -> None:
    if state.get("done"):
        return
    state["done"] = True
    sys.stderr.write(
        "\nMINICC_TEST_HANG_LIMIT: a test is still running after "
        + format(limit, ".1f")
        + "s; dumping its stack (it is reported as failed if it ever returns)\n"
    )
    sys.stderr.flush()
    faulthandler.dump_traceback(file=sys.stderr, all_threads=True)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_protocol(item, nextitem):
    """Arm the stack dump for one test and cancel it when that test comes back."""
    limit = hang_limit_seconds()
    if limit is None:
        return (yield)
    state = {"done": False}
    timer = threading.Timer(limit, dump_stuck_stack, args=(limit, state))
    timer.daemon = True
    timer.start()
    try:
        return (yield)
    finally:
        timer.cancel()
        state["done"] = True


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_runtest_makereport(item, call):
    """Fail a test whose call phase outlived the bound, using pytest's own measurement."""
    report = (yield)
    limit = hang_limit_seconds()
    if limit is not None and report.when == "call" and report.passed and report.duration > limit:
        report.outcome = "failed"
        report.longrepr = (
            "MINICC_TEST_HANG_LIMIT: this test took "
            + format(report.duration, ".1f")
            + "s, over the "
            + format(limit, ".0f")
            + "s bound. Before this hook, a test that stopped returning stalled the whole"
            " run silently (M8-T45 boundary 3)."
        )
    return report


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
