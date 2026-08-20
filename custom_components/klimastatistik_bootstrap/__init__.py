"""HA Klimastatistik Bootstrap – öffentlicher Zugangspunkt.

Dieses Repository ist öffentlich. Es enthält ausschliesslich den technisch
notwendigen Erstzugang zum privaten Produkt:

* Tokeneingabe,
* Zugriffstest,
* Abruf privater Release-Metadaten,
* Download und Integritätsprüfung,
* Installation der privaten Integration.

Es enthält KEINE Klimaberechnung, KEINE privaten Release-Assets und KEINEN
eingebetteten Zugangstoken. Die blosse Installation dieses Bootstraps gewährt
keinerlei Zugriff auf das private Produkt.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import issue_registry as ir

from .bootstrap import (
    async_installed_product_version,
    product_installed_this_process,
)
from .const import (
    CONF_TOKEN,
    DATA_HANDOVER_COMPLETE,
    DATA_INSTALLED_VERSION,
    DATA_RESTART_REQUIRED,
    DOMAIN,
    ISSUE_HANDOVER_PENDING,
    ISSUE_RESTART_REQUIRED,
    MIN_HOME_ASSISTANT,
    PRODUCT_DOMAIN,
)
from .core.version import InvalidVersionError, meets_minimum

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Bootstrap-Eintrag einrichten."""
    ha_version = str(hass.config.as_dict().get("version", "0.0.0"))
    # Wie in der Hauptintegration: eine unlesbare Versionszeichenkette lässt
    # keinen Schluss auf "zu alt" zu. Ein `ConfigEntryNotReady` erzeugte hier
    # eine endlose Wiederholung; die Schranke wird deshalb mit einer Warnung
    # übersprungen statt stillschweigend als bestanden gewertet.
    try:
        too_old = not meets_minimum(ha_version, MIN_HOME_ASSISTANT)
    except InvalidVersionError:
        _LOGGER.warning(
            "Klimastatistik-Bootstrap: Die Home-Assistant-Version %r konnte nicht "
            "gelesen werden. Die Mindestversionsprüfung gegen %s wird übersprungen.",
            ha_version,
            MIN_HOME_ASSISTANT,
        )
        too_old = False
    if too_old:
        raise ConfigEntryNotReady(
            f"Das Bootstrap benötigt mindestens Home Assistant "
            f"{MIN_HOME_ASSISTANT}; installiert ist {ha_version}."
        )

    installed = await async_installed_product_version(hass)
    entry.runtime_data = {"installed_product_version": installed}

    product_entries = hass.config_entries.async_entries(PRODUCT_DOMAIN)
    token_present = bool(entry.data.get(CONF_TOKEN))
    handover_done = bool(entry.data.get(DATA_HANDOVER_COMPLETE))

    restart_required = bool(entry.data.get(DATA_RESTART_REQUIRED))

    # Das persistente Neustart-Flag bleibt bei einem blossen Config-Entry-Reload
    # bestehen. Nach einem echten Home-Assistant-Neustart ist die rein
    # flüchtige Installationsmarkierung aus `hass.data` dagegen verschwunden.
    # Liegt die installierte Produktintegration weiterhin auf der Platte, ist
    # der zuvor verlangte Neustart damit tatsächlich erfolgt.
    if (
        restart_required
        and installed is not None
        and not product_installed_this_process(hass, installed)
    ):
        data = dict(entry.data)
        data[DATA_RESTART_REQUIRED] = False
        hass.config_entries.async_update_entry(entry, data=data)
        restart_required = False

    if installed is None:
        # Die private Integration liegt (noch) nicht auf der Platte.
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_RESTART_REQUIRED,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_RESTART_REQUIRED,
            translation_placeholders={
                "version": str(entry.data.get(DATA_INSTALLED_VERSION, "")),
            },
        )
    elif restart_required and not product_entries:
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_RESTART_REQUIRED,
            is_fixable=True,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_RESTART_REQUIRED,
            translation_placeholders={
                "version": str(entry.data.get(DATA_INSTALLED_VERSION, "")),
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_RESTART_REQUIRED)

    if installed is not None and not product_entries and token_present:
        # Die Integration liegt bereit, ist aber noch nicht eingerichtet.
        ir.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_HANDOVER_PENDING,
            is_fixable=False,
            is_persistent=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=ISSUE_HANDOVER_PENDING,
            translation_placeholders={"version": installed},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_HANDOVER_PENDING)

    if handover_done and token_present:  # pragma: no cover - Konsistenzhinweis
        _LOGGER.debug(
            "Bootstrap: Übergabe ist als abgeschlossen markiert, es liegt aber "
            "noch eine Tokenkopie vor."
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Nach Änderungen (etwa der Tokenübergabe) neu laden."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Bootstrap-Eintrag entladen."""
    ir.async_delete_issue(hass, DOMAIN, ISSUE_RESTART_REQUIRED)
    ir.async_delete_issue(hass, DOMAIN, ISSUE_HANDOVER_PENDING)
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Entry-Schema migrieren."""
    return entry.version <= 1
