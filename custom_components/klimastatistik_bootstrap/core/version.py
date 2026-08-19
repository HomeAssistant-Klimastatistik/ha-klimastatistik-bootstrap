"""Versionsvergleich ohne externe Abhängigkeiten.

Bewusst HA-frei, damit die Logik ohne Home-Assistant-Installation testbar ist
(Auftrag Abschnitt 33).

Unterstützt SemVer-artige Produktversionen (2.3.0, 2.3.1-beta.1) und die
CalVer-artigen Home-Assistant-Versionen (2026.2.0, 2026.8.2).

Ausdrücklich mit abgedeckt sind die **trennzeichenlosen** Vorabkennungen von
Home Assistant. Primärquelle `home-assistant/core`, Tag `2026.8.0b0`,
`homeassistant/const.py`:

    MAJOR_VERSION = 2026
    MINOR_VERSION = 8
    PATCH_VERSION = "0b0"
    __version__   = "2026.8.0b0"

`hass.config.as_dict()["version"]` liefert genau diesen String. Eine frühere
Fassung verlangte vor der Vorabkennung ein Trennzeichen `[-+.]`; `2026.8.0b0`
wurde dadurch als Release `2026.8` mit der unlesbaren Vorabkennung `0b0`
gedeutet und die Integration lud auf jeder HA-Beta und jedem RC überhaupt
nicht mehr.

Ebenfalls korrigiert: `+` trennt nach SemVer **Buildmetadaten**, keine
Vorabkennung. `2.3.0+build.7` ist deshalb dieselbe Version wie `2.3.0` und
ausdrücklich keine Vorabversion. Die Metadaten werden gelesen und beim
Vergleich - wie in der SemVer-Spezifikation vorgesehen - ignoriert.
"""

from __future__ import annotations

import re
from typing import NamedTuple

_VERSION_RE = re.compile(
    r"^\s*v?"
    r"(?P<release>\d+(?:\.\d+)*)"
    r"(?:"
    # SemVer: Bindestrich trennt; die Kennung darf rein numerisch sein.
    r"-(?P<pre_dash>[0-9A-Za-z][0-9A-Za-z.\-]*)"
    r"|"
    # PEP-440-artig: Punkt oder gar kein Trennzeichen. Damit die Kennung
    # keine Releasestelle verschlucken kann, muss sie mit einem Buchstaben
    # beginnen: `2026.8.0b0` -> Release 2026.8.0, Kennung `b0`;
    # `2026.9.0.dev0` -> Release 2026.9.0, Kennung `dev0`.
    r"\.?(?P<pre_bare>[A-Za-z][0-9A-Za-z.\-]*)"
    r")?"
    # Buildmetadaten nach SemVer; für die Ordnung bedeutungslos.
    r"(?:\+(?P<build>[0-9A-Za-z.\-]*))?"
    r"\s*$"
)

# Ordnung der Vorabkennungen. Kleinere Zahl = früher.
_PRE_ORDER = {"dev": 0, "alpha": 1, "a": 1, "beta": 2, "b": 2, "rc": 3, "pre": 3}


class InvalidVersionError(ValueError):
    """Version konnte nicht gelesen werden."""


class Version(NamedTuple):
    """Normalisierte, vergleichbare Version."""

    release: tuple[int, ...]
    pre: tuple[tuple[int, int, str], ...]
    raw: str
    #: SemVer-Buildmetadaten. Werden gelesen, aber nie verglichen.
    build: str = ""

    def __str__(self) -> str:  # pragma: no cover - triviale Darstellung
        """Ursprüngliche Schreibweise der Version."""
        return self.raw

    @property
    def is_prerelease(self) -> bool:
        """True, wenn es sich um eine Vorabversion handelt."""
        return bool(self.pre)

    def _key(self, width: int) -> tuple:
        release = self.release + (0,) * (width - len(self.release))
        # Eine Vorabversion ist kleiner als die zugehörige Endversion.
        return (release, (0,) if self.pre else (1,), self.pre)

    def compare(self, other: Version) -> int:
        """-1 / 0 / 1 wie ein klassischer Dreiwegvergleich."""
        width = max(len(self.release), len(other.release))
        a, b = self._key(width), other._key(width)
        if a < b:
            return -1
        if a > b:
            return 1
        return 0


def parse_version(value: str) -> Version:
    """Version lesen oder InvalidVersionError werfen."""
    if not isinstance(value, str):
        raise InvalidVersionError(f"Version ist keine Zeichenkette: {value!r}")
    match = _VERSION_RE.match(value)
    if not match:
        raise InvalidVersionError(f"Unlesbare Version: {value!r}")
    release = tuple(int(part) for part in match.group("release").split("."))
    pre_raw = match.group("pre_dash") or match.group("pre_bare")
    pre: list[tuple[int, int, str]] = []
    if pre_raw:
        for chunk in re.split(r"[.\-]", pre_raw):
            if not chunk:
                continue
            token = re.match(r"^([A-Za-z]*)(\d*)$", chunk)
            if not token:
                raise InvalidVersionError(f"Unlesbare Vorabkennung: {value!r}")
            word, number = token.group(1).lower(), token.group(2)
            if word:
                if word not in _PRE_ORDER:
                    # Unbekannte Kennungen sortieren hinter den bekannten,
                    # aber weiterhin vor der Endversion.
                    pre.append((90, int(number or 0), word))
                    continue
                pre.append((_PRE_ORDER[word], int(number or 0), word))
            else:
                pre.append((50, int(number or 0), ""))
    return Version(
        release=release,
        pre=tuple(pre),
        raw=value.strip(),
        build=match.group("build") or "",
    )


def compare_versions(left: str, right: str) -> int:
    """Zwei Versionszeichenketten vergleichen."""
    return parse_version(left).compare(parse_version(right))


def is_newer(candidate: str, installed: str) -> bool:
    """Prüfen, ob candidate echt neuer als installed ist."""
    return compare_versions(candidate, installed) > 0


def meets_minimum(actual: str, minimum: str) -> bool:
    """Prüfen, ob actual mindestens minimum ist."""
    return compare_versions(actual, minimum) >= 0


def is_prerelease_version(value: str) -> bool:
    """Prüfen, ob die Versionszeichenkette eine Vorabkennung trägt."""
    return parse_version(value).is_prerelease


def sort_versions(values: list[str], *, newest_first: bool = True) -> list[str]:
    """Versionsliste sortieren; unlesbare Einträge werden verworfen."""
    parsed: list[Version] = []
    for value in values:
        try:
            parsed.append(parse_version(value))
        except InvalidVersionError:
            continue
    import functools

    parsed.sort(key=functools.cmp_to_key(lambda a, b: a.compare(b)), reverse=newest_first)
    return [item.raw for item in parsed]
