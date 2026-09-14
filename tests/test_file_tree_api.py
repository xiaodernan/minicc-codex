"""Workspace file-tree API tests (/api/files)."""

from __future__ import annotations

import json
import threading
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from minicc.web import AgentService, MiniccHTTPServer
from minicc.webauth import WebAuth


def _service(tmp_path: Path) -> AgentService:
    config = types.SimpleNamespace(
        yolo=False,
        max_concurrent_tasks=2,
        sandbox_mode="host",
        sandbox_image="python:3.11-slim",
        base_url="https://example.test/v1",
        api_key="test-key",
        model="test-model",
        timeout=10,
        tool_mode="auto",
        reasoning_effort="high",
        max_turns=4,
        compact_threshold=300_000,
        context_window_tokens=300_000,
    )
    return AgentService(tmp_path, config)


def _make_workspace(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')", encoding="utf-8")
    (tmp_path / "src" / "deep").mkdir()
    (tmp_path / "src" / "deep" / "inner.py").write_text("x=1", encoding="utf-8")
    (tmp_path / "README.md").write_text("readme", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("x", encoding="utf-8")
    (tmp_path / ".minicc").mkdir()
    (tmp_path / ".minicc" / "secret.json").write_text("{}", encoding="utf-8")


def test_file_tree_lists_and_skips_dirs(tmp_path: Path) -> None:
    _make_workspace(tmp_path)
    service = _service(tmp_path)
    try:
        tree = service.file_tree("", depth=3)
        paths = {entry["path"] for entry in tree["entries"]}
        assert "README.md" in paths
        assert "src/app.py" in paths
        assert tree["truncated"] is False
        # Skip rules and size metadata.
        names = {entry["name"] for entry in tree["entries"]}
        assert "node_modules" not in names
        assert ".minicc" not in names
        app_entry = next(entry for entry in tree["entries"] if entry["path"] == "src/app.py")
        assert app_entry["type"] == "file"
        assert app_entry["size"] == len("print('hi')")
        dirs = [entry for entry in tree["entries"] if entry["type"] == "dir"]
        assert any(entry["path"] == "src" for entry in dirs)
    finally:
        service.shutdown()


def test_file_tree_depth_and_subpath(tmp_path: Path) -> None:
    _make_workspace(tmp_path)
    service = _service(tmp_path)
    try:
        shallow = service.file_tree("", depth=1)
        assert all(not entry["path"].startswith("src/deep/") for entry in shallow["entries"])

        subtree = service.file_tree("src", depth=2)
        assert subtree["path"] == "src"
        # Paths stay workspace-root-relative so they match /api/file & /api/diff.
        assert "src/app.py" in {entry["path"] for entry in subtree["entries"]}
        assert "src/deep/inner.py" in {entry["path"] for entry in subtree["entries"]}
    finally:
        service.shutdown()


def test_file_tree_rejects_escape_and_files(tmp_path: Path) -> None:
    _make_workspace(tmp_path)
    service = _service(tmp_path)
    try:
        with pytest.raises(ValueError, match="越界"):
            service.file_tree("../outside")
        with pytest.raises(ValueError, match="不是目录"):
            service.file_tree("README.md")
    finally:
        service.shutdown()


class _Server:
    def __init__(self, service: AgentService) -> None:
        self.server = MiniccHTTPServer(("127.0.0.1", 0), service, auth=WebAuth("t", required=False))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def test_files_route_over_http(tmp_path: Path) -> None:
    _make_workspace(tmp_path)
    service = _service(tmp_path)
    server = _Server(service)
    try:
        with urllib.request.urlopen(f"{server.url}/api/files?depth=2", timeout=5) as response:
            payload = json.loads(response.read())
        assert payload["path"] == ""
        assert any(entry["path"] == "src/app.py" for entry in payload["entries"])

        request = urllib.request.Request(f"{server.url}/api/files?path=../outside")
        try:
            urllib.request.urlopen(request, timeout=5)
            raise AssertionError("expected 400")
        except urllib.error.HTTPError as exc:
            assert exc.code == 400
    finally:
        server.shutdown()
        service.shutdown()
