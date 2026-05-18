"""Web skills: search and fetch-and-extract."""
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

from ...config import settings
from ..base import Skill


class WebSearchSkill(Skill):
    name = "web_search"
    description = "Search the web."
    tool_description = "Search the web (DuckDuckGo). Returns titles, snippets, and URLs."
    patterns = [r"^\s*(?:search|google|look up)\s+(?:for\s+)?(?P<query>.+?)\s*[!.\?]*\s*$"]
    args_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        query = match.group("query").strip() if match else text.strip()
        return await self.run_tool({"query": query})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        query = (args.get("query") or "").strip()
        if not query:
            return {"ok": False, "reply": "Tell me what to search for."}
        n = int(args.get("max_results") or 5)

        def _search() -> list[dict[str, str]]:
            from ddgs import DDGS

            with DDGS() as ddgs:
                hits = list(ddgs.text(query, max_results=n))
            return [
                {
                    "title": h.get("title", ""),
                    "url": h.get("href") or h.get("url", ""),
                    "snippet": h.get("body", ""),
                }
                for h in hits
            ]

        try:
            results = await asyncio.to_thread(_search)
        except Exception as e:
            return {"ok": False, "reply": f"Search failed: {e}"}
        if not results:
            return {"ok": True, "reply": f"No results for '{query}'."}
        summary = "; ".join(f"{r['title']}" for r in results[:3])
        return {
            "ok": True,
            "reply": f"Top {len(results)} for '{query}': {summary}",
            "results": results,
        }


class WebFetchSkill(Skill):
    name = "web_fetch"
    description = "Fetch a URL and extract its main text."
    tool_description = (
        "Fetch a URL and return its main text content (HTML stripped). Use to read articles or docs "
        "the user pointed you at."
    )
    patterns = [r"^\s*(?:fetch|read|open\s+url)\s+(?P<url>https?://\S+)\s*$"]
    args_schema = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "default": 8000},
        },
        "required": ["url"],
    }

    async def run(self, text: str, match: Any | None = None) -> dict[str, Any]:
        url = match.group("url").strip() if match else text.strip()
        return await self.run_tool({"url": url})

    async def run_tool(self, args: dict[str, Any]) -> dict[str, Any]:
        url = (args.get("url") or "").strip()
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return {"ok": False, "reply": f"Not a valid URL: {url!r}"}
        max_chars = int(args.get("max_chars") or settings.web_max_chars)

        try:
            import httpx  # already in deps via anthropic
        except ImportError:
            return {"ok": False, "reply": "httpx not installed."}

        try:
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=settings.web_timeout_s,
                headers={"User-Agent": settings.web_user_agent},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPError as e:
            return {"ok": False, "reply": f"Fetch failed: {e}"}

        text = await asyncio.to_thread(_extract_main_text, html)
        text = text[:max_chars]
        title = await asyncio.to_thread(_extract_title, html)
        word_count = len(text.split())
        reply = f"Fetched {parsed.netloc} ({word_count} words)."
        if title:
            reply = f'"{title}" — {reply}'
        return {
            "ok": True,
            "reply": reply,
            "url": url,
            "title": title,
            "text": text,
            "truncated": len(text) >= max_chars,
        }


def _extract_main_text(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "iframe", "header", "footer", "nav", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = main.get_text("\n", strip=True)
    # collapse blank lines
    lines = [ln for ln in (l.strip() for l in text.splitlines()) if ln]
    return "\n".join(lines)


def _extract_title(html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else ""
