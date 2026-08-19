"""Transportfreie GitHub-Logik: Header, Antwortdeutung, Releaseauswahl.

Bewusst ohne Netzwerkbibliothek, damit die gesamte Entscheidungslogik ohne
Home Assistant und ohne echte GitHub-Zugangsdaten testbar ist
(Auftrag Abschnitt 33 und 35).

Sicherheitsregeln dieses Moduls:

* Tokenwerte werden ausschließlich in `build_headers` verwendet.
* Es gibt keine Funktion, die einen Token zurückgibt oder in eine Meldung
  schreibt. `describe_request` existiert ausdrücklich als tokenfreie
  Protokollform.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from .errors import (
    AssetNotFoundError,
    AuthenticationError,
    NetworkError,
    PermissionError_,
    RateLimitError,
    ReleaseNotFoundError,
)
from .release_manifest import CHANNEL_BETA, CHANNEL_STABLE, MANIFEST_FILENAME
from .version import InvalidVersionError, compare_versions, parse_version

API_ROOT: Final = "https://api.github.com"
API_VERSION: Final = "2022-11-28"
ACCEPT_JSON: Final = "application/vnd.github+json"
ACCEPT_BINARY: Final = "application/octet-stream"
USER_AGENT: Final = "ha-klimastatistik"

#: Assetnamen, die ein Release mitbringen muss.
MANIFEST_ASSET_NAME: Final = MANIFEST_FILENAME
CHECKSUM_ASSET_NAME: Final = "SHA256SUMS.txt"


def releases_url(owner: str, repo: str, *, per_page: int = 30, page: int = 1) -> str:
    """URL zum Auflisten der Releases."""
    return f"{API_ROOT}/repos/{owner}/{repo}/releases?per_page={per_page}&page={page}"


def repository_url(owner: str, repo: str) -> str:
    """URL des Repositories (für den Zugriffstest)."""
    return f"{API_ROOT}/repos/{owner}/{repo}"


def asset_url(owner: str, repo: str, asset_id: int) -> str:
    """URL eines Release-Assets."""
    return f"{API_ROOT}/repos/{owner}/{repo}/releases/assets/{asset_id}"


def build_headers(
    token: str | None,
    *,
    accept: str = ACCEPT_JSON,
    etag: str | None = None,
    user_agent: str = USER_AGENT,
) -> dict[str, str]:
    """Anfrageheader erzeugen.

    `User-Agent` ist bei GitHub Pflicht; fehlt er, antwortet die API mit 403.
    """
    headers = {
        "Accept": accept,
        "X-GitHub-Api-Version": API_VERSION,
        "User-Agent": user_agent,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if etag:
        headers["If-None-Match"] = etag
    return headers


def describe_request(method: str, url: str) -> str:
    """Tokenfreie Beschreibung einer Anfrage für Protokolle."""
    return f"{method.upper()} {url}"


def strip_authorization(headers: Mapping[str, str]) -> dict[str, str]:
    """Header ohne Authorization.

    Wird für Weiterleitungen auf die vorsignierte Speicher-URL benötigt.
    Wird der Authorization-Header mitgeschickt, lehnt der Speicherdienst die
    Anfrage ab ("Only one auth mechanism allowed").
    """
    return {key: value for key, value in headers.items() if key.lower() != "authorization"}


@dataclass(slots=True)
class RateLimitInfo:
    """Auswertung der Rate-Limit-Header."""

    limit: int | None = None
    remaining: int | None = None
    reset: int | None = None
    retry_after: float | None = None

    @property
    def exhausted(self) -> bool:
        """True, wenn kein Kontingent mehr übrig ist."""
        return self.remaining is not None and self.remaining <= 0


def parse_rate_limit(headers: Mapping[str, str]) -> RateLimitInfo:
    """Rate-Limit-Header lesen (Groß-/Kleinschreibung egal)."""
    lowered = {key.lower(): value for key, value in headers.items()}

    def _int(name: str) -> int | None:
        raw = lowered.get(name)
        try:
            return int(raw) if raw is not None else None
        except (TypeError, ValueError):
            return None

    retry_after: float | None = None
    raw_retry = lowered.get("retry-after")
    if raw_retry is not None:
        try:
            retry_after = float(raw_retry)
        except (TypeError, ValueError):
            retry_after = None

    return RateLimitInfo(
        limit=_int("x-ratelimit-limit"),
        remaining=_int("x-ratelimit-remaining"),
        reset=_int("x-ratelimit-reset"),
        retry_after=retry_after,
    )


def raise_for_status(
    status: int,
    headers: Mapping[str, str],
    *,
    context: str,
    body_snippet: str = "",
) -> None:
    """HTTP-Status in eine präzise, tokenfreie Fehlerklasse übersetzen.

    Unterscheidet ausdrücklich zwischen Netzwerkfehler, Authentisierungsfehler,
    fehlender Repository-Berechtigung und Rate Limit (Auftrag Abschnitt 17).
    """
    if 200 <= status < 300 or status == 304:
        return

    rate = parse_rate_limit(headers)

    if status == 401:
        raise AuthenticationError(
            f"{context}: Der GitHub-Token wurde abgelehnt (HTTP 401). "
            "Er ist ungültig, abgelaufen oder widerrufen."
        )
    if status == 403:
        if rate.exhausted or "rate limit" in body_snippet.lower():
            raise RateLimitError(
                f"{context}: GitHub-Rate-Limit erreicht (HTTP 403).",
                retry_after=rate.retry_after,
            )
        raise PermissionError_(
            f"{context}: Zugriff verweigert (HTTP 403). Der Token hat keine "
            "Leseberechtigung für dieses private Repository."
        )
    if status == 429:
        raise RateLimitError(
            f"{context}: Zu viele Anfragen (HTTP 429).", retry_after=rate.retry_after
        )
    if status == 404:
        raise PermissionError_(
            f"{context}: Nicht gefunden (HTTP 404). Bei privaten Repositories "
            "bedeutet das in aller Regel fehlende Berechtigung, nicht ein "
            "fehlendes Repository."
        )
    if 500 <= status < 600:
        raise NetworkError(f"{context}: GitHub meldet einen Serverfehler (HTTP {status}).")
    raise NetworkError(f"{context}: Unerwartete Antwort (HTTP {status}).")


@dataclass(slots=True)
class ReleaseAsset:
    """Ein Release-Asset."""

    asset_id: int
    name: str
    size: int
    content_type: str = ""

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> ReleaseAsset:
        """Aus der API-Antwort lesen."""
        return cls(
            asset_id=int(raw.get("id", 0)),
            name=str(raw.get("name", "")),
            size=int(raw.get("size", 0)),
            content_type=str(raw.get("content_type", "")),
        )


@dataclass(slots=True)
class ReleaseInfo:
    """Ein GitHub-Release in der für dieses Produkt relevanten Form."""

    tag_name: str
    name: str
    draft: bool
    prerelease: bool
    html_url: str
    body: str
    published_at: str
    assets: list[ReleaseAsset] = field(default_factory=list)

    @property
    def version(self) -> str:
        """Produktversion aus dem Tag (führendes v wird entfernt)."""
        return self.tag_name[1:] if self.tag_name.startswith("v") else self.tag_name

    @property
    def is_prerelease_version(self) -> bool:
        """True, wenn schon der Versionsstring eine Vorabkennung trägt."""
        try:
            return parse_version(self.version).is_prerelease
        except InvalidVersionError:
            return False

    @property
    def channel(self) -> str:
        """Kanal, dem das Release angehört.

        Bestimmt aus **beiden** Signalen: dem GitHub-Häkchen `prerelease` und
        dem Versionsstring. Ein Release `2.4.0-beta.1` gehört in den
        Beta-Kanal, auch wenn das Häkchen fehlt oder später entfernt wird.

        Zuvor hing die Zuordnung allein am Häkchen. Ein `workflow_dispatch` mit
        einer Beta-Version und dem Standardkanal `stable` erzeugte ein
        widerspruchsfreies Stable-Release; und wurde ein Beta-Release später
        von Hand zu "nicht Prerelease" befördert, widersprachen sich Häkchen
        und Manifest, was die Update-Entity für alle Nutzer unbrauchbar machte.
        """
        return CHANNEL_BETA if (self.prerelease or self.is_prerelease_version) else CHANNEL_STABLE

    def asset(self, name: str) -> ReleaseAsset | None:
        """Asset nach Namen suchen."""
        for item in self.assets:
            if item.name == name:
                return item
        return None

    def require_asset(self, name: str) -> ReleaseAsset:
        """Asset nach Namen suchen oder Fehler werfen."""
        found = self.asset(name)
        if found is None:
            raise AssetNotFoundError(
                f"Release {self.tag_name} enthält kein Asset {name!r}. "
                f"Vorhanden: {sorted(item.name for item in self.assets)}"
            )
        return found

    @classmethod
    def from_api(cls, raw: Mapping[str, Any]) -> ReleaseInfo:
        """Aus der API-Antwort lesen."""
        return cls(
            tag_name=str(raw.get("tag_name", "")),
            name=str(raw.get("name") or raw.get("tag_name", "")),
            draft=bool(raw.get("draft", False)),
            prerelease=bool(raw.get("prerelease", False)),
            html_url=str(raw.get("html_url", "")),
            body=str(raw.get("body") or ""),
            published_at=str(raw.get("published_at") or ""),
            assets=[ReleaseAsset.from_api(item) for item in raw.get("assets", []) or []],
        )


def parse_releases(payload: Any) -> list[ReleaseInfo]:
    """Antwort von `GET /releases` lesen."""
    if not isinstance(payload, list):
        raise NetworkError("Unerwartete Antwortform beim Auflisten der Releases.")
    return [ReleaseInfo.from_api(item) for item in payload if isinstance(item, dict)]


def select_release(
    releases: Iterable[ReleaseInfo],
    *,
    channel: str = CHANNEL_STABLE,
    required_asset: str | None = None,
) -> ReleaseInfo | None:
    """Höchstes zulässiges Release des gewählten Kanals bestimmen.

    Entwurfsentscheidung (siehe Architektur-Gate): Draft-Releases werden
    grundsätzlich ignoriert. Sie sind über die GitHub-API nur mit
    Schreibberechtigung sichtbar; ein Beta-Kanal auf Draft-Basis würde einen
    schreibfähigen Token beim Tester erzwingen. Die Closed Beta läuft deshalb
    über Prereleases.

    Stable-Nutzer erhalten niemals ein Prerelease.
    """
    candidates: list[ReleaseInfo] = []
    for release in releases:
        if release.draft:
            continue
        try:
            parsed = parse_version(release.version)
        except InvalidVersionError:
            continue
        # Die Kanalzuordnung hängt NICHT allein am GitHub-Häkchen
        # `prerelease`, sondern zusätzlich am Versionsstring (siehe
        # `ReleaseInfo.channel`).
        if channel == CHANNEL_STABLE and (release.prerelease or parsed.is_prerelease):
            continue
        if required_asset and release.asset(required_asset) is None:
            continue
        candidates.append(release)

    if not candidates:
        return None

    import functools

    candidates.sort(
        key=functools.cmp_to_key(lambda a, b: compare_versions(a.version, b.version)),
        reverse=True,
    )
    return candidates[0]


def parse_checksums(text: str) -> dict[str, str]:
    """`SHA256SUMS.txt` im Format `<sha256>  <dateiname>` lesen."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split(None, 1)
        if len(parts) != 2:
            continue
        digest, name = parts[0].strip(), parts[1].strip().lstrip("*")
        if len(digest) == 64:
            result[name] = digest.lower()
    return result


def ensure_release_found(release: ReleaseInfo | None, channel: str) -> ReleaseInfo:
    """Release oder präziser Fehler."""
    if release is None:
        raise ReleaseNotFoundError(
            f"Im Kanal {channel!r} wurde kein installierbares Release gefunden."
        )
    return release
