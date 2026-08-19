"""Konstanten des öffentlichen Bootstraps.

Dieses Modul enthält bewusst KEINE Zugangsdaten. Es steht in einem
öffentlichen Repository und ist als vollständig einsehbar zu behandeln.
"""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "klimastatistik_bootstrap"
NAME: Final = "HA Klimastatistik Bootstrap"
VERSION: Final = "2.3.0"

#: Domain der privaten Hauptintegration, die installiert wird.
PRODUCT_DOMAIN: Final = "klimastatistik"

DEFAULT_OWNER: Final = "HomeAssistant-Klimastatistik"
DEFAULT_REPO: Final = "ha-klimastatistik-distribution"

MIN_HOME_ASSISTANT: Final = "2026.2.0"

CONF_TOKEN: Final = "github_token"
CONF_OWNER: Final = "owner"
CONF_REPO: Final = "repo"
CONF_CHANNEL: Final = "channel"

DATA_INSTALLED_VERSION: Final = "installed_product_version"
DATA_INSTALLED_AT: Final = "installed_at"
DATA_HANDOVER_COMPLETE: Final = "handover_complete"
DATA_RESTART_REQUIRED: Final = "restart_required"

SENSITIVE_KEYS: Final[tuple[str, ...]] = (
    CONF_TOKEN,
    "token",
    "access_token",
    "authorization",
    "Authorization",
    "pat",
)

ISSUE_RESTART_REQUIRED: Final = "restart_required"
ISSUE_HANDOVER_PENDING: Final = "handover_pending"

#: Temporäres Entpackverzeichnis unterhalb der HA-Konfiguration.
STAGING_DIR: Final = "klimastatistik_bootstrap_staging"

#: Hinweis für die Dokumentation und die Oberfläche.
REQUIRED_TOKEN_PERMISSION: Final = "Contents: Read-only"
