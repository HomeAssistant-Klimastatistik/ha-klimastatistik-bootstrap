#!/usr/bin/env python3
"""Tatsächlich installierte Home-Assistant-Version ausgeben und prüfen.

Zweck: Eine Kompatibilitätsmatrix, die überall dieselbe Home-Assistant-Version
installiert, ist irreführend. Dieses Werkzeug macht die wirklich installierte
Version sichtbar und bricht ab, wenn sie nicht der übergebenen Erwartung
entspricht. Die Erwartung steht im Workflow, nicht hier: das Werkzeug kennt
keine Zuordnung Zweig -> Version.

Aufruf:

    python3 tools/check_ha_version.py                        # nur ausgeben
    python3 tools/check_ha_version.py --expect 2026.2.0      # exakt erwarten
    python3 tools/check_ha_version.py --at-least 2026.8.0    # Mindestversion
    python3 tools/check_ha_version.py --newer-than 2026.8.2  # echt neuer

Verwendet wird:

    --expect      für die gepinnten Zweige `minimum` und `stable`
    --newer-than  für den Zweig `dev`, damit er nicht unbemerkt auf derselben
                  Version landet wie `stable`

Die Ausgabe ist bewusst maschinen- und menschenlesbar, damit sie im
CI-Protokoll und in den Testartefakten nachvollziehbar bleibt.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "custom_components"))


def _installed() -> tuple[str, str]:
    """Installierte Home-Assistant- und Frontend-Version ermitteln."""
    from homeassistant.const import __version__ as ha_version  # noqa: PLC0415

    try:
        from importlib.metadata import version  # noqa: PLC0415

        frontend_version = version("home-assistant-frontend")
    except Exception:  # pragma: no cover - Frontend ist optional
        frontend_version = "unbekannt"
    return str(ha_version), str(frontend_version)


def _parts(version: str) -> tuple[int, ...]:
    """Numerische Bestandteile einer Version, Vorabkennungen ignoriert."""
    numbers: list[int] = []
    for chunk in version.replace("-", ".").split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        if not digits:
            break
        numbers.append(int(digits))
    return tuple(numbers)


def _compare(installed: str, other: str) -> int:
    """Numerischer Versionsvergleich; -1, 0 oder 1."""
    left = _parts(installed)
    right = _parts(other)
    length = max(len(left), len(right))
    left += (0,) * (length - len(left))
    right += (0,) * (length - len(right))
    return (left > right) - (left < right)


def _at_least(installed: str, minimum: str) -> bool:
    return _compare(installed, minimum) >= 0


def _newer_than(installed: str, other: str) -> bool:
    return _compare(installed, other) > 0


def main() -> int:
    """Kommandozeile."""
    parser = argparse.ArgumentParser(description="Home-Assistant-Version prüfen")
    parser.add_argument("--expect", help="exakt erwartete Home-Assistant-Version")
    parser.add_argument("--at-least", dest="at_least", help="Mindestversion")
    parser.add_argument(
        "--newer-than",
        dest="newer_than",
        help=(
            "die installierte Version muss echt neuer sein. Für den "
            "Entwicklungszweig gedacht: so kann er nicht unbemerkt auf "
            "derselben Version landen wie der Stable-Zweig."
        ),
    )
    parser.add_argument("--branch", default="", help="Name des Kompatibilitätszweigs")
    args = parser.parse_args()

    ha_version, frontend_version = _installed()
    minimum = None
    try:
        from klimastatistik_bootstrap.const import MIN_HOME_ASSISTANT  # noqa: PLC0415

        minimum = MIN_HOME_ASSISTANT
    except Exception:  # pragma: no cover - defensiv
        minimum = None

    report = {
        "branch": args.branch or "unbenannt",
        "python": platform.python_version(),
        "homeassistant": ha_version,
        "home_assistant_frontend": frontend_version,
        "product_min_home_assistant": minimum,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    problems: list[str] = []
    if args.expect and ha_version != args.expect:
        problems.append(f"Erwartet war Home Assistant {args.expect}, installiert ist {ha_version}.")
    if args.at_least and not _at_least(ha_version, args.at_least):
        problems.append(
            f"Erwartet war mindestens Home Assistant {args.at_least}, installiert ist {ha_version}."
        )
    if args.newer_than and not _newer_than(ha_version, args.newer_than):
        problems.append(
            f"Erwartet war eine Home-Assistant-Version echt neuer als "
            f"{args.newer_than}, installiert ist {ha_version}. Dieser Zweig "
            "prüft damit nichts, was ein anderer Zweig nicht schon prüft."
        )

    if problems:
        for problem in problems:
            print(f"::error::{problem}")
            print(f"FEHLER: {problem}", file=sys.stderr)
        return 1

    print(
        f"OK: Zweig {report['branch']} läuft gegen Home Assistant {ha_version} "
        f"unter Python {report['python']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
