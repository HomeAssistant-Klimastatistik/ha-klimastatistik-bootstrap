"""Testvorrichtungen des öffentlichen Bootstraps.

Es wird kein Netzwerk, kein echter Token und kein privates Release benötigt.
Das Testpaket wird lokal erzeugt und trägt ausschliesslich synthetische Inhalte.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components"))
sys.path.insert(0, str(REPO_ROOT))

from klimastatistik_bootstrap.core.release_manifest import (  # noqa: E402
    MANIFEST_FILENAME,
    ReleaseManifest,
    payload_digest,
    sha256_bytes,
)

FIXED_DATE_TIME = (1980, 1, 1, 0, 0, 0)
FIXED_EXTERNAL_ATTR = (0o100644 & 0xFFFF) << 16

#: Minimalinhalt einer privaten Integration – ausschliesslich für Tests.
INTEGRATION_FILES = {
    "custom_components/klimastatistik/__init__.py": '"""Testintegration."""\n',
    "custom_components/klimastatistik/manifest.json": json.dumps(
        {
            "domain": "klimastatistik",
            "name": "Klimastatistik",
            "version": "2.3.0",
            "documentation": "https://example.invalid",
            "codeowners": [],
            "iot_class": "local_polling",
        },
        indent=2,
    )
    + "\n",
    "custom_components/klimastatistik/const.py": 'DOMAIN = "klimastatistik"\n',
}
MANAGED_FILES = {
    "managed/templates/klimamodul.yaml": "# Testinhalt\n",
    "managed/templates/klimasicherheit.yaml": "# Testinhalt\n",
    "managed/templates/klimatagesvergleich.yaml": "# Testinhalt\n",
    "managed/templates/klimavergleich.yaml": "# Testinhalt\n",
    "managed/dashboard/klimastatistik_dashboard_portabel.yaml": "# Testinhalt\n",
    "managed/configuration/klimastatistik_configuration_snippets.yaml": "# Testinhalt\n",
}


def build_package(version: str = "2.3.0", channel: str = "stable") -> tuple[bytes, ReleaseManifest]:
    """Ein vollständiges, gültiges Testpaket erzeugen."""
    files = {**INTEGRATION_FILES, **MANAGED_FILES}
    payload_files = {
        name: hashlib.sha256(content.encode()).hexdigest() for name, content in files.items()
    }
    manifest = ReleaseManifest(
        product_version=version,
        migration_schema=1,
        requires_migration_schemas=[0],
        min_home_assistant="2026.2.0",
        asset_name=f"ha-klimastatistik-{version}.zip",
        channel=channel,
        payload_sha256=payload_digest(payload_files),
        payload_files=payload_files,
        restart_required=True,
        managed_files=sorted(MANAGED_FILES),
        integration_files=sorted(INTEGRATION_FILES),
        release_title=f"Klimastatistik {version}",
    )

    entries = [(MANIFEST_FILENAME, manifest.to_json(include_asset_sha256=False))]
    entries += [(name, content.encode()) for name, content in files.items()]
    entries.sort(key=lambda item: item[0])

    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in entries:
            info = zipfile.ZipInfo(filename=name, date_time=FIXED_DATE_TIME)
            info.external_attr = FIXED_EXTERNAL_ATTR
            info.create_system = 3
            archive.writestr(info, data)
    payload = buffer.getvalue()
    manifest.asset_sha256 = sha256_bytes(payload)
    return payload, manifest


@pytest.fixture(scope="session")
def package() -> tuple[bytes, ReleaseManifest]:
    """Gültiges Testpaket."""
    return build_package()
