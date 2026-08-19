"""Testtransport für den Releaseclient.

Simuliert die GitHub-API vollständig ohne Netzwerk und ohne echten Token.
Alle Tokenwerte in Tests sind synthetisch (Auftrag Abschnitt 32.5).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from klimastatistik_bootstrap.core.client import Response

#: Ausschliesslich synthetische Testtoken. Format ist nachgebildet, der Wert
#: ist frei erfunden und funktionslos.
VALID_TOKEN = "github_pat_TESTONLY0000000000000000000000000000valid"
INVALID_TOKEN = "github_pat_TESTONLY0000000000000000000000000invalid"
NOACCESS_TOKEN = "github_pat_TESTONLY000000000000000000000000noaccess"

OWNER = "HomeAssistant-Klimastatistik"
REPO = "ha-klimastatistik"


@dataclass(slots=True)
class Recorded:
    """Eine aufgezeichnete Anfrage."""

    method: str
    url: str
    headers: dict[str, str]
    allow_redirects: bool


@dataclass
class FakeTransport:
    """Konfigurierbarer Transport."""

    releases: list[dict[str, Any]] = field(default_factory=list)
    assets: dict[int, bytes] = field(default_factory=dict)
    token: str = VALID_TOKEN
    repository_private: bool = True
    fail_with: Exception | None = None
    force_status: int | None = None
    rate_limit_remaining: int = 4999
    etag: str = 'W/"abc123"'
    use_redirect: bool = True
    redirect_host: str = "https://objects.example.invalid/download"
    calls: list[Recorded] = field(default_factory=list)
    handler: Callable[[str, str, Mapping[str, str]], Response | None] | None = None

    # -- Hilfen ---------------------------------------------------------

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": str(self.rate_limit_remaining),
            "X-RateLimit-Reset": "1800000000",
            "ETag": self.etag,
            "Content-Type": "application/json",
        }
        headers.update(extra or {})
        return headers

    def _auth_status(self, headers: Mapping[str, str]) -> int | None:
        authorization = headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return 401
        token = authorization.removeprefix("Bearer ")
        if token == INVALID_TOKEN:
            return 401
        if token == NOACCESS_TOKEN:
            return 404
        if token != self.token:
            return 401
        return None

    # -- Transport ------------------------------------------------------

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        allow_redirects: bool = True,
    ) -> Response:
        """Anfrage beantworten."""
        self.calls.append(Recorded(method, url, dict(headers), allow_redirects))
        if self.fail_with is not None:
            raise self.fail_with
        if self.handler is not None:
            custom = self.handler(method, url, headers)
            if custom is not None:
                return custom

        # Weiterleitungsziel: hier darf kein Authorization-Header ankommen.
        if url.startswith(self.redirect_host):
            if "Authorization" in headers:
                return Response(
                    status=400,
                    headers=self._headers(),
                    body=b'{"message":"Only one auth mechanism allowed"}',
                )
            asset_id = int(url.rsplit("/", 1)[-1])
            return Response(
                status=200,
                headers=self._headers({"Content-Type": "application/octet-stream"}),
                body=self.assets.get(asset_id, b""),
            )

        status = self._auth_status(headers)
        if self.force_status is not None:
            extra = {}
            if self.force_status in (403, 429):
                extra["X-RateLimit-Remaining"] = "0"
                extra["Retry-After"] = "60"
            return Response(
                status=self.force_status,
                headers=self._headers(extra),
                body=b'{"message":"API rate limit exceeded"}'
                if self.force_status in (403, 429)
                else b'{"message":"error"}',
            )
        if status is not None:
            return Response(
                status=status,
                headers=self._headers(),
                body=b'{"message":"Bad credentials"}'
                if status == 401
                else b'{"message":"Not Found"}',
            )

        if url.endswith(f"/repos/{OWNER}/{REPO}"):
            body = json.dumps(
                {
                    "full_name": f"{OWNER}/{REPO}",
                    "private": self.repository_private,
                }
            ).encode()
            return Response(status=200, headers=self._headers(), body=body)

        if "/releases?" in url or url.endswith("/releases"):
            if headers.get("If-None-Match") == self.etag:
                return Response(status=304, headers=self._headers(), body=b"")
            return Response(
                status=200,
                headers=self._headers(),
                body=json.dumps(self.releases).encode(),
            )

        if "/releases/assets/" in url:
            asset_id = int(url.rsplit("/", 1)[-1])
            if asset_id not in self.assets:
                return Response(
                    status=404, headers=self._headers(), body=b'{"message":"Not Found"}'
                )
            if self.use_redirect:
                return Response(
                    status=302,
                    headers=self._headers({"Location": f"{self.redirect_host}/{asset_id}"}),
                    body=b"",
                )
            return Response(
                status=200,
                headers=self._headers({"Content-Type": "application/octet-stream"}),
                body=self.assets[asset_id],
            )

        return Response(status=404, headers=self._headers(), body=b'{"message":"Not Found"}')


def make_release(
    tag: str,
    *,
    assets: dict[str, int],
    prerelease: bool = False,
    draft: bool = False,
    body: str = "",
) -> dict[str, Any]:
    """Ein Release im API-Format erzeugen."""
    return {
        "tag_name": tag,
        "name": f"Klimastatistik {tag}",
        "draft": draft,
        "prerelease": prerelease,
        "html_url": f"https://github.com/{OWNER}/{REPO}/releases/tag/{tag}",
        "body": body,
        "published_at": "2026-08-17T10:00:00Z",
        "assets": [
            {"id": asset_id, "name": name, "size": 1, "content_type": "application/zip"}
            for name, asset_id in assets.items()
        ],
    }
