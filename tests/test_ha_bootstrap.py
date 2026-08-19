"""Integrationstests des Bootstraps gegen eine echte Home-Assistant-Instanz."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fake_transport import (
    INVALID_TOKEN,
    NOACCESS_TOKEN,
    OWNER,
    REPO,
    VALID_TOKEN,
    FakeTransport,
    make_release,
)
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.klimastatistik_bootstrap.const import (
    CONF_CHANNEL,
    CONF_OWNER,
    CONF_REPO,
    CONF_TOKEN,
    DATA_HANDOVER_COMPLETE,
    DATA_INSTALLED_VERSION,
    DOMAIN,
    ISSUE_RESTART_REQUIRED,
)
from custom_components.klimastatistik_bootstrap.core.release_manifest import (
    MANIFEST_FILENAME,
)


@pytest.fixture(autouse=True)
def _no_socket(socket_enabled):
    """Der Fake-Transport benötigt kein Netzwerk."""
    return socket_enabled


@pytest.fixture(autouse=True)
def isolated_config_dir(hass: HomeAssistant, enable_custom_integrations, tmp_path: Path):
    """Eigenes Konfigurationsverzeichnis je Test."""
    from homeassistant import loader

    config_dir = tmp_path / "config"
    (config_dir / "custom_components").mkdir(parents=True, exist_ok=True)
    hass.config.config_dir = str(config_dir)
    hass.data.pop(loader.DATA_CUSTOM_COMPONENTS, None)
    yield config_dir


@pytest.fixture
def transport(package) -> FakeTransport:
    """Transport mit gültigem Testrelease."""
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


@pytest.fixture(autouse=True)
def patch_transport(transport):
    """aiohttp-Transport durch den Fake ersetzen."""
    with patch(
        "custom_components.klimastatistik_bootstrap.config_flow.AiohttpTransport",
        return_value=transport,
    ):
        yield transport


async def test_flow_installs_private_integration(
    hass: HomeAssistant, isolated_config_dir: Path
) -> None:
    """Der Bootstrap-Flow installiert die private Integration."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_TOKEN: VALID_TOKEN, CONF_OWNER: OWNER, CONF_REPO: REPO},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][DATA_INSTALLED_VERSION] == "2.3.0"
    assert result["data"][DATA_HANDOVER_COMPLETE] is False
    installed = isolated_config_dir / "custom_components/klimastatistik/manifest.json"
    assert installed.is_file()
    # Es wird ausschliesslich die Integration angelegt.
    assert not (isolated_config_dir / "templates").exists()
    assert not (isolated_config_dir / "configuration.yaml").exists()


@pytest.mark.parametrize(
    "token,expected",
    [(INVALID_TOKEN, "invalid_auth"), (NOACCESS_TOKEN, "no_repository_access")],
)
async def test_flow_without_permission_installs_nothing(
    hass: HomeAssistant, isolated_config_dir: Path, token, expected
) -> None:
    """Ohne Berechtigung wird nichts installiert und nichts eingerichtet."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_TOKEN: token})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    assert not hass.config_entries.async_entries(DOMAIN)
    assert not (isolated_config_dir / "custom_components/klimastatistik").exists()


async def test_flow_reports_network_problem_distinctly(
    hass: HomeAssistant, transport: FakeTransport
) -> None:
    """Ein Netzwerkproblem wird nicht als Berechtigungsproblem dargestellt."""
    transport.fail_with = OSError("kein Netz")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: VALID_TOKEN}
    )
    assert result["errors"] == {"base": "cannot_connect"}


async def test_flow_reports_corrupted_asset(
    hass: HomeAssistant, transport: FakeTransport, package
) -> None:
    """Ein beschädigtes Asset führt zu einer klaren Meldung ohne Installation."""
    archive, _ = package
    transport.assets[101] = archive[:-32] + b"x" * 32
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: VALID_TOKEN}
    )
    assert result["errors"] == {"base": "checksum_mismatch"}
    assert not hass.config_entries.async_entries(DOMAIN)


async def test_entry_creates_restart_issue(hass: HomeAssistant, isolated_config_dir: Path) -> None:
    """Nach der Installation wird der erforderliche Neustart angezeigt."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: VALID_TOKEN}
    )
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state is config_entries.ConfigEntryState.LOADED

    registry = ir.async_get(hass)
    issue = registry.async_get_issue(DOMAIN, ISSUE_RESTART_REQUIRED)
    assert issue is not None
    assert issue.is_fixable


async def test_diagnostics_contain_no_token(hass: HomeAssistant, isolated_config_dir: Path) -> None:
    """Diagnosedaten des Bootstraps enthalten keinen Token."""
    import json

    from custom_components.klimastatistik_bootstrap.diagnostics import (
        async_get_config_entry_diagnostics,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={
            CONF_TOKEN: VALID_TOKEN,
            CONF_OWNER: OWNER,
            CONF_REPO: REPO,
            CONF_CHANNEL: "stable",
            DATA_INSTALLED_VERSION: "2.3.0",
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    payload = await async_get_config_entry_diagnostics(hass, entry)
    serialised = json.dumps(payload, ensure_ascii=False)
    assert VALID_TOKEN not in serialised
    assert payload["entry_data"]["github_token"] == "**REDACTED**"
    assert payload["token_present"] is True


async def test_single_instance(hass: HomeAssistant) -> None:
    """Nur ein Bootstrap-Eintrag ist möglich."""
    entry = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN, data={})
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] in ("already_configured", "single_instance_allowed")


@pytest.mark.parametrize(
    "ha_version",
    [
        # Trennzeichenlose Vorabkennungen, wie Home Assistant sie tatsächlich
        # trägt. Primärquelle: `home-assistant/core`, Tag `2026.8.0b0`,
        # `homeassistant/const.py` -> `PATCH_VERSION = "0b0"`.
        "2026.8.0b0",
        "2026.9.0rc1",
        "2026.9.0.dev0",
    ],
)
async def test_entry_sets_up_on_a_home_assistant_prerelease(
    hass: HomeAssistant, isolated_config_dir: Path, ha_version: str
) -> None:
    """Auf einer HA-Beta oder -RC lädt auch das Bootstrap.

    Der geteilte Versionsparser ist zwischen beiden Repositorien
    byteidentisch; der Befund traf deshalb beide Integrationen.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_TOKEN: VALID_TOKEN, CONF_OWNER: OWNER, CONF_REPO: REPO},
    )
    entry.add_to_hass(hass)
    with patch("homeassistant.core_config.__version__", ha_version):
        assert hass.config.as_dict()["version"] == ha_version
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED


async def test_entry_is_not_ready_below_the_minimum_version(
    hass: HomeAssistant, isolated_config_dir: Path
) -> None:
    """Eine echt zu alte Fassung führt zu einer verständlichen Verzögerung."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_TOKEN: VALID_TOKEN, CONF_OWNER: OWNER, CONF_REPO: REPO},
    )
    entry.add_to_hass(hass)
    with patch("homeassistant.core_config.__version__", "2025.12.4"):
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.SETUP_RETRY


async def test_unreadable_home_assistant_version_does_not_block_setup(
    hass: HomeAssistant, isolated_config_dir: Path, caplog
) -> None:
    """Eine unlesbare Versionszeichenkette überspringt die Schranke."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_TOKEN: VALID_TOKEN, CONF_OWNER: OWNER, CONF_REPO: REPO},
    )
    entry.add_to_hass(hass)
    with patch("homeassistant.core_config.__version__", "völlig-unlesbar"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert "konnte nicht gelesen werden" in caplog.text
