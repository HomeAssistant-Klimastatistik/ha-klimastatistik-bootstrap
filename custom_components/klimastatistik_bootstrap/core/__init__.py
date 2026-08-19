"""Home-Assistant-freier Kern des öffentlichen Bootstraps.

Enthält ausschliesslich lesende Releaselogik. Bewusst NICHT enthalten:

* Klimaberechnungslogik,
* private Release-Assets,
* vertrauliche Projektdokumentation,
* irgendein eingebetteter Token oder Schlüssel.

Die Module `errors.py`, `version.py`, `release_manifest.py`, `github.py` und
`client.py` sind identische Kopien aus dem privaten Hauptrepository. Sie
enthalten keinerlei vertrauliche Information; ihre Offenlegung ist bewusst in
Kauf genommen (Auftrag Abschnitt 4: Security through obscurity ist unzulässig).
"""
