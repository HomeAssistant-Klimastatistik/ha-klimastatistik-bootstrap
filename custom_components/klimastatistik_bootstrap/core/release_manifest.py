"""Release-Manifest: Erzeugung, Lesen und Prüfung (Auftrag Abschnitt 20).

Bewusst nicht selbstreferenziell:

* Im ZIP liegt `release_manifest.json` mit `asset_sha256: null` und einem
  `payload_sha256`, der ausschließlich über die übrigen Paketdateien gebildet
  wird.
* Als eigenes Release-Asset liegt dasselbe Manifest zusätzlich mit gefülltem
  `asset_sha256` (SHA-256 des fertigen ZIPs) daneben.

Prüfkette beim Update:
GitHub-API (TLS + Auth) -> Manifest-Asset -> SHA-256 des ZIP -> Entpacken ->
inneres Manifest muss dem äußeren gleichen (außer `asset_sha256`) ->
`payload_sha256` neu berechnen und vergleichen.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Final

from .errors import ChecksumMismatchError, ManifestError
from .version import InvalidVersionError, parse_version

MANIFEST_FILENAME: Final = "release_manifest.json"
MANIFEST_SCHEMA: Final = 1
PACKAGE_SCHEMA: Final = 1

CHANNEL_STABLE: Final = "stable"
CHANNEL_BETA: Final = "beta"
CHANNELS: Final = (CHANNEL_STABLE, CHANNEL_BETA)

_REQUIRED_KEYS: Final = (
    "manifest_schema",
    "product",
    "product_version",
    "package_schema",
    "migration_schema",
    "requires_migration_schemas",
    "min_home_assistant",
    "asset_name",
    "channel",
    "restart_required",
    "payload_sha256",
    "payload_files",
)


def sha256_bytes(data: bytes) -> str:
    """SHA-256 als Hexstring."""
    return hashlib.sha256(data).hexdigest()


def payload_digest(files: dict[str, str]) -> str:
    r"""Deterministischer Gesamt-Hash über die Paketdateien.

    Eingabe ist `{relativer Pfad: sha256}`. Der Digest ist der SHA-256 über
    die nach Pfad sortierte Zeilenform `"<sha256>  <pfad>\\n"`. Das ist stabil,
    plattformunabhängig und ohne den ZIP-Container reproduzierbar.
    """
    lines = "".join(f"{files[path]}  {path}\n" for path in sorted(files))
    return sha256_bytes(lines.encode("utf-8"))


@dataclass(slots=True)
class ReleaseManifest:
    """Maschinenlesbares Release-Manifest."""

    product_version: str
    migration_schema: int
    requires_migration_schemas: list[int]
    min_home_assistant: str
    asset_name: str
    channel: str
    payload_sha256: str
    payload_files: dict[str, str]
    restart_required: bool = True
    asset_sha256: str | None = None
    product: str = "klimastatistik"
    manifest_schema: int = MANIFEST_SCHEMA
    package_schema: int = PACKAGE_SCHEMA
    release_notes: str = ""
    release_url: str = ""
    release_title: str = ""
    engine: str = "sqlite-legacy"
    managed_files: list[str] = field(default_factory=list)
    integration_files: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    # -- Serialisierung -------------------------------------------------

    def as_dict(self, *, include_asset_sha256: bool = True) -> dict[str, Any]:
        """Serialisierbare Darstellung in stabiler Schlüsselreihenfolge."""
        data: dict[str, Any] = {
            "manifest_schema": self.manifest_schema,
            "product": self.product,
            "product_version": self.product_version,
            "package_schema": self.package_schema,
            "migration_schema": self.migration_schema,
            "requires_migration_schemas": sorted(self.requires_migration_schemas),
            "min_home_assistant": self.min_home_assistant,
            "engine": self.engine,
            "asset_name": self.asset_name,
            "asset_sha256": self.asset_sha256 if include_asset_sha256 else None,
            "channel": self.channel,
            "restart_required": self.restart_required,
            "payload_sha256": self.payload_sha256,
            "payload_files": dict(sorted(self.payload_files.items())),
            "managed_files": sorted(self.managed_files),
            "integration_files": sorted(self.integration_files),
            "release_title": self.release_title,
            "release_notes": self.release_notes,
            "release_url": self.release_url,
        }
        if self.extra:
            data["extra"] = self.extra
        return data

    def to_json(self, *, include_asset_sha256: bool = True) -> bytes:
        """Deterministische JSON-Darstellung (sortiert, UTF-8, abschließender Zeilenumbruch)."""
        return (
            json.dumps(
                self.as_dict(include_asset_sha256=include_asset_sha256),
                ensure_ascii=False,
                indent=2,
                sort_keys=False,
            )
            + "\n"
        ).encode("utf-8")

    @classmethod
    def from_dict(cls, raw: Any) -> ReleaseManifest:
        """Manifest aus einem Dictionary lesen und streng validieren."""
        if not isinstance(raw, dict):
            raise ManifestError("Release-Manifest ist kein JSON-Objekt.")
        missing = [key for key in _REQUIRED_KEYS if key not in raw]
        if missing:
            raise ManifestError(
                f"Release-Manifest unvollständig; fehlende Schlüssel: {sorted(missing)}"
            )
        if raw["manifest_schema"] != MANIFEST_SCHEMA:
            raise ManifestError(
                f"Unbekanntes Manifestschema {raw['manifest_schema']!r}; "
                f"erwartet {MANIFEST_SCHEMA}."
            )
        if raw["product"] != "klimastatistik":
            raise ManifestError(f"Fremdes Produkt im Manifest: {raw['product']!r}")
        if raw["channel"] not in CHANNELS:
            raise ManifestError(f"Unbekannter Releasekanal: {raw['channel']!r}")
        for key in ("product_version", "min_home_assistant"):
            try:
                parse_version(str(raw[key]))
            except InvalidVersionError as err:
                raise ManifestError(f"{key}: {err}") from err
        payload_files = raw["payload_files"]
        if not isinstance(payload_files, dict) or not payload_files:
            raise ManifestError("payload_files fehlt oder ist leer.")
        for path, digest in payload_files.items():
            if not isinstance(path, str) or not isinstance(digest, str):
                raise ManifestError("payload_files enthält ungültige Einträge.")
            if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
                raise ManifestError(f"Ungültiger SHA-256 für {path!r}.")
        requires = raw["requires_migration_schemas"]
        if not isinstance(requires, list) or not all(isinstance(i, int) for i in requires):
            raise ManifestError("requires_migration_schemas muss eine Ganzzahlliste sein.")
        return cls(
            product_version=str(raw["product_version"]),
            migration_schema=int(raw["migration_schema"]),
            requires_migration_schemas=[int(i) for i in requires],
            min_home_assistant=str(raw["min_home_assistant"]),
            asset_name=str(raw["asset_name"]),
            channel=str(raw["channel"]),
            payload_sha256=str(raw["payload_sha256"]),
            payload_files={str(k): str(v) for k, v in payload_files.items()},
            restart_required=bool(raw["restart_required"]),
            asset_sha256=raw.get("asset_sha256") or None,
            product=str(raw["product"]),
            manifest_schema=int(raw["manifest_schema"]),
            package_schema=int(raw["package_schema"]),
            release_notes=str(raw.get("release_notes", "")),
            release_url=str(raw.get("release_url", "")),
            release_title=str(raw.get("release_title", "")),
            engine=str(raw.get("engine", "sqlite-legacy")),
            managed_files=[str(i) for i in raw.get("managed_files", [])],
            integration_files=[str(i) for i in raw.get("integration_files", [])],
            extra=raw.get("extra", {}) or {},
        )

    @classmethod
    def from_json(cls, data: bytes | str) -> ReleaseManifest:
        """Manifest aus JSON-Bytes lesen."""
        try:
            raw = json.loads(data)
        except (ValueError, UnicodeDecodeError) as err:
            raise ManifestError(f"Release-Manifest ist kein gültiges JSON: {err}") from err
        return cls.from_dict(raw)

    # -- Prüfungen ------------------------------------------------------

    def verify_asset(self, asset_bytes: bytes) -> None:
        """SHA-256 des heruntergeladenen Assets gegen das Manifest prüfen."""
        if not self.asset_sha256:
            raise ManifestError(
                "Das Manifest enthält keinen asset_sha256. Für die Assetprüfung "
                "ist das eigenständige Manifest-Asset des Releases erforderlich."
            )
        actual = sha256_bytes(asset_bytes)
        if actual != self.asset_sha256:
            raise ChecksumMismatchError(
                f"SHA-256 des Assets weicht ab. Erwartet {self.asset_sha256}, berechnet {actual}."
            )

    def verify_payload(self, files: dict[str, str]) -> None:
        """Entpackten Paketinhalt gegen das Manifest prüfen."""
        expected = dict(self.payload_files)
        actual = dict(files)
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        if missing:
            raise ChecksumMismatchError(f"Im Paket fehlen Dateien: {missing}")
        if extra:
            raise ChecksumMismatchError(f"Im Paket liegen unerwartete Dateien: {extra}")
        changed = sorted(path for path in expected if expected[path] != actual[path])
        if changed:
            raise ChecksumMismatchError(f"Prüfsummen weichen ab: {changed}")
        digest = payload_digest(actual)
        if digest != self.payload_sha256:
            raise ChecksumMismatchError(
                f"payload_sha256 weicht ab. Erwartet {self.payload_sha256}, berechnet {digest}."
            )

    def assert_matches_inner(self, inner: ReleaseManifest) -> None:
        """Äußeres (Asset) und inneres (im ZIP) Manifest vergleichen.

        Beide müssen identisch sein; einzige zulässige Abweichung ist
        `asset_sha256`, der im inneren Manifest naturgemäß nicht stehen kann.
        """
        outer_data = self.as_dict(include_asset_sha256=False)
        inner_data = inner.as_dict(include_asset_sha256=False)
        if outer_data != inner_data:
            differing = sorted(
                key
                for key in set(outer_data) | set(inner_data)
                if outer_data.get(key) != inner_data.get(key)
            )
            raise ManifestError(
                "Inneres und äußeres Release-Manifest stimmen nicht überein. "
                f"Abweichende Felder: {differing}"
            )
        if inner.asset_sha256 is not None:
            raise ManifestError(
                "Das Manifest im Paket darf keinen asset_sha256 enthalten "
                "(selbstreferenzielle Prüfsumme)."
            )
