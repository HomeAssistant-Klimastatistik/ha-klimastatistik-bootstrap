#!/usr/bin/env python3
"""Kompatibilitätsübersicht der CI aus den abgelegten Artefakten erzeugen.

Zweck: Der Zweig `dev` darf fehlschlagen, ohne ein Release zu blockieren. Ein
Fehlschlag darf aber nicht im grünen Gesamtergebnis verschwinden. Diese
Übersicht macht für jeden Zweig sichtbar, welche Home-Assistant- und
Python-Version tatsächlich lief und wie der Lauf ausging.

Aufruf:
    python3 tools/ci_compat_summary.py <verzeichnis-mit-artefakten>
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ElementTree
from pathlib import Path


def _versions(path: Path) -> dict[str, str]:
    """Den JSON-Teil aus der Ausgabe von `check_ha_version.py` lesen."""
    text = path.read_text(encoding="utf-8")
    end = text.rfind("}")
    if end == -1:
        return {}
    try:
        return json.loads(text[: end + 1])
    except json.JSONDecodeError:
        return {}


def _report_for(versions_file: Path, suffix: str) -> Path | None:
    """Den JUnit-Report zu einer Versionsdatei finden.

    Unterstützt beide Benennungen: `test-report-<zweig>.xml` aus der CI und
    `testreport-<repo>-<zweig>.xml` aus dem Auslieferungspaket.
    """
    directory = versions_file.parent
    for candidate in (
        directory / f"test-report-{suffix}.xml",
        directory / f"testreport-{suffix}.xml",
    ):
        if candidate.is_file():
            return candidate
    matches = sorted(directory.glob(f"*report*{suffix}.xml"))
    return matches[0] if matches else None


def _outcome(report: Path | None) -> str:
    """Ergebnis aus einem JUnit-Report ableiten."""
    if report is None or not report.is_file():
        return "kein Report (Lauf abgebrochen)"
    try:
        root = ElementTree.parse(report).getroot()
    except ElementTree.ParseError:
        return "Report unlesbar"
    suites = [root] if root.tag == "testsuite" else list(root)
    failures = sum(int(node.get("failures", 0)) for node in suites)
    errors = sum(int(node.get("errors", 0)) for node in suites)
    total = sum(int(node.get("tests", 0)) for node in suites)
    if failures or errors:
        return f"fehlgeschlagen ({failures} Fehlschläge, {errors} Fehler von {total})"
    return f"bestanden ({total} Tests)"


def main() -> int:
    """Kommandozeile."""
    if len(sys.argv) != 2:
        print("Aufruf: ci_compat_summary.py <verzeichnis>", file=sys.stderr)
        return 2

    base = Path(sys.argv[1])
    lines = [
        "## Home-Assistant-Kompatibilität",
        "",
        "| Zweig | Python | Home Assistant | Frontend | Ergebnis |",
        "| --- | --- | --- | --- | --- |",
    ]

    found = 0
    for versions_file in sorted(base.rglob("ha-version-*.json")):
        data = _versions(versions_file)
        if not data:
            continue
        found += 1
        branch = data.get("branch", "?")
        # Der Dateiname der Versionsdatei trägt den Zweig und - im
        # Auslieferungspaket - zusätzlich das Repository, etwa
        # "ha-version-bootstrap-stable.json". Der zugehörige JUnit-Report
        # heisst entsprechend "test-report-<zweig>.xml" (CI) oder
        # "testreport-<repo>-<zweig>.xml" (Auslieferung).
        suffix = versions_file.stem.removeprefix("ha-version-")
        label = suffix if suffix != branch else branch
        lines.append(
            f"| {label} | {data.get('python', '?')} | {data.get('homeassistant', '?')} "
            f"| {data.get('home_assistant_frontend', '?')} | {_outcome(_report_for(versions_file, suffix))} |"
        )

    if not found:
        lines.append("| - | - | - | - | keine Artefakte gefunden |")

    lines += [
        "",
        "Der Zweig `dev` darf fehlschlagen, ohne ein Release zu blockieren.",
        "Ein Fehlschlag ist ausdrücklich als Upstream- oder Eigenproblem zu",
        "klassifizieren und zu dokumentieren; er wird weder abgeschwächt noch",
        "still übersprungen.",
    ]
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
