"""Deterministic bounded local evidence retrieval.

This module intentionally indexes filenames, symbols, guidance notes and test
failure markers only. It is a small context aid, not a vector database:
recall is fully deterministic (token + substring matching against a locally
built snapshot with explicit scoring weights) and credential material is kept
out by name (``is_secret_filename``). A hit is a *pointer* the agent is told to
go and read, so surfacing ``secrets.json`` as the top match for an "api key"
query has the same outcome as indexing its contents — which is why the name
rule exists rather than relying on the text-suffix whitelist to skip dotfiles.

Scoring formula per file (all weights are module-level constants):

    score = W_PATH_PATTERN_EXACT|W_PATH_PATTERN_BASENAME   (query names path/file)
          + W_PATH_PATTERN_EXT                             (query names a suffix)
          + W_GUIDANCE        (guidance file matched; plus a small resident boost)
          + W_FILENAME        (per query term found in the basename)
          + W_PATH_TERM       (per query term found in the relative path)
          + W_SYMBOL          (per query term matched by an extracted symbol)
          + W_CONTENT_TERM    (per query term found in the content)
          + W_TEST_FAILURE    (file carries FAILED/ERROR markers)
          + W_FRESHNESS * 0.5 ** (age_days / FRESHNESS_HALF_LIFE_DAYS)

Query terms come from a mixed-language tokenizer: ASCII words are split on
non-alphanumeric characters and lowercased, CJK runs are reduced to
overlapping character bigrams, a small stopword list is applied, and
file-path patterns (``src/app.py``, ``view.py``, bare ``.py`` suffixes) are
extracted as strong extra signals.
"""

from __future__ import annotations

import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path


SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", "output", "tmp", "data", ".minicc", "dist", "build", "coverage"}
TEXT_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".css", ".html", ".json", ".md", ".yaml", ".yml", ".toml", ".go", ".rs", ".java", ".sql", ".vue", ".svelte"}
SECRET_FILENAMES = {".env", ".env.local"}
#: Basenames (casefolded, no suffix) that hold credentials rather than code.
#: Matched exactly, and only on data files — see ``_SECRET_STORE_SUFFIXES``.
SECRET_STEMS = {"secret", "secrets", "credential", "credentials"}
#: Suffixes that are key material in their own right.
SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx"}
#: A name like ``credentials`` is a credential *store* when it holds data and
#: ordinary code when it holds source. Without this split ``credentials.rs``
#: and ``secrets.go`` would silently vanish from the index — measured, because
#: the boundary test lists them on the allowed side.
_SECRET_STORE_SUFFIXES = {
    "", ".json", ".yaml", ".yml", ".toml", ".ini", ".conf", ".cfg",
    ".properties", ".txt", ".env", ".csv",
}


def is_secret_filename(name: str) -> bool:
    """Would indexing this basename put credential material into the evidence set?

    The index answers *queries with pointers*: it does not copy file contents,
    but a hit tells the agent to go and read that file, and the reason string
    claims its content matched. For a credential store that is the same outcome
    as indexing the store, so these names stay out entirely.
    """
    folded = name.casefold()
    if folded in SECRET_FILENAMES or folded.startswith(".env"):
        return True
    path = Path(folded)
    if path.suffix in SECRET_SUFFIXES:
        return True
    if path.suffix not in _SECRET_STORE_SUFFIXES:
        return False
    return path.stem in SECRET_STEMS or "service-account" in folded or "-api-key" in folded

JS_SUFFIXES = {".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs"}

# Guidance files carry project conventions ("context engineering"): they are
# indexed first (never evicted by max_files) and receive a strong boost when
# they match a query, plus a small resident boost so they stay visible.
GUIDANCE_PATHS = {"agents.md", "claude.md", "minicc.md", ".minicc/instructions.md"}

# --- Scoring weights (module-level constants: single place to tune) --------
W_CONTENT_TERM = 1.0           # per query term found in file content
W_PATH_TERM = 2.0              # per query term found in the relative path
W_FILENAME = 3.0               # per query term found in the file basename
W_SYMBOL = 2.0                 # per query term matched by an extracted symbol
W_GUIDANCE = 6.0               # guidance file matched by at least one term
W_GUIDANCE_RESIDENT = 2.0      # constant resident boost for guidance files
W_FRESHNESS = 3.0              # maximum mtime recency bonus (decays)
FRESHNESS_HALF_LIFE_DAYS = 30.0
W_TEST_FAILURE = 1.0           # file mentions FAILED/ERROR test output
W_PATH_PATTERN_EXACT = 12.0    # query names the exact indexed relative path
W_PATH_PATTERN_BASENAME = 8.0  # query names the file, e.g. "view.py"
W_PATH_PATTERN_EXT = 3.0       # query mentions the suffix, e.g. ".py"

MAX_CODE_SYMBOLS = 256         # bounded search coverage, including later definitions
MAX_DISPLAY_SYMBOLS = 10       # keep prompt evidence concise
MAX_MARKER_SYMBOLS = 4         # TODO/FIXME annotations kept per file
MAX_SYMBOL_TERM_MATCHES = 4    # symbol bonus capped per query
MAX_PATH_TERM_MATCHES = 6      # path bonus capped per query
_SNAPSHOT_CHARS = 100_000      # per-file content snapshot bound (memory guard)
_SECS_PER_DAY = 86400.0

# --- Symbol extraction ------------------------------------------------------
PY_SYMBOL_RE = re.compile(r"^\s*(?:async\s+)?def\s+([A-Za-z_]\w*)|^\s*class\s+([A-Za-z_]\w*)", re.M)
JS_SYMBOL_RE = re.compile(
    r"\bfunction\s*\*?\s*([A-Za-z_$][\w$]*)"
    r"|\bclass\s+([A-Za-z_$][\w$]*)"
    r"|\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)"
)
MARKER_RE = re.compile(r"\b(TODO|FIXME)\b[:\s]*(.{0,60})", re.I)
FAILURE_RE = re.compile(r"^\s*(?:FAILED|ERROR)\s+([\w./:-]+)", re.M)

# --- Query tokenization -----------------------------------------------------
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")
_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_PATH_WITH_EXT_RE = re.compile(r"(?:[\w-]+/)*[\w-]+(?:\.[\w-]+)*\.[A-Za-z][\w]{0,9}")
_SLASH_PATH_RE = re.compile(r"\w+(?:/[\w.-]+)+")
_BARE_EXT_RE = re.compile(r"(?<![\w.])\.[A-Za-z][A-Za-z0-9]{0,9}")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "had", "has", "have", "how", "i", "if", "in",
    "into", "is", "it", "its", "may", "might", "must", "no", "not", "of", "on", "or",
    "our", "should", "so", "than", "that", "the", "their", "them", "then", "there",
    "these", "they", "this", "those", "to", "too", "was", "we", "were", "what",
    "when", "where", "which", "who", "why", "will", "with", "would", "you", "your",
}
CJK_STOPWORDS = {
    "一下", "一些", "不能", "但是", "对于", "关于", "还是", "如何", "或者", "进行",
    "就是", "可以", "没有", "那个", "那些", "什么", "使用", "实现", "他们", "我们",
    "怎么", "这个", "这些", "你们", "应该", "用来", "需要", "自己",
}
CJK_SINGLE_STOPWORDS = set("的了吗呢吧啊呀在是和与或及对把被有我你他它这那也很就都里上下中前后不没")


@dataclass(frozen=True)
class EvidenceHit:
    path: str
    score: float
    reason: str
    symbols: tuple[str, ...] = ()
    test_failures: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        # Consumer contract (web.py): "path", "reason" and "symbols" must stay.
        return {"path": self.path, "score": self.score, "reason": self.reason, "symbols": list(self.symbols), "test_failures": list(self.test_failures)}


@dataclass(frozen=True)
class _QueryPlan:
    """Normalized query: match terms plus strong path/suffix patterns."""

    terms: tuple[str, ...]
    path_patterns: tuple[str, ...]
    extensions: tuple[str, ...]

    @property
    def is_empty(self) -> bool:
        return not (self.terms or self.path_patterns or self.extensions)


@dataclass(frozen=True)
class _FileRecord:
    rel: str
    rel_casefold: str
    basename: str
    content: str
    symbols: tuple[str, ...]
    failures: tuple[str, ...]
    suffix: str
    mtime: float
    is_guidance: bool


def _extract_symbols(text: str, suffix: str) -> tuple[str, ...]:
    """Extract code symbols per language plus TODO/FIXME annotations."""

    names: list[str] = []
    if suffix == ".py":
        for groups in PY_SYMBOL_RE.findall(text):
            name = next((group for group in groups if group), None)
            if name:
                names.append(name)
    elif suffix in JS_SUFFIXES:
        for groups in JS_SYMBOL_RE.findall(text):
            name = next((group for group in groups if group), None)
            if name:
                names.append(name)
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if name not in seen:
            seen.add(name)
            ordered.append(name)
    markers: list[str] = []
    marker_seen: set[str] = set()
    for match in MARKER_RE.finditer(text):
        label = match.group(1).upper()
        note = match.group(2).strip().rstrip("。.,;；:：")
        entry = f"{label}: {note}" if note else label
        folded = entry.casefold()
        if folded not in marker_seen:
            marker_seen.add(folded)
            markers.append(entry)
        if len(markers) >= MAX_MARKER_SYMBOLS:
            break
    return tuple(ordered[:MAX_CODE_SYMBOLS] + markers)


def _add_term(terms: set[str], token: str) -> None:
    token = token.casefold()
    if len(token) >= 2 and token not in STOPWORDS:
        terms.add(token)


def _plan_query(query: str) -> _QueryPlan:
    """Tokenize a mixed English/CJK query into terms and path patterns."""

    text = str(query or "")
    terms: set[str] = set()
    path_patterns: set[str] = set()
    extensions: set[str] = set()

    # 1) File paths with an extension ("src/app.py", "view.py") are strong
    #    signals; their stem words stay as regular terms.
    for match in _PATH_WITH_EXT_RE.finditer(text):
        candidate = match.group(0).replace("\\", "/").casefold()
        path_patterns.add(candidate)
        stem, _, ext = candidate.rpartition(".")
        extensions.add(f".{ext}")
        for token in _WORD_RE.findall(stem):
            _add_term(terms, token)
    remainder = _PATH_WITH_EXT_RE.sub(" ", text)

    # 2) Slash paths without an extension ("minicc/agent").
    for match in _SLASH_PATH_RE.finditer(remainder):
        candidate = match.group(0).replace("\\", "/").casefold()
        path_patterns.add(candidate)
        for segment in candidate.split("/"):
            for token in _WORD_RE.findall(segment):
                _add_term(terms, token)
    remainder = _SLASH_PATH_RE.sub(" ", remainder)

    # 3) Bare suffix words (".py") favor files with that extension.
    for match in _BARE_EXT_RE.finditer(remainder):
        extensions.add(match.group(0).casefold())
    remainder = _BARE_EXT_RE.sub(" ", remainder)

    # 4) Plain ASCII words.
    for token in _WORD_RE.findall(remainder):
        _add_term(terms, token)

    # 5) CJK runs become overlapping character bigrams (single char only when
    #    the whole run is one character).
    for run in _CJK_RUN_RE.findall(remainder):
        if len(run) == 1:
            if run not in CJK_SINGLE_STOPWORDS:
                terms.add(run)
            continue
        for index in range(len(run) - 1):
            bigram = run[index : index + 2]
            if bigram not in CJK_STOPWORDS:
                terms.add(bigram)

    return _QueryPlan(tuple(sorted(terms)), tuple(sorted(path_patterns)), tuple(sorted(extensions)))


def _score_record(record: _FileRecord, plan: _QueryPlan, now: float) -> tuple[EvidenceHit, bool] | None:
    """Score one indexed file against the query plan.

    Returns ``(hit, matched)`` where ``matched`` means at least one query
    term hit the file (guidance fallback hits are not "matched"), or None
    when the file is irrelevant.
    """

    filename_terms = [term for term in plan.terms if term in record.basename]
    path_terms = [term for term in plan.terms if term in record.rel_casefold]
    content_terms = [term for term in plan.terms if term in record.content]
    symbol_terms: list[str] = []
    if record.symbols:
        folded_symbols = [symbol.casefold() for symbol in record.symbols]
        for term in plan.terms:
            if any(term in folded for folded in folded_symbols):
                symbol_terms.append(term)
                if len(symbol_terms) >= MAX_SYMBOL_TERM_MATCHES:
                    break

    score = 0.0
    reasons: list[str] = []

    # Strong path-pattern signals first.
    if record.rel_casefold in plan.path_patterns:
        score += W_PATH_PATTERN_EXACT
        reasons.append("path-pattern")
    elif record.basename in plan.path_patterns or any(
        record.rel_casefold.endswith("/" + pattern) for pattern in plan.path_patterns
    ):
        score += W_PATH_PATTERN_BASENAME
        reasons.append("path-pattern")
    if record.suffix in plan.extensions:
        score += W_PATH_PATTERN_EXT
        reasons.append("suffix")

    matched = bool(filename_terms or path_terms or content_terms or symbol_terms or score)
    # Freshness is a tie breaker, never evidence of relevance on its own.
    if not matched and not record.is_guidance:
        return None
    if record.is_guidance:
        if matched:
            score += W_GUIDANCE
            reasons.append("guidance")
        else:
            score += W_GUIDANCE_RESIDENT
            reasons.append("guidance-resident")

    if filename_terms:
        score += W_FILENAME * len(filename_terms)
        reasons.append("filename")
    if path_terms:
        score += W_PATH_TERM * min(len(path_terms), MAX_PATH_TERM_MATCHES)
        reasons.append("path")
    if symbol_terms:
        score += W_SYMBOL * len(symbol_terms)
        reasons.append("symbol")
    if content_terms:
        score += W_CONTENT_TERM * len(content_terms)
        reasons.append("content")
    if record.failures:
        score += W_TEST_FAILURE
        reasons.append("test-failure")

    # mtime freshness decays with a 30-day half-life.
    age_days = max(0.0, (now - record.mtime) / _SECS_PER_DAY)
    fresh = W_FRESHNESS * (0.5 ** (age_days / FRESHNESS_HALF_LIFE_DAYS))
    score += fresh
    if fresh >= W_FRESHNESS / 2.0:
        reasons.append("fresh")

    if not matched and not reasons:
        return None
    return (
        EvidenceHit(
            path=record.rel,
            score=round(score, 3),
            reason="+".join(reasons) if reasons else "content",
            symbols=tuple(sorted(record.symbols, key=lambda symbol: not any(term in symbol.casefold() for term in plan.terms))[:MAX_DISPLAY_SYMBOLS]),
            test_failures=record.failures,
        ),
        matched,
    )


def query_terms(query: str) -> tuple[str, ...]:
    """Deterministic tokenizer surface for other recall indexes (M8-T1 memory).

    Returns the same normalized terms + path patterns ``search()`` scores
    with, so keyword recall stays consistent across evidence and memory.
    """

    plan = _plan_query(query)
    return plan.terms + plan.path_patterns


class LocalEvidenceIndex:
    def __init__(self, workspace: Path, *, max_files: int = 1200, max_bytes: int = 900_000, refresh_interval: float = 1.0) -> None:
        self.workspace = workspace.resolve()
        self.max_files = max(1, max_files)
        self.max_bytes = max(10_000, max_bytes)
        self._records: tuple[_FileRecord, ...] = ()
        self._stats: dict[str, object] | None = None
        self._record_cache: dict[str, tuple[tuple[int, int], _FileRecord]] = {}
        self._refresh_interval = max(0.0, refresh_interval)
        self._checked_at = 0.0
        self._lock = threading.RLock()

    def search(self, query: str, *, limit: int = 8) -> list[EvidenceHit]:
        self._ensure_built()
        plan = _plan_query(query)
        if plan.is_empty:
            return []
        now = time.time()
        hits: list[EvidenceHit] = []
        fallback: list[EvidenceHit] = []
        for record in self._records:
            scored = _score_record(record, plan, now)
            if scored is None:
                continue
            hit, matched = scored
            if record.is_guidance and not matched:
                fallback.append(hit)
            else:
                hits.append(hit)
        if not hits:
            # Resident guidance files only surface when nothing else matched,
            # so the resident boost never outranks real term evidence.
            hits = fallback
        hits.sort(key=lambda hit: (-hit.score, hit.path))
        return hits[: max(1, min(20, limit))]

    def stats(self) -> dict[str, object]:
        """Return {files_indexed, symbols_extracted, last_build_ms}."""

        self._ensure_built()
        return dict(self._stats or {})

    def _ensure_built(self) -> None:
        with self._lock:
            if self._stats is not None and time.monotonic() - self._checked_at < self._refresh_interval:
                return
            self._refresh()

    def refresh(self) -> dict[str, object]:
        """Refresh changed files immediately; unchanged records are reused."""
        with self._lock:
            self._refresh()
            return dict(self._stats or {})

    def _refresh(self) -> None:
        start = time.perf_counter()
        records: list[_FileRecord] = []
        symbols_extracted = 0
        cache: dict[str, tuple[tuple[int, int], _FileRecord]] = {}
        rebuilt = 0
        for path, rel in self._files():
            try:
                stat = path.stat()
            except OSError:
                continue
            signature = (stat.st_mtime_ns, stat.st_size)
            previous = self._record_cache.get(rel)
            if previous and previous[0] == signature:
                record = previous[1]
            else:
                record = self._build_record(path, rel)
                rebuilt += 1
            if record is None:
                continue
            cache[rel] = (signature, record)
            symbols_extracted += len(record.symbols)
            records.append(record)
        self._checked_at = time.monotonic()
        if self._stats is not None and cache == self._record_cache:
            self._stats = {**self._stats, "files_rebuilt": 0}
            return
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        self._record_cache = cache
        self._records = tuple(records)
        self._stats = {
            "files_indexed": len(records),
            "symbols_extracted": symbols_extracted,
            "last_build_ms": round(elapsed_ms, 2),
            "files_rebuilt": rebuilt,
            "file_limit": self.max_files,
            "truncated": len(records) >= self.max_files,
        }

    def _build_record(self, path: Path, rel: str) -> _FileRecord | None:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as stream:
                text = stream.read(min(self.max_bytes, _SNAPSHOT_CHARS))
        except OSError:
            return None
        head = text[: self.max_bytes]
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        rel_cf = rel.casefold()
        return _FileRecord(
            rel=rel,
            rel_casefold=rel_cf,
            basename=rel.rsplit("/", 1)[-1].casefold(),
            # The relative path is prepended so path words match content too.
            content=f"{rel}\n{head[:_SNAPSHOT_CHARS]}".casefold(),
            symbols=_extract_symbols(head, path.suffix.casefold()),
            failures=tuple(FAILURE_RE.findall(head)[:6]),
            suffix=path.suffix.casefold(),
            mtime=mtime,
            is_guidance=rel_cf in GUIDANCE_PATHS,
        )

    def _files(self) -> list[tuple[Path, str]]:
        """Collect files to index; guidance files always come first."""

        guidance: list[tuple[Path, str]] = []
        regular: list[tuple[Path, str]] = []
        # Guidance is discovered separately so pruning .minicc never loses it.
        for parent in (self.workspace, self.workspace / ".minicc"):
            if parent.is_symlink():
                continue
            try:
                for path in parent.iterdir():
                    rel = path.relative_to(self.workspace).as_posix()
                    if rel.casefold() in GUIDANCE_PATHS and path.is_file() and not path.is_symlink():
                        guidance.append((path, rel))
            except OSError:
                pass
        directories = 0
        # Prune before descent: cached browsers, git objects and dependencies
        # must never consume the source-file budget. Prefer code over archives.
        for directory, dirs, files in os.walk(self.workspace, followlinks=False):
            directories += 1
            if directories > max(4_000, self.max_files * 4):
                break
            dirs[:] = sorted(
                (name for name in dirs if name.casefold() not in SKIP_DIRS and not name.startswith(".")
                 and not (Path(directory) / name).is_symlink()),
                key=lambda name: (name.casefold() in {"docs", "tests", "benchmarks", "scripts"}, name.casefold()),
            )
            for name in sorted(files):
                path = Path(directory) / name
                if name.startswith(".") or path.suffix.casefold() not in TEXT_SUFFIXES or path.is_symlink():
                    continue
                if is_secret_filename(name):
                    continue
                rel = path.relative_to(self.workspace).as_posix()
                if rel.casefold() in GUIDANCE_PATHS:
                    continue
                regular.append((path, rel))
                if len(regular) >= self.max_files:
                    return sorted(guidance, key=lambda item: item[1]) + regular
        return sorted(guidance, key=lambda item: item[1]) + regular


_INDEX_CACHE: OrderedDict[str, LocalEvidenceIndex] = OrderedDict()
_INDEX_CACHE_LOCK = threading.Lock()


def get_evidence_index(workspace: Path) -> LocalEvidenceIndex:
    """Reuse bounded, incrementally refreshed indexes across chat requests."""
    key = str(workspace.resolve())
    with _INDEX_CACHE_LOCK:
        index = _INDEX_CACHE.pop(key, None) or LocalEvidenceIndex(workspace)
        _INDEX_CACHE[key] = index
        while len(_INDEX_CACHE) > 8:
            _INDEX_CACHE.popitem(last=False)
        return index


__all__ = ["EvidenceHit", "LocalEvidenceIndex", "get_evidence_index"]
