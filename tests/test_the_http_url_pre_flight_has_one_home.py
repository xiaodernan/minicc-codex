"""The http(s) URL pre-flight must have exactly one home.

``netguard``'s module docstring says it holds the shared SSRF checks for
webfetch and the HTTP MCP transport, and it does - except for the two
checks that run before anything is resolved.  ``webfetch._validate_url``
kept its own copy of the scheme gate and the hostname gate, sentences and
all, so the agent-facing fetch tool and the SSRF guard held separate
opinions about what a legal URL is.

The hostname refusal is the dangerous half: a URL with no hostname is how
a malformed or scheme-relative target reaches a resolver at all, and two
free-to-drift spellings of that sentence meant a grep for it found half
the refusals.

This door pins:

* both sentences are spelled once, in ``netguard``;
* the pre-flight is defined once and is what both callers run;
* webfetch holds no second copy of either check;
* both callers refuse identically, byte for byte.
"""

from __future__ import annotations

import ast
import pathlib

import minicc.netguard as netguard
from minicc.netguard import assert_public_http_url, parse_http_url
from minicc.tools.webfetch import _validate_url

REPO = pathlib.Path(__file__).resolve().parents[1]
HOME = "minicc/netguard.py"

SENTENCES = ("仅支持 http/https URL: ", "URL 缺少主机名: ")


def _trees():
    for path in sorted((REPO / "minicc").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path, ast.parse(path.read_bytes().decode("utf-8"))


def _carriers(needle: str) -> list[str]:
    """Every string constant carrying the needle - f-string parts included."""
    hits = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if needle in node.value:
                    hits.append(f"{path.relative_to(REPO).as_posix()}:{node.lineno}")
    return hits


def test_the_pre_flight_accepts_an_http_url():
    parsed = parse_http_url("http://example.com/a?b=c")
    assert parsed.scheme == "http"
    assert parsed.hostname == "example.com"


def test_the_pre_flight_refuses_a_scheme_outside_the_vocabulary():
    for url in ("ftp://example.com/", "file:///etc/passwd", "gopher://x/"):
        try:
            parse_http_url(url)
        except ValueError as exc:
            assert "仅支持 http/https URL: " in str(exc), str(exc)
        else:  # pragma: no cover - the guard must fire
            raise AssertionError(f"{url} was accepted")


def test_the_pre_flight_refuses_a_url_with_no_hostname():
    for url in ("http://", "https://", "http:///path"):
        try:
            parse_http_url(url)
        except ValueError as exc:
            assert "URL 缺少主机名: " in str(exc), str(exc)
        else:  # pragma: no cover - the guard must fire
            raise AssertionError(f"{url} was accepted")


def test_each_sentence_is_spelled_in_exactly_one_place():
    for needle in SENTENCES:
        hits = _carriers(needle)
        assert len(hits) == 1, (needle, hits)
        assert hits[0].startswith(f"{HOME}:"), (needle, hits)


def test_no_other_constant_starts_with_a_sentence():
    """A near-miss spelling is the drift; containment alone cannot see it.

    ``"URL 缺少主机名:  "`` (one space too many) still *contains* the needle,
    so a containment census waves it through - and it is exactly the shape
    a hand-written copy takes.  Judging on the head catches it.
    """
    for needle in SENTENCES:
        strays = []
        for path, tree in _trees():
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    if node.value.startswith(needle) and node.value != needle:
                        strays.append((path.as_posix(), node.lineno, node.value[:50]))
        assert strays == [], (needle, strays)


def test_the_sentences_are_exactly_what_both_paths_emit():
    """Byte-level pins: the sentence is the contract, not just its head."""
    try:
        parse_http_url("http://")
    except ValueError as exc:
        assert str(exc) == "URL 缺少主机名: 'http://'", str(exc)
    else:  # pragma: no cover - the guard must fire
        raise AssertionError("a hostname-less URL was accepted")
    try:
        parse_http_url("ftp://example.com/")
    except ValueError as exc:
        assert str(exc) == "仅支持 http/https URL: 'ftp://example.com/'", str(exc)
    else:  # pragma: no cover - the guard must fire
        raise AssertionError("a non-http scheme was accepted")


def test_the_pre_flight_is_defined_exactly_once():
    definitions = []
    for path, tree in _trees():
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "parse_http_url":
                definitions.append(path.relative_to(REPO).as_posix())
    assert definitions == [HOME], definitions


def test_webfetch_holds_no_second_copy_of_either_check():
    """The defect: a second scheme gate and a second hostname gate."""
    for path, tree in _trees():
        rel = path.relative_to(REPO).as_posix()
        if rel == "minicc/tools/webfetch.py":
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare) and isinstance(node.left, ast.Attribute) \
                        and node.left.attr == "scheme":
                    raise AssertionError(f"{rel}:{node.lineno} re-runs the scheme gate")
                if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not) \
                        and isinstance(node.operand, ast.Attribute) \
                        and node.operand.attr == "hostname":
                    raise AssertionError(f"{rel}:{node.lineno} re-runs the hostname gate")


def test_webfetch_calls_the_home_rather_than_reimplementing_it():
    from minicc.tools.webfetch import parse_http_url as webfetch_pre_flight

    assert webfetch_pre_flight is netguard.parse_http_url


def test_both_callers_refuse_identically():
    """The two paths must produce the same sentence for the same URL."""
    for url in ("ftp://example.com/", "http://", "file:///etc/passwd", "https://"):
        webfetch_error = _refusal(lambda: _validate_url(url))
        netguard_error = _refusal(
            lambda: assert_public_http_url(url, allow_env="MINICC_ALLOW_PRIVATE_FETCH")
        )
        assert webfetch_error == netguard_error, (url, webfetch_error, netguard_error)


def _refusal(call):
    try:
        call()
    except ValueError as exc:
        return str(exc)
    raise AssertionError("no refusal")
