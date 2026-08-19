"""Diagnostics des Bootstraps – ausdrücklich ohne jeden Tokenwert."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .bootstrap import async_installed_product_version
from .const import (
    CONF_TOKEN,
    DATA_HANDOVER_COMPLETE,
    PRODUCT_DOMAIN,
    SENSITIVE_KEYS,
    VERSION,
)
from .core.errors import redact_secrets

TO_REDACT = set(SENSITIVE_KEYS)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Diagnosedaten liefern."""
    payload: dict[str, Any] = {
        "bootstrap_version": VERSION,
        "home_assistant_version": hass.config.as_dict().get("version"),
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "installed_product_version": await async_installed_product_version(hass),
        "product_entry_configured": bool(hass.config_entries.async_entries(PRODUCT_DOMAIN)),
        "token_present": bool(entry.data.get(CONF_TOKEN)),
        "handover_complete": bool(entry.data.get(DATA_HANDOVER_COMPLETE)),
    }
    serialised = json.dumps(payload, ensure_ascii=False, default=str)
    return json.loads(redact_secrets(serialised))
