# HA Klimastatistik Bootstrap

Öffentlicher Zugangspunkt für die private Home-Assistant-Integration
**Klimastatistik**.

Dieses Repository enthält ausschliesslich den technisch notwendigen
Erstinstallationsweg. Es enthält **keine** Klimaberechnung, **keine** privaten
Release-Assets und **keine** eingebetteten Zugangsdaten.

> **Wichtig:** Das Installieren dieses Bootstraps gewährt keinen Zugriff auf das
> private Produkt. Für die Installation der eigentlichen Integration ist eine
> individuell erteilte Leseberechtigung auf dem privaten Distributionsrepository und ein
> gültiger GitHub-Token erforderlich. Ohne beides wird nichts heruntergeladen
> und nichts installiert.


## Zugang zu HA Klimastatistik anfordern

HA Klimastatistik wird derzeit privat verteilt.

Der aktuelle Distributionsweg ist für das **Update einer bereits bestehenden
HA-Klimastatistik-Installation aus der Reihe v2.2.x** vorgesehen.

Eine Neuinstallation wird derzeit bewusst nicht angeboten. Sie wird wieder
freigegeben, sobald der vollständige Installationsweg ohne zusätzlichen
manuellen Aufwand möglich ist.

### Zugang anfordern

Für das Update wird zunächst Zugang zur privaten GitHub-Distribution benötigt.

1. Öffne im Bereich **Issues** dieses Repositories ein neues Issue.
2. Wähle **„Zugang zu HA Klimastatistik anfordern“**.
3. Fülle das kurze Formular aus und sende die Anfrage ab.
4. Nach Prüfung erhältst du eine Einladung zur GitHub-Organisation
   `HomeAssistant-Klimastatistik`.
5. Nimm diese Organisationseinladung an.
6. Prüfe anschließend, dass du Zugriff auf das private Repository
   `ha-klimastatistik-distribution` hast.
7. Erst danach erstellst du den für das Update benötigten
   Fine-grained Personal Access Token.

Die Zugangsanfrage ist als GitHub-Issue öffentlich sichtbar.

**Veröffentliche dort niemals Tokens, Passwörter, E-Mail-Adressen oder andere
vertrauliche Informationen.**

---

## Was das Bootstrap tut

1. nimmt einen GitHub-Token entgegen,
2. prüft, ob dieser Token das private Distributionsrepository lesen darf,
3. ermittelt das neueste Release des gewählten Kanals,
4. lädt das Release-Manifest und das Produktpaket,
5. prüft SHA-256, Manifest und Paketstruktur,
6. legt ausschliesslich `custom_components/klimastatistik/` an,
7. fordert den erforderlichen Neustart an.

Alles Weitere — Adoption bestehender Installationen, verwaltete Dateien,
Updates, Backup und Rollback — übernimmt danach die private Integration selbst.

## Was das Bootstrap ausdrücklich nicht tut

* keine Änderungen an `configuration.yaml`,
* keine Änderungen an Templates, Dashboards, Helpern oder SQL-Konfiguration,
* keine Zugriffe auf `.storage`,
* keine Zugriffe auf die Recorder-Datenbank,
* keine Speicherung eines Tokens im Repository oder in Protokollen.

---

## Installation

### 1. Als HACS Custom Repository hinzufügen

HACS öffnen → Menü oben rechts (drei Punkte) → **Custom repositories** →

* **Repository:** `https://github.com/HomeAssistant-Klimastatistik/ha-klimastatistik-bootstrap`
* **Type / Category:** `Integration`

→ **ADD**.

Anschliessend `HA Klimastatistik Bootstrap` in HACS herunterladen.

> Dieses Projekt wird bewusst **nicht** im offiziellen HACS-Katalog eingereicht.
> Der Weg über Custom Repositories ist der vorgesehene und einzige Weg.

### 2. Home Assistant neu starten

### 3. GitHub-Token anlegen

Siehe [docs/TOKEN.md](docs/TOKEN.md). Kurzfassung:

* der Nutzer muss zuvor vom Projektinhaber als Mitglied der
  GitHub-Organisation freigeschaltet worden sein,
* **Fine-grained personal access token**,
* **Resource owner:** `HomeAssistant-Klimastatistik`,
* **Repository access:** *Only select repositories* →
  `ha-klimastatistik-distribution`,
* **Repository permissions:** **Contents: Read-only** (mehr wird nicht
  benötigt und soll nicht vergeben werden),
* Schreibrechte sind ausdrücklich **nicht** erforderlich.
### 4. Bootstrap einrichten

**Einstellungen → Geräte & Dienste → Integration hinzufügen →
`HA Klimastatistik Bootstrap`**

Token eintragen und bestätigen. Das Bootstrap prüft den Zugriff und
installiert die private Integration.

### 5. Neustart

Der erforderliche Neustart wird als Reparaturhinweis angezeigt und kann von
dort direkt ausgelöst werden.

### 6. Klimastatistik einrichten

**Einstellungen → Geräte & Dienste → Integration hinzufügen → `Klimastatistik`**

Der bereits eingegebene Token wird dabei automatisch übernommen. Danach
entfernt das Bootstrap seine eigene Tokenkopie; der Token muss also nur einmal
eingegeben werden.

---

## Updatekanäle

| Kanal | Inhalt | Für wen |
| --- | --- | --- |
| `stable` | ausschliesslich freigegebene Releases | alle berechtigten Nutzer |
| `beta` | zusätzlich Vorabversionen (Prereleases) | ausdrücklich autorisierte Tester |

Stable-Nutzer erhalten niemals ein Prerelease.

Draft-Releases werden bewusst nicht verwendet: sie sind über die GitHub-API nur
mit Schreibberechtigung sichtbar, was bei Testern einen schreibfähigen Token
erzwingen würde.

---

## Fehlermeldungen

| Meldung | Bedeutung | Abhilfe |
| --- | --- | --- |
| Der Token wurde abgelehnt | Token ungültig, abgelaufen oder widerrufen | neuen Token erzeugen |
| Keine Leseberechtigung für dieses private Repository | Token gültig, aber ohne Zugriff | Berechtigung beim Projektinhaber anfragen; bei Organisationen kann eine Freigabe des Tokens durch einen Owner nötig sein |
| GitHub ist nicht erreichbar | Netzwerkproblem, kein Berechtigungsproblem | Netzwerk und DNS prüfen |
| Das GitHub-Anfragekontingent ist erschöpft | Rate Limit | später erneut versuchen |
| Kein installierbares Release gefunden | im gewählten Kanal liegt kein passendes Release | Kanal prüfen |
| Prüfsumme stimmt nicht | Download beschädigt oder Paket verändert | erneut versuchen; bei Wiederholung Projektinhaber informieren |

Diese Ursachen werden bewusst getrennt gemeldet, damit ein Netzwerkfehler
nicht als Berechtigungsproblem missverstanden wird.

---

## Sicherheitsmodell

* Dieses Repository ist öffentlich und als vollständig einsehbar zu behandeln.
  Es gibt keine Sicherheit durch Verschleierung.
* Der Token wird ausschliesslich im `Authorization`-Header verwendet.
* Der Token erscheint niemals in Protokollen, Diagnosedaten, Fehlermeldungen
  oder Releaseartefakten. Die CI prüft das statisch bei jedem Commit.
* Beim Herunterladen von Release-Assets folgt das Bootstrap der Weiterleitung
  auf den Speicherdienst bewusst selbst und **ohne** `Authorization`-Header.
* Bootstrap installiert ≠ Zugriff auf Klimastatistik.

## Datenschutz

Das Bootstrap sendet ausschliesslich Anfragen an `api.github.com` und an die
von GitHub zurückgegebene Speicheradresse des Release-Assets. Es werden keine
Nutzungsdaten erhoben oder übertragen.

---

## Entwicklung

Die Home-Assistant-Version steht bewusst **nicht** in
`requirements-test.txt`, sondern in einer Zweigdatei — sonst würde der
Auflöser immer dieselbe Fassung wählen und die Kompatibilitätsmatrix wäre
eine Behauptung statt einer Prüfung.

```bash
# Mindestversion: Home Assistant 2026.2.0 (exakt) unter Python 3.13
pip install -r requirements-test.txt -r requirements-ha-minimum.txt

# oder: gepinnter Stable-Stand: Home Assistant 2026.8.2 unter Python 3.14
# pip install -r requirements-test.txt -r requirements-ha-stable.txt

python tools/check_ha_version.py          # installierte HA-Version ausweisen
pytest -q
ruff check custom_components tests tools
ruff format --check custom_components tests tools
```

Die CI prüft in drei Zweigen, die tatsächlich unterschiedliche
Home-Assistant-Versionen installieren:

| Zweig | Python | Home Assistant | Pflicht |
| --- | --- | --- | --- |
| `minimum` | 3.13 | 2026.2.0 (exakt) | ja |
| `stable` | 3.14 | 2026.8.2 (gepinnt) | ja |
| `dev` | 3.14 | `dev`-Zweig aus `home-assistant/core` | nein |

Zusätzlich prüft sie hassfest, die HACS-Struktur und statisch, dass in
diesem öffentlichen Repository weder ein Geheimnis noch Produktlogik liegt.

## Lizenz

Siehe [LICENSE](LICENSE). Das private Hauptprodukt bleibt privat geteilt.
