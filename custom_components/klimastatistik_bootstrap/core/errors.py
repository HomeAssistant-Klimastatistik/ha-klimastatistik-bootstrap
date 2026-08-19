"""Fehlerklassen des Produkts.

Wichtige Sicherheitsregel (Auftrag Abschnitt 17 und 32.5):
Keine Fehlermeldung dieses Moduls darf jemals einen Tokenwert enthalten.
`redact_secrets` wird defensiv auf jede Fehlermeldung angewendet.
"""

from __future__ import annotations

import re

# Bekannte GitHub-Tokenformate (github.blog, "new authentication token formats").
_TOKEN_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer|token)\s+\S+"),
    re.compile(
        r"(?i)(\"?(?:token|github_token|access_token|pat)\"?\s*[:=]\s*)\"?[A-Za-z0-9_\-]{12,}\"?"
    ),
)

REDACTED = "**REDACTED**"


def redact_secrets(text: str) -> str:
    """Alle erkennbaren Geheimnisse aus einem Text entfernen."""
    if not text:
        return text
    result = text
    result = _TOKEN_PATTERNS[0].sub(REDACTED, result)
    result = _TOKEN_PATTERNS[1].sub(REDACTED, result)
    result = _TOKEN_PATTERNS[2].sub(rf"\1\2 {REDACTED}", result)
    result = _TOKEN_PATTERNS[3].sub(rf"\1{REDACTED}", result)
    return result


class KlimastatistikError(Exception):
    """Basisfehler. Redigiert die eigene Meldung grundsätzlich."""

    #: Übersetzungsschlüssel für die Anzeige in Home Assistant.
    translation_key = "unknown"

    def __init__(self, message: str = "", *args: object) -> None:
        """Fehler erzeugen; die Meldung wird grundsätzlich redigiert."""
        super().__init__(redact_secrets(str(message)), *args)

    def __str__(self) -> str:
        """Redigierte Fehlermeldung."""
        return redact_secrets(super().__str__())


class ConfigurationError(KlimastatistikError):
    """Fehlerhafte oder unvollständige Konfiguration."""

    translation_key = "configuration_error"


# --- Netzwerk / GitHub -------------------------------------------------


class ReleaseAccessError(KlimastatistikError):
    """Oberklasse aller Releasezugriffsfehler."""

    translation_key = "release_access"


class NetworkError(ReleaseAccessError):
    """Netzwerkproblem; ausdrücklich kein Berechtigungsproblem."""

    translation_key = "network_error"


class AuthenticationError(ReleaseAccessError):
    """Token ungültig, abgelaufen oder widerrufen (HTTP 401)."""

    translation_key = "invalid_auth"


class PermissionError_(ReleaseAccessError):
    """Token gültig, aber ohne Zugriff auf das private Repository (HTTP 403/404)."""

    translation_key = "no_repository_access"


class RateLimitError(ReleaseAccessError):
    """GitHub-Rate-Limit erreicht."""

    translation_key = "rate_limit"

    def __init__(self, message: str = "", retry_after: float | None = None) -> None:
        """Fehler mit optionaler Wartezeit aus dem Retry-After-Header."""
        super().__init__(message)
        self.retry_after = retry_after


class ReleaseNotFoundError(ReleaseAccessError):
    """Kein passendes Release im gewählten Kanal."""

    translation_key = "release_not_found"


class AssetNotFoundError(ReleaseAccessError):
    """Release vorhanden, benötigtes Asset fehlt."""

    translation_key = "asset_not_found"


# --- Integrität / Paket ------------------------------------------------


class IntegrityError(KlimastatistikError):
    """Prüfsumme oder Paketstruktur stimmt nicht."""

    translation_key = "integrity_error"


class ChecksumMismatchError(IntegrityError):
    """SHA-256 des Assets weicht vom Manifest ab."""

    translation_key = "checksum_mismatch"


class ManifestError(IntegrityError):
    """Release-Manifest fehlt, ist unlesbar oder unvollständig."""

    translation_key = "manifest_error"


class PackageStructureError(IntegrityError):
    """Paketinhalt entspricht nicht dem erwarteten Aufbau."""

    translation_key = "package_structure"


# --- Migration / Adoption ----------------------------------------------


class MigrationError(KlimastatistikError):
    """Migrationsproblem."""

    translation_key = "migration_error"


class MigrationPathError(MigrationError):
    """Erforderliches Migrationsschema würde übersprungen."""

    translation_key = "migration_path"


class DowngradeError(MigrationError):
    """Das Ziel ist älter als der installierte Stand.

    Eine Rückstufung wird nicht als Update angeboten und nicht ausgeführt:
    sie setzte `product_version` zurück und protokollierte einen Rückschritt
    als Update. Für einen bewussten Rückschritt gibt es den Dienst
    `klimastatistik.rollback` auf ein Backup.
    """

    translation_key = "downgrade_refused"


class AdoptionError(KlimastatistikError):
    """Bestehende Installation konnte nicht sicher übernommen werden."""

    translation_key = "adoption_error"


class LocalModificationError(AdoptionError):
    """Lokal veränderte Managed-Datei; nicht überschreiben."""

    translation_key = "local_modification"


class InconsistentSourceError(AdoptionError):
    """Die fünf Quellsensorstellen enthalten unterschiedliche IDs."""

    translation_key = "inconsistent_source"


class UnsupportedHomeAssistantError(KlimastatistikError):
    """Home-Assistant-Version unterschreitet die Mindestanforderung."""

    translation_key = "unsupported_ha"


class InstallationError(KlimastatistikError):
    """Ein Schreib- oder Dateisystemfehler während einer verwalteten Operation.

    Kapselt `OSError` (voller Datenträger, fehlende Rechte, schreibgeschütztes
    Dateisystem). Ohne diese Kapselung verliess ein roher `OSError` den
    Dienstaufruf ungefangen.
    """

    translation_key = "installation_failed"


class ConcurrentOperationError(KlimastatistikError):
    """Es läuft bereits eine verwaltete Operation."""

    translation_key = "operation_in_progress"
