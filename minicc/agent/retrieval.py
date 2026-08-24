"""Deterministic bounded local evidence retrieval.

This intentionally indexes filenames, symbols and test failures only. It is a
small context aid, not a vector database and never reads secret files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", "output", "tmp", "data", ".minicc"}
TEXT_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".json", ".md", ".yaml", ".yml"}
SYMBOL_RE = re.compile(r"^\s*(?:def|class|function)\s+([A-Za-z_][\w]*)", re.M)


@dataclass(frozen=True)
class EvidenceHit:
    path: str
    score: int
    reason: str
    symbols: tuple[str, ...] = ()
    test_failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "score": self.score, "reason": self.reason, "symbols": list(self.symbols), "test_failures": list(self.test_failures)}


class LocalEvidenceIndex:
    def __init__(self, workspace: Path, *, max_files: int = 240, max_bytes: int = 900_000) -> None:
        self.workspace = workspace.resolve()
        self.max_files = max(1, max_files)
        self.max_bytes = max(10_000, max_bytes)

    def search(self, query: str, *, limit: int = 8) -> list[EvidenceHit]:
        terms = {term.casefold() for term in re.findall(r"[A-Za-z_][\w.-]{2,}|[\u4e00-\u9fff]{2,}", str(query or ""))}
        if not terms:
            return []
        hits: list[EvidenceHit] = []
        for path in self._files():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            relative = path.relative_to(self.workspace).as_posix()
            haystack = f"{relative}\n{text[:self.max_bytes]}".casefold()
            matched = sorted(term for term in terms if term in haystack)
            if not matched:
                continue
            symbols = tuple(SYMBOL_RE.findall(text[:self.max_bytes])[:8])
            failures = tuple(re.findall(r"(?:FAILED|ERROR)\s+([\w./:-]+)", text[:self.max_bytes], re.I)[:6])
            score = len(matched) + (2 if any(term in relative.casefold() for term in terms) else 0) + (1 if failures else 0)
            hits.append(EvidenceHit(relative, score, "path" if score > len(matched) else "content", symbols, failures))
        hits.sort(key=lambda hit: (-hit.score, hit.path))
        return hits[: max(1, min(20, limit))]

    def _files(self):
        count = 0
        for path in self.workspace.rglob("*"):
            if count >= self.max_files:
                break
            if not path.is_file() or path.suffix.casefold() not in TEXT_SUFFIXES or path.name in {".env", ".env.local"}:
                continue
            try:
                relative_parts = path.relative_to(self.workspace).parts
            except ValueError:
                continue
            if any(part in SKIP_DIRS for part in relative_parts):
                continue
            count += 1
            yield path


__all__ = ["EvidenceHit", "LocalEvidenceIndex"]
