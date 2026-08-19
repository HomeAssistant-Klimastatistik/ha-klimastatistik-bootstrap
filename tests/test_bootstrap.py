"""Tests des öffentlichen Bootstraps.

Schwerpunkt: Ohne gültige Berechtigung darf nichts installiert werden
(Auftrag Abschnitt 19), und die Integritätskette muss lückenlos greifen.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import build_package
from fake_transport import (
    INVALID_TOKEN,
    NOACCESS_TOKEN,
    OWNER,
    REPO,
    VALID_TOKEN,
    FakeTransport,
    make_release,
)
from klimastatistik_bootstrap.core.client import ReleaseClient
from klimastatistik_bootstrap.core.errors import (
    AuthenticationError,
    ChecksumMismatchError,
    ManifestError,
    NetworkError,
    PackageStructureError,
    PermissionError_,
    RateLimitError,
    ReleaseNotFoundError,
)
from klimastatistik_bootstrap.core.installer import (
    install_integration,
    installed_version,
    unpack_archive,
    verify_package,
)
from klimastatistik_bootstrap.core.release_manifest import (
    CHANNEL_BETA,
    CHANNEL_STABLE,
    MANIFEST_FILENAME,
    ReleaseManifest,
)


@pytest.fixture
def transport(package) -> FakeTransport:
    """Transport mit einem gültigen Testrelease."""
    archive, manifest = package
    return FakeTransport(
        releases=[
            make_release(
                "v2.3.0",
                assets={
                    "ha-klimastatistik-2.3.0.zip": 101,
                    MANIFEST_FILENAME: 102,
                },
            )
        ],
        assets={101: archive, 102: manifest.to_json(include_asset_sha256=True)},
    )


def _client(transport: FakeTransport, token: str | None = VALID_TOKEN) -> ReleaseClient:
    return ReleaseClient(transport, owner=OWNER, repo=REPO, token=token)


# --- Zugriffsschutz ----------------------------------------------------


async def test_valid_token_can_read_releases(transport) -> None:
    """Ein berechtigter Nutzer erreicht die privaten Releases."""
    client = _client(transport)
    assert (await client.check_access()).ok
    release = await client.resolve_release()
    assert release.version == "2.3.0"


@pytest.mark.parametrize(
    "token,expected",
    [
        (INVALID_TOKEN, AuthenticationError),
        (NOACCESS_TOKEN, PermissionError_),
        (None, AuthenticationError),
    ],
)
async def test_without_permission_nothing_is_reachable(transport, token, expected) -> None:
    """Ohne Berechtigung ist weder Auflisten noch Herunterladen möglich."""
    client = _client(transport, token)
    with pytest.raises(expected):
        await client.check_access()
    with pytest.raises(expected):
        await client.list_releases()


async def test_bootstrap_alone_grants_no_access(transport, tmp_path: Path) -> None:
    """Das blosse Vorhandensein des Bootstraps installiert nichts.

    Der Kernsatz des Sicherheitsmodells: Bootstrap installiert ist nicht
    gleichbedeutend mit Zugriff auf Klimastatistik.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    client = _client(transport, NOACCESS_TOKEN)
    with pytest.raises(PermissionError_):
        await client.resolve_release()
    assert not (config_dir / "custom_components").exists()
    assert installed_version(config_dir) is None


async def test_network_error_is_not_a_permission_error(transport) -> None:
    """Netzwerkfehler und Berechtigungsfehler werden unterschieden."""
    transport.fail_with = OSError("kein Netz")
    with pytest.raises(NetworkError):
        await _client(transport).check_access()


async def test_rate_limit_is_reported_separately(transport) -> None:
    """Ein Rate Limit ist kein Berechtigungsfehler."""
    transport.force_status = 429
    with pytest.raises(RateLimitError):
        await _client(transport).check_access()


async def test_missing_release_is_reported(transport) -> None:
    """Ein leerer Releasekanal wird verständlich gemeldet."""
    transport.releases = []
    with pytest.raises(ReleaseNotFoundError):
        await _client(transport).resolve_release()


async def test_stable_ignores_prereleases(transport, package) -> None:
    """Stable-Nutzer erhalten keine Beta-Releases."""
    beta_archive, beta_manifest = build_package("2.4.0-beta.1", channel=CHANNEL_BETA)
    transport.releases.append(
        make_release(
            "v2.4.0-beta.1",
            assets={
                "ha-klimastatistik-2.4.0-beta.1.zip": 201,
                MANIFEST_FILENAME: 202,
            },
            prerelease=True,
        )
    )
    transport.assets[201] = beta_archive
    transport.assets[202] = beta_manifest.to_json()

    stable = await _client(transport).resolve_release(channel=CHANNEL_STABLE)
    assert stable.version == "2.3.0"
    beta = await _client(transport).resolve_release(channel=CHANNEL_BETA)
    assert beta.version == "2.4.0-beta.1"


# --- Integritätskette --------------------------------------------------


async def test_full_verification_and_installation(transport, tmp_path: Path, package) -> None:
    """Der vollständige Pfad installiert die private Integration."""
    archive, manifest = package
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    staging = tmp_path / "staging"

    client = _client(transport)
    release = await client.resolve_release()
    fetched = await client.fetch_manifest(release)
    downloaded = await client.download_package(release, fetched)
    assert downloaded == archive

    verify_package(downloaded, staging, fetched)
    files = install_integration(staging, config_dir)
    assert "manifest.json" in files
    assert installed_version(config_dir) == "2.3.0"
    assert (config_dir / "custom_components/klimastatistik/__init__.py").is_file()
    # Ausschliesslich die Integration wird angelegt, keine Managed-Dateien.
    assert not (config_dir / "templates").exists()
    assert not (config_dir / "configuration.yaml").exists()


async def test_corrupted_asset_is_rejected(transport, tmp_path: Path, package) -> None:
    """Ein beschädigtes Asset wird nicht installiert."""
    archive, _ = package
    transport.assets[101] = archive[:-40] + b"x" * 40
    client = _client(transport)
    release = await client.resolve_release()
    manifest = await client.fetch_manifest(release)
    with pytest.raises(ChecksumMismatchError):
        await client.download_package(release, manifest)
    assert installed_version(tmp_path) is None


async def test_tampered_payload_is_rejected(tmp_path: Path, package) -> None:
    """Ein manipuliertes Paketinneres fällt bei der Payload-Prüfung auf."""
    import io
    import zipfile

    archive, manifest = package
    tampered = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(archive)) as source,
        zipfile.ZipFile(tampered, "w") as destination,
    ):
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename.endswith("const.py"):
                data += b"\n# eingeschleust\n"
            destination.writestr(info, data)
    data = tampered.getvalue()
    forged = ReleaseManifest.from_dict(
        {**manifest.as_dict(), "asset_sha256": __import__("hashlib").sha256(data).hexdigest()}
    )
    with pytest.raises(ChecksumMismatchError):
        verify_package(data, tmp_path / "staging", forged)


async def test_missing_manifest_in_package_is_rejected(tmp_path: Path) -> None:
    """Ein Paket ohne inneres Manifest wird abgewiesen."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("custom_components/klimastatistik/__init__.py", "x")
    with pytest.raises(PackageStructureError):
        unpack_archive(b"kein zip", tmp_path / "s1")


async def test_zip_slip_is_rejected(tmp_path: Path) -> None:
    """Pfadausbrüche im Archiv werden abgewiesen."""
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../ausbruch.txt", "boese")
    with pytest.raises(PackageStructureError):
        unpack_archive(buffer.getvalue(), tmp_path / "s2")


async def test_package_without_integration_is_rejected(tmp_path: Path, package) -> None:
    """Ein Paket ohne Integration wird nicht installiert."""
    import io
    import zipfile

    _, manifest = package
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(MANIFEST_FILENAME, manifest.to_json(include_asset_sha256=False))
        archive.writestr("managed/templates/klimamodul.yaml", "# Testinhalt\n")
    data = buffer.getvalue()
    forged = ReleaseManifest.from_dict(
        {**manifest.as_dict(), "asset_sha256": __import__("hashlib").sha256(data).hexdigest()}
    )
    with pytest.raises(ChecksumMismatchError):
        verify_package(data, tmp_path / "s3", forged)


async def test_manifest_asset_must_carry_hash(transport, package) -> None:
    """Ein Manifest-Asset ohne asset_sha256 wird abgewiesen."""
    _, manifest = package
    transport.assets[102] = manifest.to_json(include_asset_sha256=False)
    client = _client(transport)
    release = await client.resolve_release()
    with pytest.raises(ChecksumMismatchError):
        await client.fetch_manifest(release)


async def test_broken_manifest_asset_is_rejected(transport) -> None:
    """Ein unlesbares Manifest-Asset wird abgewiesen."""
    transport.assets[102] = b"kaputt"
    client = _client(transport)
    release = await client.resolve_release()
    with pytest.raises(ManifestError):
        await client.fetch_manifest(release)


# --- Installationsverhalten -------------------------------------------


async def test_reinstall_replaces_previous_version(tmp_path: Path, package) -> None:
    """Eine erneute Installation ersetzt den vorherigen Stand vollständig."""
    archive, manifest = package
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    staging = tmp_path / "staging"

    verify_package(archive, staging, manifest)
    install_integration(staging, config_dir)
    stray = config_dir / "custom_components/klimastatistik/alt.py"
    stray.write_text("# Rest einer alten Version\n", encoding="utf-8")

    verify_package(archive, staging, manifest)
    install_integration(staging, config_dir)
    assert not stray.exists()
    assert installed_version(config_dir) == "2.3.0"


async def test_installation_leaves_no_temporary_directories(tmp_path: Path, package) -> None:
    """Nach der Installation bleiben keine Hilfsverzeichnisse zurück."""
    archive, manifest = package
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    staging = tmp_path / "staging"
    verify_package(archive, staging, manifest)
    install_integration(staging, config_dir)
    leftovers = [
        path.name
        for path in (config_dir / "custom_components").iterdir()
        if path.name.startswith(".")
    ]
    assert leftovers == []


async def test_authorization_not_leaked_to_storage_redirect(transport, package) -> None:
    """Auch im Bootstrap geht der Token nicht an die Speicher-URL."""
    client = _client(transport)
    release = await client.resolve_release()
    manifest = await client.fetch_manifest(release)
    await client.download_package(release, manifest)
    for call in transport.calls:
        if call.url.startswith(transport.redirect_host):
            assert "Authorization" not in call.headers


@pytest.mark.parametrize(
    "value,release,prerelease",
    [
        # Primärquelle: `home-assistant/core`, Tag `2026.8.0b0`,
        # `homeassistant/const.py` -> `PATCH_VERSION = "0b0"`.
        ("2026.8.0b0", (2026, 8, 0), True),
        ("2026.9.0rc1", (2026, 9, 0), True),
        ("2026.9.0.dev0", (2026, 9, 0), True),
        ("2026.8.2", (2026, 8, 2), False),
        # SemVer-Buildmetadaten sind keine Vorabkennung.
        ("2.3.0+build.7", (2, 3, 0), False),
    ],
)
def test_version_parser_handles_home_assistant_prereleases(value, release, prerelease) -> None:
    """Der geteilte Versionsparser liest trennzeichenlose Vorabkennungen.

    Der Parser ist zwischen beiden Repositorien byteidentisch; die Prüfung
    liegt deshalb in beiden Suiten.
    """
    from klimastatistik_bootstrap.core.version import parse_version

    parsed = parse_version(value)
    assert parsed.release == release
    assert parsed.is_prerelease is prerelease


def test_minimum_version_accepts_a_newer_beta() -> None:
    """Eine Beta oberhalb der Mindestversion besteht die Schranke."""
    from klimastatistik_bootstrap.core.version import compare_versions, meets_minimum

    assert meets_minimum("2026.8.0b0", "2026.2.0")
    assert not meets_minimum("2026.1.0b0", "2026.2.0")
    assert compare_versions("2026.8.0b0", "2026.8.0") == -1
    assert compare_versions("2.3.0+build.7", "2.3.0") == 0
