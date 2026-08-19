# GitHub-Token für Klimastatistik

Diese Anleitung beschreibt, wie ein möglichst restriktiver GitHub-Token für den
Zugriff auf das private Distributionsrepository von HA Klimastatistik erstellt
wird. Das private Entwicklungsrepository wird Endnutzern nicht freigegeben.

Sie enthält bewusst keine vertraulichen Projektinhalte.

---

## Grundsatz

Es wird ausschliesslich **Leseberechtigung** benötigt. Ein Token mit
Schreibrechten soll nicht erstellt und nicht verwendet werden.

---

## Voraussetzung: Freischaltung durch den Projektinhaber

Für den vorgesehenen Fine-grained-Token-Weg muss der Nutzer Mitglied der
GitHub-Organisation `HomeAssistant-Klimastatistik` sein und Leseberechtigung
für das Repository `ha-klimastatistik-distribution` erhalten haben.

Die Organisationsmitgliedschaft gewährt keinen Zugriff auf das private
Entwicklungsrepository `ha-klimastatistik`. Der Produktzugriff wird gezielt
auf das Distributionsrepository beschränkt.

Outside Collaborators werden für diesen Fine-grained-PAT-Weg von GitHub
derzeit nicht unterstützt.

## Empfohlen: Fine-grained personal access token

**GitHub → Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Generate new token**

| Feld | Wert |
| --- | --- |
| Token name | z. B. `klimastatistik-readonly` |
| Expiration | nach Sicherheitsvorgabe des Projektinhabers bzw. der Organisation; eine Organisationspolicy kann eine maximale Laufzeit erzwingen |
| Resource owner | `HomeAssistant-Klimastatistik` |
| Repository access | **Only select repositories** → `ha-klimastatistik-distribution` |
| Repository permissions → **Contents** | **Read-only** |

`Metadata: Read-only` wird von GitHub automatisch mitgesetzt und ist
erforderlich. Weitere Berechtigungen werden nicht benötigt.

### Freigabe durch die Organisation

Die Organisation kann verlangen, dass ein Organisationsinhaber einen
Fine-grained Token freigibt, bevor er auf private Organisationsressourcen
zugreifen darf. Bei aktivierter Genehmigungspflicht bleibt ein neuer Token
bis zur Freigabe auf öffentliche Ressourcen beschränkt.

Tokens, die ein Organisationsinhaber selbst für seine Organisation erstellt,
werden von GitHub automatisch genehmigt.

### Laufzeit

Organisationen und Unternehmen können eine maximale Tokenlaufzeit erzwingen
(für organisationseigene Ressourcen üblicherweise bis zu 366 Tage). Läuft der
Token ab, meldet Home Assistant dies und bietet über den Reauth-Dialog die
Eingabe eines neuen Tokens an; die Installation bleibt dabei unverändert
bestehen.

---

## Nicht empfohlen: klassischer Token

Ein klassischer *personal access token* benötigt für private Repositories den
Scope `repo`. Dieser Scope umfasst **Schreibzugriff auf alle** Repositories, auf
die der Benutzer Zugriff hat. Für dieses Projekt ist das unverhältnismässig.

Klassische Token funktionieren technisch, sind für diesen Zweck aber
ausdrücklich nicht vorgesehen.

---

## Was mit dem Token geschieht

* Er wird ausschliesslich im `Authorization`-Header an `api.github.com`
  gesendet.
* Er wird im Config Entry von Home Assistant gespeichert, wie jede andere
  Zugangsinformation einer Integration auch.
* Er erscheint **niemals** in Protokollen, Diagnosedaten, Fehlermeldungen oder
  Releaseartefakten.
* Beim Herunterladen eines Release-Assets folgt die Integration der
  Weiterleitung auf den Speicherdienst selbst und sendet den Token dorthin
  ausdrücklich **nicht**.
* Nach der Übergabe an die private Integration entfernt das Bootstrap seine
  eigene Tokenkopie, damit nicht zwei dauerhafte Kopien bestehen bleiben.

---

## Token widerrufen

**GitHub → Settings → Developer settings → Personal access tokens →
Fine-grained tokens → Token auswählen → Delete**

Danach meldet Home Assistant beim nächsten Abruf einen Authentisierungsfehler
und bietet die Eingabe eines neuen Tokens an. Die installierte Klimastatistik
läuft in der Zwischenzeit unverändert weiter; lediglich die Updateprüfung
pausiert.

> GitHub widerruft Token automatisch, die ein Jahr lang nicht verwendet wurden,
> sowie Token, die versehentlich in ein öffentliches Repository gelangen.

---

## Häufige Fehlerbilder

| Beobachtung | Wahrscheinliche Ursache |
| --- | --- |
| „Der Token wurde abgelehnt“ (HTTP 401) | Tippfehler, abgelaufen oder widerrufen |
| „Keine Leseberechtigung“ (HTTP 403/404) | Token nicht für dieses Repository freigegeben, oder Organisationsfreigabe fehlt |
| Funktioniert für öffentliche, nicht für private Repositories | Repository access steht auf *Public repositories* |
| Funktioniert kurz, dann nicht mehr | Ablaufdatum erreicht |
