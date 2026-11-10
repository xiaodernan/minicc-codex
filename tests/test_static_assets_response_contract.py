"""M8-T760 — ``minicc/static_assets.asset_response`` 的可测试契约。

这个函数是浏览器静态资产的唯一出口，逻辑不涉及网络、进程或时钟——
它只读文件、哈希、gzip。它和 M8-T292 留下的注释一起承诺：

1. 找不到文件或路径逃逸 → ``FileNotFoundError``；
2. ``.js`` → ``text/javascript; charset=utf-8``；
3. ETag 稳定（两次调用一致）；
4. 大 `.js` + ``accept_gzip=True`` → gzip payload + ``Content-Encoding: gzip``；
5. 内容寻址的 ``assets/<name>.<16-hex>.js|css`` → immutable 长缓存，
   否则 ``no-cache``；
6. ``asset-manifest.json`` 存在时，html 里的原始资产名被改写成
   清单里的版本化名字。
"""

from __future__ import annotations

import gzip
import hashlib
import json

import pytest

from minicc import static_assets


def _write(root, name, body: bytes):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


def test_missing_file_raises_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        static_assets.asset_response(tmp_path, "nope.css")


def test_path_traversal_is_refused(tmp_path):
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        static_assets.asset_response(tmp_path, "../secret.txt")


def test_js_content_type_is_text_javascript(tmp_path):
    _write(tmp_path, "app.js", b"console.log(1)")
    body, headers = static_assets.asset_response(tmp_path, "app.js")
    assert headers["Content-Type"] == "text/javascript; charset=utf-8"
    assert body == b"console.log(1)"


def test_etag_is_stable_across_calls(tmp_path):
    _write(tmp_path, "app.js", b"console.log(1)\n")
    _, h1 = static_assets.asset_response(tmp_path, "app.js")
    _, h2 = static_assets.asset_response(tmp_path, "app.js")
    assert h1["ETag"] == h2["ETag"]
    expected = '"' + hashlib.sha256(b"console.log(1)\n").hexdigest()[:24] + '"'
    assert h1["ETag"] == expected


def test_gzip_kicks_in_for_textual_over_1kb(tmp_path):
    payload = b"/* comment */\n" * 100  # > 1024 bytes, textual
    _write(tmp_path, "big.js", payload)
    body, headers = static_assets.asset_response(tmp_path, "big.js", accept_gzip=True)
    assert headers.get("Content-Encoding") == "gzip"
    assert gzip.decompress(body) == payload


def test_no_gzip_for_small_or_binary(tmp_path):
    payload = b"console.log(1)"
    _write(tmp_path, "small.js", payload)
    body, headers = static_assets.asset_response(tmp_path, "small.js", accept_gzip=True)
    assert "Content-Encoding" not in headers
    assert body == payload


def test_content_addressed_asset_gets_immutable_cache(tmp_path):
    name = "assets/app.0123456789abcdef.js"
    _write(tmp_path, name, b"console.log(1)")
    _, headers = static_assets.asset_response(tmp_path, name)
    assert "immutable" in headers["Cache-Control"]
    assert headers["Cache-Control"].startswith("public, max-age=31536000")


def test_plain_asset_gets_no_cache(tmp_path):
    _write(tmp_path, "styles.css", b"body{}")
    _, headers = static_assets.asset_response(tmp_path, "styles.css")
    assert headers["Cache-Control"] == "no-cache"


def test_manifest_rewrites_versions_in_html(tmp_path):
    _write(tmp_path, "assets/app.0123456789abcdef.js", b"console.log(1)")
    (tmp_path / "asset-manifest.json").write_text(
        json.dumps({"/assets/app.js": "/assets/app.0123456789abcdef.js"}),
        encoding="utf-8",
    )
    _write(tmp_path, "index.html", b'<script src="/assets/app.js"></script>')
    body, _ = static_assets.asset_response(tmp_path, "index.html")
    assert b"app.0123456789abcdef.js" in body


def test_security_headers_present(tmp_path):
    _write(tmp_path, "app.js", b"console.log(1)")
    _, headers = static_assets.asset_response(tmp_path, "app.js")
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Vary"] == "Accept-Encoding"
