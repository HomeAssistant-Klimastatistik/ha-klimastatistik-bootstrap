"""Übersetzungen des Bootstraps: Struktur und echte Zweisprachigkeit.

`translations/en.json` war byteidentisch zu `translations/de.json`; die
"englische" Übersetzung war die deutsche. Kein Test hat das bemerkt.
"""

from __future__ import annotations

import json
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "custom_components/klimastatistik_bootstrap"

#: Wörter, die es in einer englischen Fassung nicht geben darf.
GERMAN_MARKERS = (
    "erforderlich",
    "wurde",
    "nicht",
    "Berechtigung",
    "Neustart",
    "Bitte",
    "Token wird niemals",
)

#: Eigennamen, die in beiden Sprachen gleich lauten dürfen.
SHARED_VALUES = frozenset({"Klimastatistik", "Stable", "Repository"})


def _flatten(node, prefix: str = "") -> dict[str, str]:
    result: dict[str, str] = {}
    if isinstance(node, dict):
        for key, value in node.items():
            result.update(_flatten(value, f"{prefix}{key}."))
    elif isinstance(node, str):
        result[prefix.rstrip(".")] = node
    return result


def _load(name: str) -> dict[str, str]:
    return _flatten(json.loads((PACKAGE / name).read_text(encoding="utf-8")))


def test_translation_keys_match_strings() -> None:
    """`de.json` und `en.json` haben genau die Schlüssel von `strings.json`."""
    reference = _load("strings.json")
    for language in ("de", "en"):
        translated = _load(f"translations/{language}.json")
        assert set(translated) == set(reference), language
        assert all(value.strip() for value in translated.values()), language


def test_german_translation_is_the_reference() -> None:
    """`de.json` stimmt mit `strings.json` überein."""
    assert (PACKAGE / "translations/de.json").read_bytes() == (
        PACKAGE / "strings.json"
    ).read_bytes()


def test_english_translation_is_really_english() -> None:
    """`en.json` ist keine Kopie der deutschen Fassung."""
    assert (PACKAGE / "translations/en.json").read_bytes() != (
        PACKAGE / "translations/de.json"
    ).read_bytes()
    german = _load("translations/de.json")
    english = _load("translations/en.json")
    identical = [
        key for key, value in english.items() if value == german[key] and value not in SHARED_VALUES
    ]
    assert not identical, identical
    with_markers = [
        key
        for key, value in english.items()
        if any(marker.lower() in value.lower() for marker in GERMAN_MARKERS)
    ]
    assert not with_markers, with_markers
