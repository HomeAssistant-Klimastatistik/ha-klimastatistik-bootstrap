"""Config Flow des öffentlichen Bootstraps.

Ablauf (Auftrag Abschnitt 18):
Token eingeben -> Zugriff prüfen -> privates Release ermitteln -> Asset laden
-> Manifest und Integrität prüfen -> private Integration installieren ->
Neustart anzeigen.

Ohne gültige Berechtigung endet der Flow mit einer verständlichen Meldung und
es wird nichts installiert.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .bootstrap import async_install, async_resolve, async_verify_access, describe_error
from .const import (
    CONF_CHANNEL,
    CONF_OWNER,
    CONF_REPO,
    CONF_TOKEN,
    DATA_HANDOVER_COMPLETE,
    DATA_INSTALLED_AT,
    DATA_INSTALLED_VERSION,
    DATA_RESTART_REQUIRED,
    DEFAULT_OWNER,
    DEFAULT_REPO,
    DOMAIN,
    NAME,
    REQUIRED_TOKEN_PERMISSION,
    VERSION,
)
from .core.client import ReleaseClient
from .core.errors import (
    AssetNotFoundError,
    AuthenticationError,
    ChecksumMismatchError,
    IntegrityError,
    KlimastatistikError,
    NetworkError,
    PermissionError_,
    RateLimitError,
    ReleaseNotFoundError,
)
from .core.release_manifest import CHANNEL_BETA, CHANNEL_STABLE
from .transport import AiohttpTransport

_LOGGER = logging.getLogger(__name__)

_TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_CHANNEL_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[CHANNEL_STABLE, CHANNEL_BETA],
        mode=SelectSelectorMode.DROPDOWN,
        translation_key="channel",
    )
)


def _schema(owner: str, repo: str, channel: str) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_TOKEN): _TOKEN_SELECTOR,
            vol.Optional(CONF_OWNER, default=owner): str,
            vol.Optional(CONF_REPO, default=repo): str,
            vol.Optional(CONF_CHANNEL, default=channel): _CHANNEL_SELECTOR,
        }
    )


def _error_key(err: Exception) -> str:
    """Fehlerklasse in einen Formularschlüssel übersetzen."""
    if isinstance(err, AuthenticationError):
        return "invalid_auth"
    if isinstance(err, PermissionError_):
        return "no_repository_access"
    if isinstance(err, RateLimitError):
        return "rate_limit"
    if isinstance(err, NetworkError):
        return "cannot_connect"
    if isinstance(err, ReleaseNotFoundError):
        return "release_not_found"
    if isinstance(err, AssetNotFoundError):
        return "asset_not_found"
    if isinstance(err, ChecksumMismatchError):
        return "checksum_mismatch"
    if isinstance(err, IntegrityError):
        return "integrity_error"
    return "unknown"


class BootstrapConfigFlow(ConfigFlow, domain=DOMAIN):
    """Erstinstallation der privaten Integration."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Token entgegennehmen und die private Integration installieren."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        owner, repo, channel = DEFAULT_OWNER, DEFAULT_REPO, CHANNEL_STABLE
        errors: dict[str, str] = {}
        placeholders = {
            "repository": f"{owner}/{repo}",
            "permission": REQUIRED_TOKEN_PERMISSION,
        }

        if user_input is None:
            return self.async_show_form(
                step_id="user",
                data_schema=_schema(owner, repo, channel),
                description_placeholders=placeholders,
            )

        owner = str(user_input.get(CONF_OWNER) or DEFAULT_OWNER).strip()
        repo = str(user_input.get(CONF_REPO) or DEFAULT_REPO).strip()
        channel = str(user_input.get(CONF_CHANNEL) or CHANNEL_STABLE)
        token = str(user_input[CONF_TOKEN]).strip()
        placeholders["repository"] = f"{owner}/{repo}"

        client = ReleaseClient(
            AiohttpTransport(async_get_clientsession(self.hass)),
            owner=owner,
            repo=repo,
            token=token,
            user_agent=f"ha-klimastatistik-bootstrap/{VERSION}",
        )

        try:
            await async_verify_access(client)
            release, manifest = await async_resolve(client, channel=channel)
            outcome = await async_install(
                self.hass,
                client,
                release,
                manifest,
                home_assistant_version=str(self.hass.config.as_dict().get("version", "0.0.0")),
            )
        except KlimastatistikError as err:
            errors["base"] = _error_key(err)
            _LOGGER.debug("Bootstrap fehlgeschlagen: %s", describe_error(err))
            placeholders["error"] = describe_error(err)[:300]
            return self.async_show_form(
                step_id="user",
                data_schema=_schema(owner, repo, channel),
                errors=errors,
                description_placeholders=placeholders,
            )

        return self.async_create_entry(
            title=NAME,
            data={
                # Der Token bleibt genau so lange hier liegen, bis die private
                # Integration ihn übernommen hat. Danach entfernt sie ihn
                # (siehe klimastatistik/config_flow.py).
                CONF_TOKEN: token,
                CONF_OWNER: owner,
                CONF_REPO: repo,
                CONF_CHANNEL: channel,
                DATA_INSTALLED_VERSION: outcome.product_version,
                DATA_INSTALLED_AT: outcome.release_tag,
                DATA_RESTART_REQUIRED: outcome.restart_required,
                DATA_HANDOVER_COMPLETE: False,
            },
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Erneute Tokeneingabe."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Neuen Token prüfen."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            token = str(user_input[CONF_TOKEN]).strip()
            client = ReleaseClient(
                AiohttpTransport(async_get_clientsession(self.hass)),
                owner=str(entry.data.get(CONF_OWNER, DEFAULT_OWNER)),
                repo=str(entry.data.get(CONF_REPO, DEFAULT_REPO)),
                token=token,
                user_agent=f"ha-klimastatistik-bootstrap/{VERSION}",
            )
            try:
                await async_verify_access(client)
            except KlimastatistikError as err:
                errors["base"] = _error_key(err)
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): _TOKEN_SELECTOR}),
            errors=errors,
            description_placeholders={
                "repository": f"{entry.data.get(CONF_OWNER)}/{entry.data.get(CONF_REPO)}",
                "permission": REQUIRED_TOKEN_PERMISSION,
            },
        )
