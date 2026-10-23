"""The request-failed log line must have exactly one home."""

from __future__ import annotations

import logging
import pathlib

from minicc.webserver import MiniccRequestHandler

REPO = pathlib.Path(__file__).resolve().parents[1]


class _Handler:
    path = "/api/tasks"

    _log_request_failed = MiniccRequestHandler._log_request_failed


def test_home_logs_info_for_a_4xx(caplog):
    with caplog.at_level(logging.INFO, logger="minicc.web"):
        _Handler()._log_request_failed(404, "invalid_request", "not found", None)
    record = next(r for r in caplog.records if "request_failed" in r.getMessage())
    assert record.levelno == logging.INFO
    assert "status=404 code=invalid_request path=/api/tasks detail=not found" in record.getMessage()


def test_home_logs_error_with_traceback_for_a_5xx(caplog):
    with caplog.at_level(logging.INFO, logger="minicc.web"):
        _Handler()._log_request_failed(500, "internal", "boom", RuntimeError("x"))
    record = next(r for r in caplog.records if "request_failed" in r.getMessage())
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None
    assert "status=500 code=internal path=/api/tasks detail=boom" in record.getMessage()


def test_home_truncates_the_detail():
    _Handler()._log_request_failed(400, "bad", "x" * 500, None)


def test_census_exactly_one_line_and_it_is_the_home():
    marker = "request_failed status=%s code=%s path=%s detail=%s"
    hits = []
    for path in sorted((REPO / "minicc").rglob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if marker in line:
                hits.append((path.relative_to(REPO).as_posix(), lineno))
    assert len(hits) == 1, hits
    path, lineno = hits[0]
    assert path == "minicc/webserver.py"
    source = (REPO / path).read_text(encoding="utf-8")
    lines = source.splitlines()
    window = "\n".join(lines[max(0, lineno - 14):lineno + 2])
    assert "def _log_request_failed" in window, window


def test_call_sites_use_the_home():
    source = (REPO / "minicc" / "webserver.py").read_text(encoding="utf-8")
    assert source.count("_log_request_failed(") == 2
