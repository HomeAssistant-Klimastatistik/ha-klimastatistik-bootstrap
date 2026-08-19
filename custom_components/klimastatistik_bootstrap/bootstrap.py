"""Beschaffungslogik des Bootstraps.

Kapselt: Zugriffstest, Releaseauswahl, Manifestprüfung, Assetdownload,
Integritätsprüfung, Entpacken und Installation der privaten Integration.

Sicherheitszusage dieses Moduls: der Token wird ausschliesslich an den
`ReleaseClient` übergeben. Er wird nicht protokolliert, nicht in Rückgabewerte
geschrieben und nicht in Fehlermeldungen aufgenommen.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import PRODUCT_DOMAIN, STAGING_DIR
from .core.client import ReleaseClient
from .core.errors import KlimastatistikError, redact_secrets
from .core.github import ReleaseInfo
from .core.installer import (
    install_integration,
    installed_version,
    verify_package,
)
from .core.release_manifest import CHANNEL_STABLE, ReleaseManifest
from .core.version import meets_minimum

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class InstallOutcome:
    """Ergebnis einer Bootstrap-Installation."""

    product_version: str
    release_tag: str
    channel: str
    asset_name: str
    asset_sha256: str
    installed_files: list[str] = field(default_factory=list)
    restart_required: bool = True
    previous_version: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Tokenfreie, serialisierbare Darstellung."""
        return {
            "product_version": self.product_version,
            "release_tag": self.release_tag,
            "channel": self.channel,
            "asset_name": self.asset_name,
            "asset_sha256": self.asset_sha256,
            "installed_files": len(self.installed_files),
            "restart_required": self.restart_required,
            "previous_version": self.previous_version,
        }


async def async_verify_access(client: ReleaseClient) -> str:
    """Zugriff auf das private Repository prüfen.

    Der reine Besitz des Bootstraps gewährt keinen Zugriff. Ohne gültige
    Berechtigung schlägt bereits dieser Aufruf fehl und es wird nichts
    heruntergeladen oder installiert.
    """
    result = await client.check_access()
    return result.full_name


async def async_resolve(
    client: ReleaseClient, *, channel: str = CHANNEL_STABLE
) -> tuple[ReleaseInfo, ReleaseManifest]:
    """Zielrelease und geprüftes Manifest bestimmen."""
    release = await client.resolve_release(channel=channel)
    manifest = await client.fetch_manifest(release)
    return release, manifest


async def async_install(
    hass: HomeAssistant,
    client: ReleaseClient,
    release: ReleaseInfo,
    manifest: ReleaseManifest,
    *,
    home_assistant_version: str,
) -> InstallOutcome:
    """Die private Integration herunterladen, prüfen und installieren."""
    if not meets_minimum(home_assistant_version, manifest.min_home_assistant):
        raise KlimastatistikError(
            f"Dieses Release benötigt mindestens Home Assistant "
            f"{manifest.min_home_assistant}; installiert ist {home_assistant_version}."
        )

    archive = await client.download_package(release, manifest)
    await client.verify_release_consistency(release, manifest, archive)

    config_dir = Path(hass.config.path())
    staging = config_dir / STAGING_DIR

    def _install() -> tuple[list[str], str | None]:
        previous = installed_version(config_dir)
        try:
            verify_package(archive, staging, manifest)
            files = install_integration(staging, config_dir)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        return files, previous

    files, previous = await hass.async_add_executor_job(_install)

    _LOGGER.info(
        "Klimastatistik %s wurde installiert (%d Dateien). Ein Neustart ist erforderlich.",
        manifest.product_version,
        len(files),
    )
    return InstallOutcome(
        product_version=manifest.product_version,
        release_tag=release.tag_name,
        channel=manifest.channel,
        asset_name=manifest.asset_name,
        asset_sha256=manifest.asset_sha256 or "",
        installed_files=files,
        restart_required=manifest.restart_required,
        previous_version=previous,
    )


async def async_installed_product_version(hass: HomeAssistant) -> str | None:
    """Bereits installierte Version der privaten Integration lesen."""
    config_dir = Path(hass.config.path())
    return await hass.async_add_executor_job(installed_version, config_dir)


def describe_error(err: Exception) -> str:
    """Fehler tokenfrei beschreiben."""
    return redact_secrets(str(err)) or type(err).__name__


PRODUCT_INTEGRATION_PATH = f"custom_components/{PRODUCT_DOMAIN}"
