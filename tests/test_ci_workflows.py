"""Maschinelle Prüfung der Workflowdateien des Bootstraps.

Ein echter Lauf auf GitHubs Runnern lässt sich hier nicht erzeugen. Was sich
prüfen lässt, ist die Struktur: gültiges YAML, zwei tatsächlich
unterschiedliche Home-Assistant-Stände in der Pflichtmatrix, ein optionaler
Entwicklungszweig und ein Secret-Scan, dessen Exitcode ausgewertet wird
statt in einer `if`-Bedingung zu verschwinden.

Bewusst ohne jede Kenntnis des privaten Hauptrepositories: dieser Test muss
auch bei einem Solo-Checkout laufen.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"

sys.path.insert(0, str(REPO_ROOT / "custom_components"))

from klimastatistik_bootstrap.const import MIN_HOME_ASSISTANT  # noqa: E402

WORKFLOW_FILES = sorted(WORKFLOW_DIR.glob("*.yml"))


def _load(name: str) -> dict[str, Any]:
    return yaml.safe_load((WORKFLOW_DIR / name).read_text(encoding="utf-8"))


def _run_steps(document: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for job in document.get("jobs", {}).values():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and "run" in step:
                steps.append(step)
    return steps


def test_the_expected_workflow_files_exist() -> None:
    """Die Matrix liegt auch hier in einem wiederverwendbaren Workflow."""
    assert [path.name for path in WORKFLOW_FILES] == ["compat-matrix.yml", "validate.yml"]


@pytest.mark.parametrize("path", WORKFLOW_FILES, ids=lambda path: path.name)
def test_every_workflow_file_is_valid_yaml(path: Path) -> None:
    """Ein Workflow mit ungültigem YAML startet auf GitHub gar nicht."""
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    assert document.get("jobs"), path.name
    # PyYAML liest das Schlüsselwort `on` nach YAML 1.1 als Wahrheitswert.
    assert True in document or "on" in document, path.name


def test_no_workflow_requests_write_permission() -> None:
    """Das öffentliche Repository veröffentlicht nichts."""
    for path in WORKFLOW_FILES:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert document.get("permissions") == {"contents": "read"}, path.name
        for name, job in document["jobs"].items():
            assert "write" not in str(job.get("permissions", "")), (path.name, name)


def test_the_mandatory_matrix_pins_two_different_home_assistant_versions() -> None:
    """Die Pflichtzweige installieren nachweislich unterschiedliche Stände."""
    entries = _load("compat-matrix.yml")["jobs"]["pflicht"]["strategy"]["matrix"]["include"]
    by_branch = {entry["branch"]: entry for entry in entries}
    assert set(by_branch) == {"minimum", "stable"}

    minimum = by_branch["minimum"]
    assert minimum["check"] == f"--expect {MIN_HOME_ASSISTANT}"
    assert minimum["ha_label"] == MIN_HOME_ASSISTANT

    stable = by_branch["stable"]
    assert stable["check"] == f"--expect {stable['ha_label']}"
    assert stable["ha_label"] != minimum["ha_label"]
    assert stable["python"] != minimum["python"]


def test_the_development_branch_is_optional_but_visible() -> None:
    """`continue-on-error` genau dort, wo es hingehört."""
    jobs = _load("compat-matrix.yml")["jobs"]
    assert jobs["optional"]["continue-on-error"] is True
    assert jobs["pflicht"].get("continue-on-error") is None
    dev_steps = " ".join(step["run"] for step in jobs["optional"]["steps"] if "run" in step)
    assert "--newer-than" in dev_steps
    assert "always()" in jobs["zusammenfassung"]["if"]


def test_the_version_check_is_never_piped() -> None:
    """Eine Pipe würde den Exitcode verschlucken (`bash -e` ohne `pipefail`)."""
    for name in ("compat-matrix.yml", "validate.yml"):
        for step in _run_steps(_load(name)):
            for line in step["run"].splitlines():
                code = line.split("#", 1)[0]
                if "check_ha_version.py" in code:
                    assert "|" not in code, (name, line)


def test_the_history_scan_evaluates_the_exit_code() -> None:
    """Ein defekter Secret-Scan muss rot werden, nicht grün."""
    steps = [
        step
        for step in _run_steps(_load("validate.yml"))
        if "git log" in step["run"] and "grep" in step["run"]
    ]
    assert len(steps) == 1
    script = steps[0]["run"]
    assert "if git log" not in script
    assert "STATUS=$?" in script
    assert "grep-Exitcode" in script
    for line in script.splitlines():
        code = line.split("#", 1)[0]
        if "git log" in code:
            assert "|" not in code, line


def test_the_history_scan_never_prints_the_found_value() -> None:
    """Ein Treffer darf nicht im öffentlich lesbaren Protokoll landen."""
    script = next(
        step["run"]
        for step in _run_steps(_load("validate.yml"))
        if "git log" in step["run"] and "grep" in step["run"]
    )
    assert "hits.txt" in script
    assert "cut -d: -f1" in script
    assert "nicht ausgegeben" in script
    for line in script.splitlines():
        code = line.split("#", 1)[0]
        if "grep -nP" in code:
            assert "hits.txt" in code or ">" in code or "\\" in code, line


def test_the_hacs_check_does_not_claim_catalogue_membership() -> None:
    """Das Projekt wird bewusst nicht im offiziellen HACS-Katalog eingereicht."""
    hacs = _load("validate.yml")["jobs"]["hacs"]["steps"]
    action = [step for step in hacs if str(step.get("uses", "")).startswith("hacs/action")]
    assert len(action) == 1
    assert action[0]["with"]["category"] == "integration"
    assert set(action[0]["with"]["ignore"].split()) == {
        "topics",
        "license",
    }
