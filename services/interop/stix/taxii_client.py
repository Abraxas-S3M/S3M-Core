"""TAXII 2.1 transport client with offline queueing for air-gapped CTI."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, parse, request
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TAXIIClient:
    """REST client for TAXII 2.1 STIX bundle exchange."""

    def __init__(
        self,
        server_url: str,
        collection_id: str | None = None,
        auth: dict | None = None,
        timeout: float = 10.0,
        outbox_dir: str = "data/interop/taxii_outbox/",
        inbox_dir: str = "data/interop/taxii_inbox/",
    ) -> None:
        self.server_url = str(server_url or "").strip().rstrip("/")
        self.collection_id = str(collection_id or "").strip() or None
        self.auth = dict(auth or {})
        self.timeout = float(timeout) if float(timeout) > 0 else 10.0
        self.outbox_dir = Path(outbox_dir)
        self.inbox_dir = Path(inbox_dir)
        self.outbox_dir.mkdir(parents=True, exist_ok=True)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)

        self.api_roots: list[str] = []
        self.active_api_root: str | None = None
        self.connected = False
        self.last_error: str | None = None

    def discover(self) -> dict:
        """Discover TAXII API roots from the discovery endpoint."""
        payload = self._request_json(
            method="GET",
            url=self._discovery_url(),
            headers={"Accept": "application/taxii+json;version=2.1"},
        )

        roots_raw = payload.get("api_roots", [])
        if not isinstance(roots_raw, list):
            roots_raw = []

        discovery_url = self._discovery_url()
        parsed_roots: list[str] = []
        for root in roots_raw:
            root_text = str(root).strip()
            if not root_text:
                continue
            absolute = parse.urljoin(f"{discovery_url.rstrip('/')}/", root_text)
            parsed_roots.append(absolute.rstrip("/") + "/")

        self.api_roots = parsed_roots
        self.active_api_root = parsed_roots[0] if parsed_roots else None
        self._flush_outbox()

        return {
            "title": str(payload.get("title", "")).strip(),
            "description": str(payload.get("description", "")).strip(),
            "api_roots": list(self.api_roots),
        }

    def list_collections(self, api_root: str | None = None) -> list[dict]:
        """List TAXII collections exposed by the selected API root."""
        root = self._resolve_api_root(api_root)
        payload = self._request_json(
            method="GET",
            url=f"{root.rstrip('/')}/collections/",
            headers={"Accept": "application/taxii+json;version=2.1"},
        )
        self._flush_outbox()

        rows: list[dict] = []
        for raw in payload.get("collections", []) if isinstance(payload, dict) else []:
            if not isinstance(raw, dict):
                continue
            rows.append(
                {
                    "id": str(raw.get("id", "")).strip(),
                    "title": str(raw.get("title", "")).strip(),
                    "description": str(raw.get("description", "")).strip(),
                    "can_read": bool(raw.get("can_read", False)),
                    "can_write": bool(raw.get("can_write", False)),
                }
            )
        return rows

    def poll(self, collection_id: str | None = None, added_after: str | None = None) -> list[dict]:
        """Poll STIX objects from a TAXII collection and cache incoming bundles."""
        resolved_collection = self._resolve_collection_id(collection_id)
        root = self._resolve_api_root(None)
        query = ""
        if added_after:
            query = "?" + parse.urlencode({"added_after": str(added_after).strip()})

        url = f"{root.rstrip('/')}/collections/{parse.quote(resolved_collection)}/objects/{query}"
        payload = self._request_json(
            method="GET",
            url=url,
            headers={"Accept": "application/stix+json;version=2.1"},
        )
        self._flush_outbox()

        if payload.get("type") == "bundle":
            self._cache_inbox_bundle(payload)

        objects: list[dict] = []
        for item in payload.get("objects", []) if isinstance(payload, dict) else []:
            if isinstance(item, dict):
                objects.append(item)
        return objects

    def publish(self, bundle: dict, collection_id: str | None = None) -> bool:
        """Publish a STIX 2.1 bundle to a TAXII collection."""
        if not isinstance(bundle, dict):
            raise ValueError("bundle must be a dictionary")
        if str(bundle.get("type", "")).strip() != "bundle":
            raise ValueError("bundle.type must be 'bundle'")

        resolved_collection = self._resolve_collection_id(collection_id)
        root = self._resolve_api_root(None)
        url = f"{root.rstrip('/')}/collections/{parse.quote(resolved_collection)}/objects/"

        try:
            self._request_json(
                method="POST",
                url=url,
                headers={
                    "Accept": "application/taxii+json;version=2.1",
                    "Content-Type": "application/stix+json;version=2.1",
                },
                payload=bundle,
            )
            self._flush_outbox()
            return True
        except (error.URLError, TimeoutError, ValueError, OSError):
            # Tactical context: queue outbound CTI when coalition uplinks are down.
            self.connected = False
            self.last_error = "publish_failed_offline_queued"
            self._queue_bundle(bundle=bundle, collection_id=resolved_collection)
            return True

    def health_check(self) -> dict:
        """Return current TAXII transport health and offline queue statistics."""
        return {
            "connected": self.connected,
            "server_url": self.server_url,
            "collection_id": self.collection_id,
            "api_roots": list(self.api_roots),
            "active_api_root": self.active_api_root,
            "timeout_seconds": self.timeout,
            "offline_outbox_count": len(list(self.outbox_dir.glob("*.json"))),
            "cached_inbox_count": len(list(self.inbox_dir.glob("*.json"))),
            "last_error": self.last_error,
        }

    def _resolve_api_root(self, api_root: str | None) -> str:
        if api_root and str(api_root).strip():
            root_text = str(api_root).strip()
            if root_text.startswith("http://") or root_text.startswith("https://"):
                resolved = root_text
            else:
                resolved = parse.urljoin(f"{self.server_url.rstrip('/')}/", root_text)
            self.active_api_root = resolved.rstrip("/") + "/"
            return self.active_api_root

        if self.active_api_root:
            return self.active_api_root

        if self.api_roots:
            self.active_api_root = self.api_roots[0]
            return self.active_api_root

        discovery = self.discover()
        roots = discovery.get("api_roots", [])
        if roots:
            return str(roots[0])
        raise ValueError("No TAXII API root available")

    def _resolve_collection_id(self, collection_id: str | None) -> str:
        resolved = str(collection_id or self.collection_id or "").strip()
        if not resolved:
            raise ValueError("collection_id is required")
        self.collection_id = resolved
        return resolved

    def _request_json(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict:
        if not self.server_url:
            raise ValueError("server_url is required")

        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=True).encode("utf-8")

        req = request.Request(
            url=url,
            data=body,
            headers=self._headers(headers),
            method=method.upper(),
        )

        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="ignore")
                self.connected = 200 <= response.status < 300
                self.last_error = None
                if not raw.strip():
                    return {}
                parsed = json.loads(raw)
                return parsed if isinstance(parsed, dict) else {}
        except (error.URLError, error.HTTPError, TimeoutError, ConnectionError, OSError) as exc:
            self.connected = False
            self.last_error = str(exc)
            raise
        except json.JSONDecodeError as exc:
            self.connected = False
            self.last_error = f"invalid_json: {exc}"
            raise ValueError("Invalid JSON response from TAXII server") from exc

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers: dict[str, str] = {
            "User-Agent": "S3M-TAXIIClient/1.0",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)

        auth_type = str(self.auth.get("type", "")).strip().lower()
        username = str(self.auth.get("username", "")).strip()
        password = str(self.auth.get("password", ""))

        if auth_type == "basic" or (username and "password" in self.auth):
            token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
            return headers

        token_value = (
            self.auth.get("token")
            or self.auth.get("api_token")
            or self.auth.get("api_key")
            or self.auth.get("bearer_token")
        )
        if token_value:
            header_name = str(self.auth.get("header", "Authorization")).strip() or "Authorization"
            raw_token = str(token_value).strip()
            if not raw_token:
                return headers
            if header_name.lower() == "authorization":
                prefix = str(self.auth.get("prefix", "Bearer")).strip() or "Bearer"
                if raw_token.lower().startswith("bearer ") or raw_token.lower().startswith("basic "):
                    headers[header_name] = raw_token
                else:
                    headers[header_name] = f"{prefix} {raw_token}"
            else:
                headers[header_name] = raw_token
        return headers

    def _queue_bundle(self, bundle: dict[str, Any], collection_id: str) -> Path:
        payload = {
            "queued_at": _utc_now_iso(),
            "server_url": self.server_url,
            "collection_id": collection_id,
            "bundle": bundle,
        }
        path = self.outbox_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}.json"
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        return path

    def _cache_inbox_bundle(self, bundle: dict[str, Any]) -> Path:
        payload = {"received_at": _utc_now_iso(), "bundle": bundle}
        path = self.inbox_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}-{uuid4().hex[:8]}.json"
        path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        return path

    def _flush_outbox(self) -> None:
        if not self.connected:
            return
        for path in sorted(self.outbox_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                bundle = payload.get("bundle")
                collection_id = str(payload.get("collection_id", self.collection_id or "")).strip()
                if not isinstance(bundle, dict) or not collection_id:
                    continue
                root = self._resolve_api_root(None)
                url = f"{root.rstrip('/')}/collections/{parse.quote(collection_id)}/objects/"
                self._request_json(
                    method="POST",
                    url=url,
                    headers={
                        "Accept": "application/taxii+json;version=2.1",
                        "Content-Type": "application/stix+json;version=2.1",
                    },
                    payload=bundle,
                )
                path.unlink(missing_ok=True)
            except Exception:
                self.connected = False
                break

    def _discovery_url(self) -> str:
        base = self.server_url
        if base.endswith("/taxii2"):
            return f"{base}/"
        return f"{base}/taxii2/"
