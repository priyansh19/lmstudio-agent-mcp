"""
web_tools.py — A FastMCP server giving a local LLM internet access:
fetch a URL as readable text, and run a keyless web search (DuckDuckGo HTML).

No API keys required. Transport: stdio.

Run directly:
    python web_tools.py
"""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("local-web-tools")

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) local-agent/1.0"
_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_WS_RE = re.compile(r"\n\s*\n\s*\n+")


def _strip_html(raw: str) -> str:
    raw = _SCRIPT_RE.sub(" ", raw)
    raw = _TAG_RE.sub("", raw)
    raw = html.unescape(raw)
    raw = _WS_RE.sub("\n\n", raw)
    return raw.strip()


@mcp.tool()
def fetch_url(url: str, max_chars: int = 8000) -> str:
    """Fetch a web page and return its visible text (HTML stripped).
    Truncated to `max_chars`. Use this to read docs, APIs, articles."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            data = resp.read(2_000_000)  # 2 MB cap
            body = data.decode(charset, errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"Error fetching {url}: {exc!r}"
    text = _strip_html(body)
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n... (truncated, {len(text)} chars total)"
    return text or "(no readable text found)"


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> str:
    """Search the web (DuckDuckGo, no API key) and return titles + URLs +
    snippets. Use this to discover docs or sources, then fetch_url to read."""
    endpoint = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
    req = urllib.request.Request(endpoint, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return f"Error searching: {exc!r}"

    results: list[str] = []
    # DuckDuckGo HTML result anchors carry the result__a class.
    pattern = re.compile(
        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    snippet_re = re.compile(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
        re.DOTALL | re.IGNORECASE,
    )
    links = pattern.findall(body)
    snippets = snippet_re.findall(body)
    for i, (href, title) in enumerate(links[:max_results]):
        # DDG wraps real URLs in a redirect with uddg= param.
        real = href
        m = re.search(r"uddg=([^&]+)", href)
        if m:
            real = urllib.parse.unquote(m.group(1))
        clean_title = _strip_html(title)
        snip = _strip_html(snippets[i]) if i < len(snippets) else ""
        results.append(f"{i + 1}. {clean_title}\n   {real}\n   {snip}")
    return "\n\n".join(results) if results else "(no results)"


if __name__ == "__main__":
    mcp.run(transport="stdio")
