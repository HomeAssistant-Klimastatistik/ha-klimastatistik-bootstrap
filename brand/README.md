# Brand-Assets

HACS erwartet für Integrationen ein `brand`-Verzeichnis mit mindestens
`icon.png`.

**Noch beizulegen:** `icon.png` (PNG, quadratisch, mindestens 256×256 px).

Solange die Datei fehlt, schlägt in der CI ausschliesslich die HACS-Prüfung
`brands` fehl. Sie ist im Workflow bewusst über `ignore: brands` abgeschaltet,
weil dieses Projekt nicht im offiziellen HACS-Katalog eingereicht wird.
