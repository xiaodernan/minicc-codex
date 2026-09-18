"""Versioned local assets with bounded compression cache and ETag validation."""
from __future__ import annotations

import gzip
import hashlib
import json
import mimetypes
import re
import threading
from collections import OrderedDict
from pathlib import Path

_CACHE: OrderedDict[tuple[str, int, int, bool], tuple[bytes, str]] = OrderedDict()
_LOCK = threading.Lock()


def asset_response(root: Path, relative: str, *, accept_gzip: bool = False) -> tuple[bytes, dict[str, str]]:
    root = root.resolve()
    manifest_path = root / "asset-manifest.json"
    manifest = {}
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    requested = relative or "index.html"
    # Aliases support dynamic optional panels and old bookmarks. They always
    # revalidate; only content-addressed URLs may be immutable.
    relative = str(manifest.get("/" + requested, "/" + requested)).lstrip("/")
    target = (root / relative).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise FileNotFoundError(relative)
    stat = target.stat()
    html = target.suffix == ".html"
    textual = target.suffix in {".html", ".js", ".css", ".json", ".svg"}
    compressed = accept_gzip and textual and stat.st_size > 1024
    key = (str(target), stat.st_mtime_ns, stat.st_size, compressed)
    with _LOCK:
        cached = None if html else _CACHE.get(key)
    if cached is None:
        content = target.read_bytes()
        if html and manifest:
            text = content.decode("utf-8")
            for original, versioned in manifest.items():
                if (root / str(versioned).lstrip("/")).is_file():
                    text = text.replace(f'"{original}"', f'"{versioned}"')
            content = text.encode("utf-8")
        if compressed:
            content = gzip.compress(content, compresslevel=6, mtime=0)
        etag = '"' + hashlib.sha256(content).hexdigest()[:24] + '"'
        cached = (content, etag)
        if not html:
            with _LOCK:
                _CACHE[key] = cached
                _CACHE.move_to_end(key)
                while len(_CACHE) > 32:
                    _CACHE.popitem(last=False)
    content, etag = cached
    content_type = "text/javascript" if target.suffix == ".js" else mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    if textual:
        content_type += "; charset=utf-8"
    immutable = bool(re.fullmatch(r"assets/[a-zA-Z0-9_-]+\.[a-f0-9]{16}\.(?:js|css)", requested))
    headers = {
        "Content-Type": content_type, "ETag": etag, "Vary": "Accept-Encoding",
        "Cache-Control": "public, max-age=31536000, immutable" if immutable else "no-cache",
        "X-Content-Type-Options": "nosniff",
    }
    if compressed:
        headers["Content-Encoding"] = "gzip"
    return content, headers
