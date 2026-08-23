"""Small, dependency-free web search tool for the local agent.

Search results are untrusted context. The tool returns short snippets and
source URLs so the model can cite what it used without treating a snippet as
authoritative.
"""

from __future__ import annotations

import threading
import time
from html import unescape
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit
from urllib.request import Request, urlopen

from .registry import ToolError
from .schemas import ToolResult

SEARCH_ENDPOINTS = (
    ("Bing", "https://www.bing.com/search?q={}"),
    ("DuckDuckGo Lite", "https://lite.duckduckgo.com/lite/?q={}"),
    ("DuckDuckGo HTML", "https://html.duckduckgo.com/html/?q={}"),
)
USER_AGENT = "minicc-web-search/0.4 (+local coding agent)"
MAX_QUERY_CHARS = 500
MAX_RESULTS = 8
REQUEST_TIMEOUT = 12
SEARCH_ATTEMPTS = 2
SEARCH_CACHE_TTL = 300.0
SEARCH_CACHE_SIZE = 64


class _SearchFetch:
    def __init__(
        self,
        *,
        source: str,
        results: list[dict[str, str]],
        diagnostics: list[str],
        html: str = "",
        cached: bool = False,
    ) -> None:
        self.source = source
        self.results = results
        self.diagnostics = diagnostics
        self.html = html
        self.cached = cached


_SEARCH_CACHE: dict[str, tuple[float, _SearchFetch]] = {}
_SEARCH_CACHE_LOCK = threading.Lock()


def _cache_key(query: str) -> str:
    return " ".join(query.casefold().split())


def _cache_get(query: str) -> _SearchFetch | None:
    key = _cache_key(query)
    now = time.monotonic()
    with _SEARCH_CACHE_LOCK:
        item = _SEARCH_CACHE.get(key)
        if item is None:
            return None
        created, value = item
        if now - created > SEARCH_CACHE_TTL:
            _SEARCH_CACHE.pop(key, None)
            return None
        return _SearchFetch(
            source=value.source,
            results=[dict(result) for result in value.results],
            diagnostics=list(value.diagnostics),
            html=value.html,
            cached=True,
        )


def _cache_put(query: str, value: _SearchFetch) -> None:
    key = _cache_key(query)
    cached_value = _SearchFetch(
        source=value.source,
        results=[dict(result) for result in value.results],
        diagnostics=list(value.diagnostics),
    )
    with _SEARCH_CACHE_LOCK:
        _SEARCH_CACHE[key] = (time.monotonic(), cached_value)
        if len(_SEARCH_CACHE) > SEARCH_CACHE_SIZE:
            oldest = min(_SEARCH_CACHE, key=lambda item: _SEARCH_CACHE[item][0])
            _SEARCH_CACHE.pop(oldest, None)


def _class_names(attrs: list[tuple[str, str | None]]) -> set[str]:
    return set((dict(attrs).get("class") or "").split())


def _result_url(raw_url: str) -> str:
    value = unescape(raw_url or "").strip()
    if value.startswith("//"):
        value = f"https:{value}"
    parsed = urlsplit(value)
    if parsed.netloc.endswith("duckduckgo.com"):
        redirected = parse_qs(parsed.query).get("uddg", [""])[0]
        if redirected:
            value = unquote(redirected)
    return value


class _DuckDuckGoParser(HTMLParser):
    """Parse only stable result classes, ignoring page instructions."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._active: str | None = None
        self._active_tag: str | None = None
        self._active_depth = 0
        self._buffer: list[str] = []
        self._href = ""

    def _begin(self, field: str, tag: str, href: str = "") -> None:
        self._active = field
        self._active_tag = tag
        self._active_depth = 0
        self._buffer = []
        self._href = href

    def _finish(self) -> None:
        if self._active is None:
            return
        text = " ".join("".join(self._buffer).split())
        if self._active == "title" and text:
            self.results.append({"title": text, "url": _result_url(self._href), "snippet": ""})
        elif self._active == "snippet" and text and self.results:
            self.results[-1]["snippet"] = text
        self._active = None
        self._active_tag = None
        self._active_depth = 0
        self._buffer = []
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._active is not None:
            self._active_depth += 1
            return
        classes = _class_names(attrs)
        attr_map = dict(attrs)
        if "result__a" in classes or "result-link" in classes:
            self._begin("title", tag, attr_map.get("href") or "")
        elif "result__snippet" in classes or "result-snippet" in classes:
            self._begin("snippet", tag)

    def handle_endtag(self, tag: str) -> None:
        if self._active is None:
            return
        if self._active_depth:
            self._active_depth -= 1
        elif tag == self._active_tag:
            self._finish()

    def handle_data(self, data: str) -> None:
        if self._active is not None:
            self._buffer.append(data)


class _BingParser(HTMLParser):
    """Parse Bing's organic ``b_algo`` list items without trusting markup text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._result: dict[str, str] | None = None
        self._result_depth = -1
        self._capture: str | None = None
        self._capture_tag: str | None = None
        self._capture_depth = 0
        self._buffer: list[str] = []
        self._href = ""

    def _begin_capture(self, field: str, tag: str) -> None:
        self._capture = field
        self._capture_tag = tag
        self._capture_depth = 0
        self._buffer = []
        self._href = ""

    def _finish_capture(self) -> None:
        if self._capture is None or self._result is None:
            return
        text = " ".join("".join(self._buffer).split())
        if text:
            self._result[self._capture] = text
        if self._capture == "title" and self._href:
            self._result["url"] = _result_url(self._href)
        self._capture = None
        self._capture_tag = None
        self._capture_depth = 0
        self._buffer = []
        self._href = ""

    def _finish_result(self) -> None:
        if self._result is not None:
            self.results.append(self._result)
        self._result = None
        self._result_depth = -1
        self._capture = None
        self._capture_tag = None
        self._capture_depth = 0
        self._buffer = []
        self._href = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = dict(attrs)
        classes = _class_names(attrs)
        if self._result is None:
            if tag == "li" and "b_algo" in classes:
                self._result = {"title": "", "url": "", "snippet": ""}
                self._result_depth = 0
            return
        if self._capture is not None:
            if self._capture == "title" and tag == "a" and not self._href:
                self._href = attr_map.get("href") or ""
            self._capture_depth += 1
            return
        if tag == "h2" and not self._result.get("title"):
            self._begin_capture("title", tag)
        elif tag == "p" and ("b_lineclamp" in " ".join(classes) or "b_caption" in classes):
            self._begin_capture("snippet", tag)
        else:
            self._result_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._result is None:
            return
        if self._capture is not None:
            if self._capture_depth:
                self._capture_depth -= 1
            elif tag == self._capture_tag:
                self._finish_capture()
            return
        if tag == "li" and self._result_depth == 0:
            self._finish_result()
        elif self._result_depth >= 0:
            self._result_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._buffer.append(data)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Bing puts self-closing stylesheet/link tags inside result items.
        # HTMLParser emits no end-tag for them, so balance the depth here.
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def close(self) -> None:
        super().close()
        if self._capture is not None:
            self._finish_capture()
        if self._result is not None:
            self._finish_result()


def parse_search_html(html: str, max_results: int = MAX_RESULTS) -> list[dict[str, str]]:
    parser = _DuckDuckGoParser()
    parser.feed(html)
    bing_parser = _BingParser()
    bing_parser.feed(html)
    bing_parser.close()
    output: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*parser.results, *bing_parser.results]:
        url = item.get("url", "")
        if not url or url in seen or not url.startswith(("http://", "https://")):
            continue
        seen.add(url)
        output.append(
            {
                "title": item.get("title", "")[:240],
                "url": url[:2000],
                "snippet": item.get("snippet", "")[:700],
            }
        )
        if len(output) >= max_results:
            break
    return output


def _is_challenge_page(html: str) -> bool:
    lowered = html.casefold()
    return any(marker in lowered for marker in ("anomaly-modal", "captcha", "verify you are human", "unusual traffic"))


def _fetch_search(query: str) -> _SearchFetch:
    diagnostics: list[str] = []
    saw_valid_page = False
    last_html = ""
    last_source = ""
    last_valid_source = ""
    for source, endpoint in SEARCH_ENDPOINTS:
        for attempt in range(1, SEARCH_ATTEMPTS + 1):
            request = Request(
                endpoint.format(quote_plus(query)),
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            try:
                with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
                    status = int(getattr(response, "status", 200) or 200)
                    body = response.read(1_500_000)
                    headers = getattr(response, "headers", None)
                    charset = headers.get_content_charset() if headers is not None else None
                    html = body.decode(charset or "utf-8", errors="replace")
                last_html = html
                last_source = source
                if status in {429, 500, 502, 503, 504}:
                    diagnostics.append(f"{source} HTTP {status}")
                elif _is_challenge_page(html):
                    diagnostics.append(f"{source} 返回验证页面")
                else:
                    saw_valid_page = True
                    last_valid_source = source
                    results = parse_search_html(html, MAX_RESULTS)
                    if results:
                        return _SearchFetch(source=source, results=results, diagnostics=diagnostics, html=html)
                    diagnostics.append(f"{source} 返回页面但没有可解析结果")
                    break
            except HTTPError as exc:
                diagnostics.append(f"{source} HTTP {exc.code}")
            except (URLError, TimeoutError, OSError) as exc:
                diagnostics.append(f"{source} 网络错误: {type(exc).__name__}")
            if attempt < SEARCH_ATTEMPTS:
                time.sleep(0.25 * (2 ** (attempt - 1)))
        # A challenge or transport failure should move to the next source;
        # retrying the same page more than SEARCH_ATTEMPTS times is wasteful.
    if saw_valid_page:
        return _SearchFetch(
            source=last_valid_source or last_source or "多源搜索",
            results=[],
            diagnostics=diagnostics,
            html=last_html,
        )
    detail = "; ".join(dict.fromkeys(diagnostics)) or "没有可用搜索服务"
    raise ToolError(f"联网搜索暂不可用：{detail}。已自动尝试备用来源，请稍后重试或换用项目内证据。")


def _fetch_search_html(query: str) -> str:
    """Compatibility helper retained for callers that only need raw HTML."""
    return _fetch_search(query).html


def web_search(args: dict[str, object]) -> ToolResult:
    raw_query = str(args.get("query") or "").strip()
    if not raw_query:
        raise ToolError("搜索关键词不能为空")
    if len(raw_query) > MAX_QUERY_CHARS:
        raise ToolError(f"搜索关键词不能超过 {MAX_QUERY_CHARS} 个字符")
    raw_limit = args.get("max_results", 5)
    try:
        limit = max(1, min(MAX_RESULTS, int(raw_limit)))
    except (TypeError, ValueError) as exc:
        raise ToolError("max_results 必须是整数") from exc

    fetched = _cache_get(raw_query)
    if fetched is None:
        fetched = _fetch_search(raw_query)
        _cache_put(raw_query, fetched)
    results = fetched.results[:limit]
    lines: list[str] = []
    for index, item in enumerate(results, start=1):
        lines.append(f"[{index}] {item['title']}\nURL: {item['url']}\n{item['snippet']}")
    output = "\n\n".join(lines) or "(没有找到结果，请换一种关键词；搜索服务已返回可访问页面。)"
    cache_note = "（缓存）" if fetched.cached else ""
    diagnostic_note = f"；诊断：{'；'.join(fetched.diagnostics[-3:])}" if fetched.diagnostics else ""
    return ToolResult(
        status="ok",
        summary=f"联网搜索 {raw_query!r}，通过 {fetched.source}{cache_note}返回 {len(results)} 条结果{diagnostic_note}",
        output=output,
        data={
            "query": raw_query,
            "source": fetched.source,
            "results": results,
            "diagnostics": list(fetched.diagnostics),
            "cached": fetched.cached,
        },
        security_tags=["untrusted", "network"],
    )


__all__ = ["parse_search_html", "web_search"]
