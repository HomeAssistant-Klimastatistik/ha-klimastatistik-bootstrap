"""Privater Releaseclient.

Der Client ist transportagnostisch: er spricht ausschließlich über das
`Transport`-Protokoll. Dadurch laufen sämtliche Auth-, Fehler-, Integritäts-
und Kanalfälle in Unit-Tests ohne Netzwerk und ohne echten Token
(Auftrag Abschnitt 32.3 und 35).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .errors import (
    AssetNotFoundError,
    ChecksumMismatchError,
    NetworkError,
    ReleaseAccessError,
)
from .github import (
    ACCEPT_BINARY,
    ACCEPT_JSON,
    CHECKSUM_ASSET_NAME,
    MANIFEST_ASSET_NAME,
    ReleaseInfo,
    asset_url,
    build_headers,
    ensure_release_found,
    parse_checksums,
    parse_rate_limit,
    parse_releases,
    raise_for_status,
    releases_url,
    repository_url,
    select_release,
    strip_authorization,
)
from .release_manifest import CHANNEL_BETA, CHANNEL_STABLE, ReleaseManifest, sha256_bytes
from .version import is_prerelease_version


@dataclass(slots=True)
class Response:
    """Transportantwort."""

    status: int
    headers: Mapping[str, str]
    body: bytes

    @property
    def text(self) -> str:
        """Antworttext in UTF-8."""
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """Antwort als JSON."""
        try:
            return json.loads(self.body)
        except ValueError as err:
            raise NetworkError(f"Antwort ist kein gültiges JSON: {err}") from err


class Transport(Protocol):
    """Minimaler HTTP-Transport."""

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        allow_redirects: bool = True,
    ) -> Response:  # pragma: no cover - Protokoll
        """Eine HTTP-Anfrage ausführen."""
        ...


@dataclass(slots=True)
class AccessCheck:
    """Ergebnis des Zugriffstests."""

    ok: bool
    private: bool
    full_name: str
    detail: str = ""


class ReleaseClient:
    """Liest private Releases, Manifeste und Assets."""

    def __init__(
        self,
        transport: Transport,
        *,
        owner: str,
        repo: str,
        token: str | None,
        user_agent: str = "ha-klimastatistik",
    ) -> None:
        """Client erzeugen. Der Token wird ausschließlich in Headern verwendet."""
        self._transport = transport
        self._owner = owner
        self._repo = repo
        self._token = token
        self._user_agent = user_agent
        self._etag: str | None = None
        self._cached_releases: list[ReleaseInfo] = []
        self.last_rate_limit = None

    # -- Basis ----------------------------------------------------------

    async def _get(
        self,
        url: str,
        *,
        accept: str = ACCEPT_JSON,
        etag: str | None = None,
        context: str,
        allow_redirects: bool = True,
    ) -> Response:
        headers = build_headers(self._token, accept=accept, etag=etag, user_agent=self._user_agent)
        try:
            response = await self._transport.request(
                "GET", url, headers=headers, allow_redirects=allow_redirects
            )
        except ReleaseAccessError:
            raise
        except Exception as err:  # Transportfehler -> Netzwerkfehler
            raise NetworkError(f"{context}: Netzwerkfehler ({type(err).__name__}).") from err
        self.last_rate_limit = parse_rate_limit(response.headers)
        raise_for_status(
            response.status,
            response.headers,
            context=context,
            body_snippet=response.text[:400],
        )
        return response

    # -- Zugriffstest ---------------------------------------------------

    async def check_access(self) -> AccessCheck:
        """Prüfen, ob der Token dieses private Repository lesen darf."""
        response = await self._get(
            repository_url(self._owner, self._repo),
            context="Zugriffstest auf das private Repository",
        )
        data = response.json()
        if not isinstance(data, dict):
            raise NetworkError("Unerwartete Antwortform beim Zugriffstest.")
        return AccessCheck(
            ok=True,
            private=bool(data.get("private", True)),
            full_name=str(data.get("full_name", f"{self._owner}/{self._repo}")),
        )

    # -- Releases -------------------------------------------------------

    async def list_releases(self, *, use_cache: bool = True) -> list[ReleaseInfo]:
        """Releases auflisten; nutzt ETag, damit 304 kein Kontingent kostet."""
        response = await self._get(
            releases_url(self._owner, self._repo),
            etag=self._etag if use_cache else None,
            context="Auflisten der privaten Releases",
        )
        if response.status == 304 and self._cached_releases:
            return list(self._cached_releases)
        etag = None
        for key, value in response.headers.items():
            if key.lower() == "etag":
                etag = value
                break
        self._etag = etag
        self._cached_releases = parse_releases(response.json())
        return list(self._cached_releases)

    async def resolve_release(
        self, *, channel: str = CHANNEL_STABLE, use_cache: bool = True
    ) -> ReleaseInfo:
        """Das für den Kanal maßgebliche Release bestimmen."""
        releases = await self.list_releases(use_cache=use_cache)
        selected = select_release(releases, channel=channel, required_asset=MANIFEST_ASSET_NAME)
        return ensure_release_found(selected, channel)

    # -- Assets ---------------------------------------------------------

    async def download_asset(self, release: ReleaseInfo, name: str) -> bytes:
        """Ein Release-Asset herunterladen.

        Wichtig: GitHub antwortet auf die Asset-URL mit einer Weiterleitung auf
        eine vorsignierte Speicher-URL. Der Authorization-Header darf dorthin
        NICHT mitgeschickt werden, sonst lehnt der Speicherdienst ab. Deshalb
        wird die Weiterleitung hier bewusst selbst ausgeführt.
        """
        asset = release.require_asset(name)
        url = asset_url(self._owner, self._repo, asset.asset_id)
        headers = build_headers(self._token, accept=ACCEPT_BINARY, user_agent=self._user_agent)
        try:
            response = await self._transport.request(
                "GET", url, headers=headers, allow_redirects=False
            )
        except Exception as err:
            raise NetworkError(
                f"Download von {name!r}: Netzwerkfehler ({type(err).__name__})."
            ) from err
        self.last_rate_limit = parse_rate_limit(response.headers)

        if response.status in (301, 302, 303, 307, 308):
            location = None
            for key, value in response.headers.items():
                if key.lower() == "location":
                    location = value
                    break
            if not location:
                raise NetworkError(f"Download von {name!r}: Weiterleitung ohne Zieladresse.")
            try:
                response = await self._transport.request(
                    "GET",
                    location,
                    headers=strip_authorization(headers),
                    allow_redirects=True,
                )
            except Exception as err:
                raise NetworkError(
                    f"Download von {name!r}: Netzwerkfehler beim Abruf des Assets "
                    f"({type(err).__name__})."
                ) from err

        raise_for_status(
            response.status,
            response.headers,
            context=f"Download von {name!r}",
            body_snippet=response.text[:200] if response.status >= 400 else "",
        )
        if not response.body:
            raise AssetNotFoundError(f"Asset {name!r} ist leer.")
        return response.body

    async def fetch_manifest(self, release: ReleaseInfo) -> ReleaseManifest:
        """Das eigenständige Manifest-Asset laden und prüfen."""
        raw = await self.download_asset(release, MANIFEST_ASSET_NAME)
        manifest = ReleaseManifest.from_json(raw)
        if manifest.product_version != release.version:
            raise ChecksumMismatchError(
                "Die Produktversion im Manifest passt nicht zum Release-Tag: "
                f"Manifest {manifest.product_version!r}, Tag {release.tag_name!r}."
            )
        if manifest.channel != release.channel:
            raise ChecksumMismatchError(
                "Der Kanal im Manifest passt nicht zum Releasetyp: "
                f"Manifest {manifest.channel!r}, Release {release.channel!r}."
            )
        # Dritte, unabhängige Querprüfung: der Kanal muss zum VERSIONSSTRING
        # passen. Ohne sie konnte ein `workflow_dispatch` mit einer
        # Beta-Version und dem Standardkanal `stable` ein in sich
        # widerspruchsfreies Stable-Release erzeugen und eine Vorabversion an
        # alle Stable-Nutzer ausliefern.
        expected_channel = (
            CHANNEL_BETA if is_prerelease_version(manifest.product_version) else CHANNEL_STABLE
        )
        if manifest.channel != expected_channel:
            raise ChecksumMismatchError(
                f"Die Version {manifest.product_version!r} gehört in den Kanal "
                f"{expected_channel!r}, das Manifest nennt aber "
                f"{manifest.channel!r}."
            )
        if not manifest.asset_sha256:
            raise ChecksumMismatchError("Das Manifest-Asset enthält keinen asset_sha256.")
        # Ein Release ohne das im Manifest benannte Paket wird nicht angeboten.
        # Zuvor scheiterte es erst bei der Installation.
        release.require_asset(manifest.asset_name)
        return manifest

    async def download_package(self, release: ReleaseInfo, manifest: ReleaseManifest) -> bytes:
        """Das Produktpaket laden und gegen das Manifest verifizieren."""
        archive = await self.download_asset(release, manifest.asset_name)
        manifest.verify_asset(archive)
        return archive

    async def fetch_checksums(self, release: ReleaseInfo) -> dict[str, str]:
        """Optionales `SHA256SUMS.txt` laden (menschliche Gegenprobe)."""
        if release.asset(CHECKSUM_ASSET_NAME) is None:
            return {}
        raw = await self.download_asset(release, CHECKSUM_ASSET_NAME)
        return parse_checksums(raw.decode("utf-8", errors="replace"))

    async def verify_release_consistency(
        self, release: ReleaseInfo, manifest: ReleaseManifest, archive: bytes
    ) -> None:
        """Optionale Gegenprobe gegen die menschenlesbare Prüfsummendatei."""
        checksums = await self.fetch_checksums(release)
        if not checksums:
            return
        expected = checksums.get(manifest.asset_name)
        if expected and expected != sha256_bytes(archive):
            raise ChecksumMismatchError(
                f"{CHECKSUM_ASSET_NAME} widerspricht dem heruntergeladenen Asset."
            )
