"""Behavior checks for change summaries, scoped verification and HTTP assets."""
from pathlib import Path
from types import SimpleNamespace
import gzip
import json
import subprocess
import threading
import http.client

import pytest

from minicc.changes import ChangeInspector
from minicc.agent.verification_plan import build_verification_plan, VerificationCommand
from minicc.agent.verifier import Verifier
from minicc.static_assets import asset_response


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_summary_batches_git_and_preserves_unicode_rename_and_changes(tmp_path):
    git(tmp_path, "init")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    (tmp_path / "原文件 name.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fixture")
    git(tmp_path, "mv", "原文件 name.txt", "目标 name.txt")
    (tmp_path / "目标 name.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("new\n", encoding="utf-8")
    inspector = ChangeInspector(tmp_path)
    original = inspector._git
    calls = []
    def capture(args):
        calls.append(args[0])
        return original(args)
    inspector._git = capture
    result = {item["path"]: item for item in inspector.files()}
    assert result["目标 name.txt"]["additions"] == 1
    assert result["目标 name.txt"]["deletions"] == 0
    assert result["new.txt"]["additions"] == 1
    assert calls.count("show") == 0
    assert len(calls) == 3
    assert inspector.diff("目标 name.txt")["additions"] == 1
    (tmp_path / "new.txt").write_text("new\nsecond\n", encoding="utf-8")
    assert next(item for item in inspector.files() if item["path"] == "new.txt")["additions"] == 2


def test_verification_selects_related_checks_and_invalidates_dependencies(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text("value = 1\n")
    (tmp_path / "dependency.py").write_text("value = 1\n")
    (tmp_path / "tests/test_app.py").write_text("import app\n")
    (tmp_path / "tests/test_unrelated.py").write_text("assert True\n")
    plan = build_verification_plan(tmp_path, ["app.py"])
    assert "tests/test_app.py" in plan.commands[0].command
    assert "test_unrelated" not in plan.commands[0].command
    calls = []
    def run(command, *_):
        calls.append(command)
        return SimpleNamespace(status="ok", exit_code=0, render=lambda: "passed")
    verifier = Verifier(run)
    assert verifier.run(tmp_path, plan=plan).passed
    assert verifier.run(tmp_path, plan=plan).cached
    assert len(calls) == 1
    (tmp_path / "dependency.py").write_text("value = 2\n")
    changed = build_verification_plan(tmp_path, ["app.py"])
    assert changed.fingerprint != plan.fingerprint
    assert not verifier.run(tmp_path, plan=changed).cached
    assert build_verification_plan(tmp_path, ["README.md"]).commands == []


def test_unborn_summary_uses_current_content_after_staging(tmp_path):
    git(tmp_path, "init")
    staged = tmp_path / "staged.txt"
    removed = tmp_path / "removed.txt"
    staged.write_text("one\n", encoding="utf-8")
    removed.write_text("removed\n", encoding="utf-8")
    git(tmp_path, "add", ".")
    staged.write_text("one\ntwo\n", encoding="utf-8")
    removed.unlink()
    inspector = ChangeInspector(tmp_path)
    results = {item["path"]: item for item in inspector.files()}
    assert results["staged.txt"]["additions"] == 2
    assert results["removed.txt"]["additions"] == 0
    assert results["staged.txt"]["additions"] == inspector.diff("staged.txt")["additions"]


def test_verification_runs_all_commands_and_preserves_failure(tmp_path):
    calls = []
    def execute(command, *_):
        calls.append(command)
        failed = "test_bad" in command
        return SimpleNamespace(status="error" if failed else "ok", exit_code=int(failed), render=lambda: "FAILED tests/test_bad.py::test_case" if failed else "ok")
    result = Verifier(execute).run(tmp_path, [VerificationCommand("python -m pytest tests/test_bad.py -q"), VerificationCommand("node --check app.js", "syntax")])
    assert len(calls) == 2 and result.status == "failed"
    assert len(result.checks) == 2
    json.dumps(result.to_dict())


def test_frontend_plan_requires_script_authorization(tmp_path):
    (tmp_path / "app.js").write_text("const x = 1;")
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"check:web": "node build.mjs --check", "typecheck": "tsc --noEmit"}}))
    plan = build_verification_plan(tmp_path, ["app.js"])
    assert {c.command for c in plan.commands} == {"npm run check:web", "npm run typecheck", 'node --check "app.js"'}
    executor = lambda *_: SimpleNamespace(status="ok", exit_code=0, render=lambda: "ok")
    verifier = Verifier(executor)
    assert verifier.run(tmp_path, plan=plan, allow_project_scripts=True).passed
    assert verifier.run(tmp_path, plan=plan).status == "blocked"


def test_nested_rules_and_jsx_or_fixture_edits_invalidate_cache(tmp_path):
    (tmp_path / "web/src").mkdir(parents=True)
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc/verification.json").write_text(json.dumps({"rules": [{"paths": ["web/**", "fixtures/**"], "commands": ["node --check web/src/app.jsx"]}]}))
    target = tmp_path / "web/src/app.jsx"
    target.write_text("export const value = 1;")
    before = build_verification_plan(tmp_path, ["web/src/app.jsx"])
    assert before.commands
    target.write_text("export const value = 2;")
    after = build_verification_plan(tmp_path, ["web/src/app.jsx"])
    assert after.fingerprint != before.fingerprint
    (tmp_path / "fixtures").mkdir()
    fixture = tmp_path / "fixtures/data.txt"
    fixture.write_text("first")
    before = build_verification_plan(tmp_path, ["fixtures/data.txt"])
    fixture.write_text("next")
    assert before.fingerprint != build_verification_plan(tmp_path, ["fixtures/data.txt"]).fingerprint


def test_versioned_assets_have_compression_etag_and_html_revalidation(tmp_path):
    (tmp_path / "assets").mkdir()
    name = "assets/app.1234567890abcdef.js"
    (tmp_path / name).write_text("const x = 1;\n" * 500)
    (tmp_path / "asset-manifest.json").write_text(json.dumps({"/app.js": "/" + name}))
    (tmp_path / "index.html").write_text('<script src="/app.js"></script>')
    html, headers = asset_response(tmp_path, "index.html")
    assert name.encode() in html and headers["Cache-Control"] == "no-cache"
    body, headers = asset_response(tmp_path, name, accept_gzip=True)
    assert gzip.decompress(body) == (tmp_path / name).read_bytes()
    assert "immutable" in headers["Cache-Control"]
    assert headers["Content-Encoding"] == "gzip"
    _, alias = asset_response(tmp_path, "app.js")
    assert alias["Cache-Control"] == "no-cache"
    with pytest.raises(FileNotFoundError):
        asset_response(tmp_path, "../outside.txt")


def test_http_asset_conditional_request_and_fractional_gzip(monkeypatch, tmp_path):
    from minicc import webserver
    (tmp_path / "styles.css").write_text("body { color: black; }\n" * 200)
    monkeypatch.setattr(webserver, "STATIC_ROOT", tmp_path)
    server = webserver.MiniccHTTPServer(("127.0.0.1", 0), SimpleNamespace(config=SimpleNamespace(max_concurrent_tasks=1)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    try:
        connection.request("GET", "/styles.css", headers={"Accept-Encoding": "gzip;q=0.5"})
        response = connection.getresponse()
        assert response.status == 200
        assert response.getheader("Content-Encoding") == "gzip"
        tag = response.getheader("ETag")
        assert gzip.decompress(response.read()) == (tmp_path / "styles.css").read_bytes()
        connection.request("GET", "/styles.css", headers={"Accept-Encoding": "gzip;q=0.5", "If-None-Match": tag})
        response = connection.getresponse()
        assert response.status == 304 and response.read() == b""
        connection.request("GET", "/styles.css", headers={"Accept-Encoding": "gzip;q=0"})
        response = connection.getresponse()
        assert response.status == 200 and response.getheader("Content-Encoding") is None
        assert response.read() == (tmp_path / "styles.css").read_bytes()
    finally:
        connection.close()
        server.shutdown()
        server.server_close()
        thread.join(3)
