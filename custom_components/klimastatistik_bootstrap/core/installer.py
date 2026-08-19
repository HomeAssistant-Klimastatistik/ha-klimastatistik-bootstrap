"""Installation der privaten Integration aus einem geprüften Release-Asset.

Bewusst minimal: das öffentliche Bootstrap entpackt ein Paket, prüft dessen
Integrität und legt ausschliesslich `custom_components/klimastatistik/` an.

Es fasst NICHTS anderes an:

* keine `configuration.yaml`,
* keine Templates,
* keine Dashboards,
* keine Helper,
* kein `.storage`,
* keine Recorder-Datenbank.

Die eigentliche Produktverwaltung (Adoption, Managed Files, Backup, Rollback)
übernimmt danach die private Integration selbst.
"""

from __future__ import annotations

import hashlib
import io
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from typing import Final

from .errors import PackageStructureError
from .release_manifest import MANIFEST_FILENAME, ReleaseManifest

INTEGRATION_DOMAIN: Final = "klimastatistik"
INTEGRATION_PREFIX: Final = f"custom_components/{INTEGRATION_DOMAIN}/"

MAX_ARCHIVE_BYTES: Final = 64 * 1024 * 1024
MAX_FILE_BYTES: Final = 16 * 1024 * 1024
MAX_ENTRIES: Final = 2000


def _safe_member_name(name: str) -> str:
    """Archiveintrag prüfen und normalisieren."""
    if name.startswith("/") or name.startswith("\\") or ":" in name.split("/")[0]:
        raise PackageStructureError(f"Unzulässiger absoluter Pfad im Paket: {name!r}")
    pure = PurePosixPath(name.replace("\\", "/"))
    parts = [part for part in pure.parts if part != "."]
    if any(part == ".." for part in parts):
        raise PackageStructureError(f"Pfadausbruch im Paket: {name!r}")
    if not parts:
        raise PackageStructureError("Leerer Eintragsname im Paket.")
    return "/".join(parts)


def unpack_archive(archive: bytes, destination: str | Path) -> dict[str, str]:
    """ZIP entpacken und `{relativer Pfad: sha256}` zurückgeben."""
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    try:
        zip_file = zipfile.ZipFile(io.BytesIO(archive))
    except zipfile.BadZipFile as err:
        raise PackageStructureError(f"Das Paket ist kein lesbares ZIP-Archiv: {err}") from err

    with zip_file:
        infos = zip_file.infolist()
        if len(infos) > MAX_ENTRIES:
            raise PackageStructureError("Das Paket enthält zu viele Einträge.")
        if sum(info.file_size for info in infos) > MAX_ARCHIVE_BYTES:
            raise PackageStructureError("Das entpackte Paket ist zu groß.")

        result: dict[str, str] = {}
        for info in infos:
            mode = info.external_attr >> 16
            if mode and (mode & 0o170000) == 0o120000:
                raise PackageStructureError(f"Symlink im Paket ist unzulässig: {info.filename!r}")
            if info.is_dir():
                continue
            if info.file_size > MAX_FILE_BYTES:
                raise PackageStructureError(
                    f"Datei {info.filename!r} überschreitet die Einzelgröße."
                )
            name = _safe_member_name(info.filename)
            target = destination / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(info) as source, target.open("wb") as sink:
                digest = hashlib.sha256()
                while True:
                    chunk = source.read(1024 * 256)
                    if not chunk:
                        break
                    digest.update(chunk)
                    sink.write(chunk)
            result[name] = digest.hexdigest()
    return result


def payload_files_only(files: dict[str, str]) -> dict[str, str]:
    """Dateiliste ohne das Manifest selbst."""
    return {path: digest for path, digest in files.items() if path != MANIFEST_FILENAME}


def read_inner_manifest(payload_dir: str | Path) -> ReleaseManifest:
    """Das im Paket mitgelieferte Manifest lesen."""
    path = Path(payload_dir) / MANIFEST_FILENAME
    if not path.is_file():
        raise PackageStructureError(f"Im Paket fehlt {MANIFEST_FILENAME}.")
    return ReleaseManifest.from_json(path.read_bytes())


def verify_package(
    archive: bytes, payload_dir: str | Path, manifest: ReleaseManifest
) -> ReleaseManifest:
    """Vollständige Integritätskette prüfen und das Paket entpacken.

    Reihenfolge: SHA-256 des Assets, Entpacken, Dateiprüfsummen,
    Abgleich zwischen äußerem und innerem Manifest, Strukturprüfung.
    """
    manifest.verify_asset(archive)
    files = unpack_archive(archive, payload_dir)
    manifest.verify_payload(payload_files_only(files))
    inner = read_inner_manifest(payload_dir)
    manifest.assert_matches_inner(inner)

    payload_dir = Path(payload_dir)
    if not (payload_dir / INTEGRATION_PREFIX / "manifest.json").is_file():
        raise PackageStructureError(f"Im Paket fehlt die Integration unter {INTEGRATION_PREFIX}.")
    if not (payload_dir / INTEGRATION_PREFIX / "__init__.py").is_file():
        raise PackageStructureError("Die Integration im Paket ist unvollständig.")
    return inner


def _recover_interrupted_install(target: Path, previous: Path) -> None:
    """Einen abgebrochenen früheren Einsetzvorgang wiederherstellen.

    Das Ersetzen eines Verzeichnisses ist auf POSIX nicht atomar: zwischen
    `target -> previous` und `staging -> target` gibt es ein sehr kurzes
    Fenster. Stirbt der Prozess genau dort (SIGKILL, OOM, Stromausfall),
    existiert `custom_components/klimastatistik` nicht mehr, sondern nur noch
    `.klimastatistik.old`.

    Dieser Zustand wird beim nächsten Einsetzvorgang zuerst geheilt, damit
    kein Stand verloren geht. Weil in diesem Zustand die Integration selbst
    nicht lädt, ist der ausführende Akteur regelmässig das öffentliche
    Bootstrap - dort gilt dieselbe Heilung.
    """
    if not target.exists() and previous.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
        previous.rename(target)


def install_integration(payload_dir: str | Path, config_dir: str | Path) -> list[str]:
    """Die private Integration nach `custom_components/klimastatistik/` legen.

    Das Zielverzeichnis gehört ausschliesslich diesem Produkt und wird
    vollständig ersetzt. Ein bereits vorhandener Stand wird bis zum Abschluss
    beiseitegelegt und erst danach entfernt.
    """
    payload_dir = Path(payload_dir)
    config_dir = Path(config_dir)
    source = payload_dir / INTEGRATION_PREFIX
    if not (source / "manifest.json").is_file():
        raise PackageStructureError("Im Paket fehlt die Integration.")

    target = config_dir / "custom_components" / INTEGRATION_DOMAIN
    staging = config_dir / "custom_components" / f".{INTEGRATION_DOMAIN}.new"
    previous = config_dir / "custom_components" / f".{INTEGRATION_DOMAIN}.old"

    _recover_interrupted_install(target, previous)

    for directory in (staging, previous):
        if directory.exists():
            shutil.rmtree(directory)

    shutil.copytree(source, staging)
    installed = sorted(
        str(path.relative_to(staging)).replace("\\", "/")
        for path in staging.rglob("*")
        if path.is_file()
    )
    if "manifest.json" not in installed:
        shutil.rmtree(staging, ignore_errors=True)
        raise PackageStructureError("Die kopierte Integration ist unvollständig.")

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        if target.exists():
            target.rename(previous)
        staging.rename(target)
    except OSError:
        if not target.exists() and previous.exists():
            previous.rename(target)
        shutil.rmtree(staging, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(previous, ignore_errors=True)
    return installed


def installed_version(config_dir: str | Path) -> str | None:
    """Version einer bereits installierten privaten Integration lesen."""
    import json

    manifest = Path(config_dir) / "custom_components" / INTEGRATION_DOMAIN / "manifest.json"
    if not manifest.is_file():
        return None
    try:
        return str(json.loads(manifest.read_text(encoding="utf-8")).get("version") or "")
    except (OSError, ValueError):
        return None
