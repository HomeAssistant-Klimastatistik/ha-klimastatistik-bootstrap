"""aiohttp-Transport für den Releaseclient.

Getrennt vom Client gehalten, damit die gesamte Entscheidungslogik ohne
Netzwerk testbar bleibt. Diese Datei enthält bewusst keine Produktlogik.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

import aiohttp

from .core.client import Response, Transport

#: Zeitlimits. Der Metadatenabruf ist kurz, der Assetdownload großzügig.
METADATA_TIMEOUT = aiohttp.ClientTimeout(total=30)
DOWNLOAD_TIMEOUT = aiohttp.ClientTimeout(total=300, sock_read=60)

#: Obergrenze für einen einzelnen Download (Schutz gegen Fehlkonfiguration).
MAX_DOWNLOAD_BYTES = 64 * 1024 * 1024


class AiohttpTransport(Transport):
    """Transport auf Basis einer geteilten aiohttp-Session."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Transport mit der von Home Assistant verwalteten Session erzeugen."""
        self._session = session

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        allow_redirects: bool = True,
    ) -> Response:
        """Eine HTTP-Anfrage ausführen.

        `allow_redirects=False` wird für Release-Assets verwendet: aiohttp
        würde den Authorization-Header auf die vorsignierte Speicher-URL
        weiterreichen, was der Speicherdienst mit einem Fehler quittiert.
        Der Client führt die Weiterleitung deshalb selbst und ohne
        Authorization-Header aus.
        """
        timeout = (
            DOWNLOAD_TIMEOUT
            if headers.get("Accept", "").endswith("octet-stream")
            else METADATA_TIMEOUT
        )
        async with self._session.request(
            method,
            url,
            headers=dict(headers),
            allow_redirects=allow_redirects,
            timeout=timeout,
        ) as response:
            length = response.headers.get("Content-Length")
            if length is not None:
                try:
                    if int(length) > MAX_DOWNLOAD_BYTES:
                        raise aiohttp.ClientError("Antwort überschreitet die zulässige Größe.")
                except ValueError:
                    pass
            body = b""
            if response.status not in (301, 302, 303, 307, 308):
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.content.iter_chunked(1024 * 64):
                    total += len(chunk)
                    if total > MAX_DOWNLOAD_BYTES:
                        raise aiohttp.ClientError("Antwort überschreitet die zulässige Größe.")
                    chunks.append(chunk)
                body = b"".join(chunks)
            return Response(
                status=response.status,
                headers={key: value for key, value in response.headers.items()},
                body=body,
            )


async def sleep_for_retry(seconds: float) -> None:
    """Kurze Wartezeit für Wiederholungen."""
    await asyncio.sleep(max(0.0, min(seconds, 60.0)))
