"""Sicherheitsprüfungen des öffentlichen Repositories.

Dieses Repository ist öffentlich einsehbar. Die folgenden Prüfungen laufen in
der CI und stellen sicher, dass hier niemals ein Geheimnis, ein Produktinhalt
oder ein universeller Zugang landet (Auftrag Abschnitte 4, 19 und 32.5).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SECRET_PATTERNS = (
    re.compile(r"github_pat_(?!TESTONLY)[A-Za-z0-9_]{20,}"),
    re.compile(r"gh[pousr]_(?!TESTONLY)[A-Za-z0-9]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)aws_secret_access_key\s*[:=]"),
    re.compile(r"(?i)client_secret\s*[:=]\s*['\"][^'\"]{8,}"),
)

#: Begriffe, die auf mitgelieferte Produktlogik hindeuten.
PRODUCT_MARKERS = (
    "Tropennacht",
    "Kysely",
    "Vegetationsperiode",
    "statistics_meta",
    "sql.query",
    "klima_quellsensor",
    "input_select.klima_vergleichsjahr",
)

TEXT_SUFFIXES = {".py", ".json", ".yaml", ".yml", ".md", ".txt", ".cfg", ".ini", ".toml"}


def _files() -> list[Path]:
    return [
        path
        for path in REPO_ROOT.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and ".git" not in path.parts
        and path.suffix in TEXT_SUFFIXES
    ]


def test_no_secrets_in_repository() -> None:
    """Im öffentlichen Repository liegt kein Geheimnis."""
    files = _files()
    assert files
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in SECRET_PATTERNS:
            assert not pattern.search(text), f"Verdächtiger Inhalt in {path}"


def test_no_product_logic_in_repository() -> None:
    """Im öffentlichen Repository liegt keine Klimaberechnung."""
    for path in (REPO_ROOT / "custom_components").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for marker in PRODUCT_MARKERS:
            assert marker not in text, f"{path} enthält Produktlogik: {marker}"


def test_no_managed_payload_in_repository() -> None:
    """Es werden keine privaten Nutzdaten mitgeliefert."""
    for name in (
        "klimamodul.yaml",
        "klimavergleich.yaml",
        "klimatagesvergleich.yaml",
        "klimasicherheit.yaml",
        "klimastatistik_dashboard_portabel.yaml",
    ):
        assert not list(REPO_ROOT.rglob(name)), name
    assert not list(REPO_ROOT.rglob("*.zip"))


def test_no_hardcoded_credentials_in_constants() -> None:
    """Keine Konstante trägt einen Zugangsdatenwert."""
    for path in (REPO_ROOT / "custom_components").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for pattern in SECRET_PATTERNS:
                    assert not pattern.search(node.value), f"{path}:{node.lineno}"


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Docstring-Konstanten sammeln; sie dürfen Begriffe erklären."""
    result: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                result.add(id(body[0].value))
    return result


def _code_strings(path: Path) -> list[tuple[int, str]]:
    """Alle Zeichenkettenkonstanten ausserhalb von Docstrings."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_nodes(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_no_storage_or_database_access() -> None:
    """Das Bootstrap fasst weder `.storage` noch die Recorder-Datenbank an."""
    for path in (REPO_ROOT / "custom_components").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        assert "sqlite3" not in path.read_text(encoding="utf-8"), path
        for lineno, value in _code_strings(path):
            assert ".storage" not in value, f"{path}:{lineno}"
            assert "home-assistant_v2.db" not in value, f"{path}:{lineno}"


def test_bootstrap_writes_only_its_own_paths() -> None:
    """Das Bootstrap schreibt ausschliesslich in sein Staging und die Integration."""
    installer = REPO_ROOT / "custom_components/klimastatistik_bootstrap/core/installer.py"
    source = installer.read_text(encoding="utf-8")
    assert 'INTEGRATION_PREFIX: Final = f"custom_components/{INTEGRATION_DOMAIN}/"' in source
    for _lineno, value in _code_strings(installer):
        for forbidden in ("configuration.yaml", "secrets.yaml", "templates/", "recorder"):
            assert forbidden not in value, f"{forbidden} in {value!r}"


def test_hacs_manifest_is_minimal_and_valid() -> None:
    """hacs.json enthält nur dokumentierte Schlüssel."""
    import json

    data = json.loads((REPO_ROOT / "hacs.json").read_text(encoding="utf-8"))
    allowed = {
        "name",
        "content_in_root",
        "zip_release",
        "filename",
        "hide_default_branch",
        "country",
        "homeassistant",
        "hacs",
        "persistent_directory",
        "render_readme",
    }
    assert set(data) <= allowed, set(data) - allowed
    assert data["name"]
    assert "homeassistant" in data


def test_integration_manifest_is_complete() -> None:
    """Das Integrationsmanifest erfüllt die Pflichtfelder für Custom Integrations."""
    import json

    data = json.loads(
        (REPO_ROOT / "custom_components/klimastatistik_bootstrap/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for key in (
        "domain",
        "name",
        "version",
        "documentation",
        "issue_tracker",
        "codeowners",
        "iot_class",
    ):
        assert data.get(key), key
    assert data["domain"] == "klimastatistik_bootstrap"
    assert data["config_flow"] is True
    assert not data["documentation"].startswith("https://www.home-assistant.io/integrations")
