"""Pagination helpers for provider-specific API traversal patterns."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterator, Optional


class OffsetPaginator:
    """Offset + limit pagination common to tactical OSINT endpoints."""

    def __init__(self, limit: int = 100, start_offset: int = 0, offset_param: str = "offset", limit_param: str = "limit") -> None:
        self.limit = int(limit)
        self.start_offset = int(start_offset)
        self.offset_param = offset_param
        self.limit_param = limit_param

    def iterate(self, fetch_page: Callable[[Dict[str, int]], Dict[str, Any]], max_pages: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        offset = self.start_offset
        pages = 0
        while max_pages is None or pages < max_pages:
            response = fetch_page({self.offset_param: offset, self.limit_param: self.limit})
            yield response
            pages += 1

            items = response.get("items", [])
            if not items:
                break
            if response.get("has_more") is False:
                break
            next_offset = response.get("next_offset")
            if next_offset is not None:
                offset = int(next_offset)
            else:
                offset += self.limit
            total = response.get("total")
            if total is not None and offset >= int(total):
                break


class CursorPaginator:
    """Cursor/token pagination for premium and streaming APIs."""

    def __init__(self, start_cursor: Optional[str] = None) -> None:
        self.start_cursor = start_cursor

    def iterate(self, fetch_page: Callable[[Optional[str]], Dict[str, Any]], max_pages: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        cursor = self.start_cursor
        pages = 0
        while max_pages is None or pages < max_pages:
            response = fetch_page(cursor)
            yield response
            pages += 1
            next_cursor = response.get("next_cursor")
            if not next_cursor or next_cursor == cursor:
                break
            cursor = str(next_cursor)


class PageNumberPaginator:
    """Page-number pagination for legacy provider APIs."""

    def __init__(self, start_page: int = 1, per_page: int = 100, page_param: str = "page", per_page_param: str = "per_page") -> None:
        self.start_page = int(start_page)
        self.per_page = int(per_page)
        self.page_param = page_param
        self.per_page_param = per_page_param

    def iterate(self, fetch_page: Callable[[Dict[str, int]], Dict[str, Any]], max_pages: Optional[int] = None) -> Iterator[Dict[str, Any]]:
        page = self.start_page
        pages_seen = 0
        while max_pages is None or pages_seen < max_pages:
            response = fetch_page({self.page_param: page, self.per_page_param: self.per_page})
            yield response
            pages_seen += 1

            items = response.get("items", [])
            if not items:
                break
            total_pages = response.get("total_pages")
            if total_pages is not None and page >= int(total_pages):
                break
            if response.get("has_more") is False:
                break
            page += 1


class LinkHeaderPaginator:
    """RFC 5988 Link header pagination used by GitHub-style APIs."""

    _NEXT_RE = re.compile(r'<([^>]+)>;\s*rel="next"')

    def iterate(
        self,
        fetch_page: Callable[[str], Dict[str, Any]],
        initial_url: str,
        max_pages: Optional[int] = None,
    ) -> Iterator[Dict[str, Any]]:
        url: Optional[str] = initial_url
        pages = 0
        while url and (max_pages is None or pages < max_pages):
            response = fetch_page(url)
            yield response
            pages += 1

            headers = response.get("headers") or {}
            link = headers.get("Link") or headers.get("link") or ""
            match = self._NEXT_RE.search(link)
            url = match.group(1) if match else None
