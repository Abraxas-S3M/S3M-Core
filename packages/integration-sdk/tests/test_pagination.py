from integration_sdk.http.pagination import CursorPaginator, LinkHeaderPaginator, OffsetPaginator, PageNumberPaginator


def test_offset_paginator_iterates_pages():
    paginator = OffsetPaginator(limit=2)

    def fetch(params):
        offset = params["offset"]
        if offset >= 4:
            return {"items": []}
        return {"items": [offset, offset + 1], "next_offset": offset + 2}

    pages = list(paginator.iterate(fetch))
    assert len(pages) == 3


def test_cursor_paginator_stops_without_next_cursor():
    paginator = CursorPaginator(start_cursor=None)

    def fetch(cursor):
        if cursor is None:
            return {"items": [1], "next_cursor": "abc"}
        return {"items": [2], "next_cursor": None}

    pages = list(paginator.iterate(fetch))
    assert len(pages) == 2


def test_page_number_paginator_max_pages():
    paginator = PageNumberPaginator(start_page=1, per_page=1)

    def fetch(params):
        return {"items": [params["page"]], "has_more": True}

    pages = list(paginator.iterate(fetch, max_pages=3))
    assert len(pages) == 3


def test_link_header_paginator():
    paginator = LinkHeaderPaginator()
    responses = {
        "https://api/a": {"items": [1], "headers": {"Link": '<https://api/b>; rel="next"'}},
        "https://api/b": {"items": [2], "headers": {}},
    }

    pages = list(paginator.iterate(lambda url: responses[url], initial_url="https://api/a"))
    assert [p["items"][0] for p in pages] == [1, 2]
