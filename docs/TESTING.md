# Redline – Testanleitung (neue Version prüfen)

> **Für wen ist dieses Dokument?**
> Für alle, die eine neue Version von Redline testen – ohne Entwicklerkenntnisse.
> Hier steht **nur**, was du zum Testen brauchst. Die Erst-Installation ist in `INSTALLATION.md` beschrieben.

---

## Inhaltsverzeichnis

1. [Was du brauchst](#1-was-du-brauchst)
2. [App für den Test-Modus starten](#2-app-für-den-test-modus-starten)
3. [Erkennungszeichen: Bist du im Test-Modus?](#3-erkennungszeichen-bist-du-im-test-modus)
4. [Test-Benutzerkonten anlegen](#4-test-benutzerkonten-anlegen)
5. [Test-Checkliste – Admin-Rolle](#5-test-checkliste--admin-rolle)
6. [Test-Checkliste – Disponent-Rolle](#6-test-checkliste--disponent-rolle)
7. [Test-Checkliste – Community-User (Techniker)](#7-test-checkliste--community-user-techniker)
8. [Test-Checkliste – QR-Code-Scan (Gerät melden)](#8-test-checkliste--qr-code-scan-gerät-melden)
9. [Was du NICHT tun musst](#9-was-du-nicht-tun-musst)
10. [Fehler melden – was du notieren sollst](#10-fehler-melden--was-du-notieren-sollst)

---

## 1. Was du brauchst

- Den Computer, auf dem Redline bereits installiert ist
- Einen Browser (Chrome, Firefox oder Safari)
- Evtl. ein Smartphone zum Testen des QR-Code-Scans

Du brauchst **keinen** Internetzugang, kein E-Mail-Konto und keine besonderen Programme.

---

## 2. App für den Test-Modus starten

> **Wichtig:** Für Tests immer mit den folgenden Einstellungen starten – nie mit den Produktions-Einstellungen testen!

### Option A – Schnellstart (Kommandozeile / Terminal)

Öffne das Terminal und führe diesen Befehl im Redline-Ordner aus:

```
FLASK_ENV=development python app.py
```

Das war's. Die App läuft jetzt auf: **http://localhost:5000**

### Option B – Wenn du eine `.env`-Datei verwendest

Stelle sicher, dass deine `.env`-Datei diese Werte enthält:

```
FLASK_ENV=development
SECRET_KEY=test-secret-key-nur-fuer-tests
MAIL_SUPPRESS_SEND=true
```

Dann starte mit:

```
python app.py
```

### Option C – Docker (falls Docker verwendet wird)

```
docker compose up
```

---

### Was bedeuten die Einstellungen?

| Einstellung | Was sie bewirkt |
|---|---|
| `FLASK_ENV=development` | Gelbes Entwicklungs-Banner wird angezeigt – du siehst sofort, dass du testest |
| `MAIL_SUPPRESS_SEND=true` | Keine echten E-Mails werden verschickt – Werkstatt-Meldungen kommen nur im Log an |
| `SECRET_KEY=...` | Eigener Schlüssel für Test – nie den Produktions-Schlüssel beim Testen verwenden |

> Du musst **keine** FileMaker-Konfiguration, keinen E-Mail-Server und keine externen Dienste einrichten. Die App läuft vollständig lokal.

---

## 3. Erkennungszeichen: Bist du im Test-Modus?

Bevor du anfängst zu testen, prüfe folgendes:

- [ ] Oben auf jeder Seite siehst du ein **gelbes Banner** mit dem Text „Entwicklung"
- [ ] Die Adresse im Browser ist `http://localhost:5000`
- [ ] Unten in der Fußzeile steht die Versionsnummer (z.B. `v1.4.0`)

Wenn du **kein** gelbes Banner siehst, stoppe die App und prüfe die Starteinstellungen aus Abschnitt 2.

---

## 4. Test-Benutzerkonten anlegen

Beim allerersten Start werden automatisch Standard-Testdaten angelegt.

### Standard-Admin-Konto (automatisch angelegt)

| Feld | Wert |
|---|---|
| Benutzername | `admin` |
| Passwort | `admin` |

> Melde dich damit an und lege dann weitere Testkonten an (siehe unten).

### Weitere Testkonten anlegen

1. Melde dich als **admin** an
2. Klicke oben auf **Admin** → **Benutzer**
3. Lege folgende Konten an:

| Benutzername | Passwort | Rolle | Einstellung |
|---|---|---|---|
| `disponent1` | `Test1234` | Disponent | Checkbox „Disponent" anhaken |
| `techniker1` | `Test1234` | Community | Beide Checkboxen LEER lassen |

---

## 5. Test-Checkliste – Admin-Rolle

Melde dich mit `admin` / `admin` an.

### 5.1 Geräte verwalten

- [ ] **Gerät anlegen:** Klicke auf „Neues Gerät" → trage eine ID (z.B. `CAM-TEST-01`) und einen Namen ein → „Speichern" klicken → Gerät erscheint in der Liste
- [ ] **QR-Code anzeigen:** Klicke auf das Gerät → QR-Code-Symbol → ein QR-Code wird angezeigt und kann heruntergeladen werden
- [ ] **Gerät bearbeiten:** Name oder Beschreibung ändern → „Speichern" → Änderung erscheint in der Liste

### 5.2 Defekte verwalten

- [ ] **Defekt sehen:** Wenn ein Defekt gemeldet wurde, erscheint er in der Defektliste
- [ ] **Defekt als behoben markieren:** Klicke auf den Defekt → „Als behoben markieren" → Status wechselt auf „Behoben" → Gerätestatus springt auf „Verfügbar"

### 5.3 Benutzer verwalten

- [ ] **Benutzer anlegen:** Benutzername + Passwort eingeben, Rolle wählen → „Anlegen" → Benutzer erscheint in der Liste
- [ ] **Benutzer löschen:** Auf den roten Löschen-Button klicken → Bestätigung → Benutzer verschwindet aus der Liste
- [ ] **Eigenen Account kann man nicht löschen** → Fehlermeldung erscheint (das ist korrekt)

### 5.4 Kategorien verwalten

- [ ] **Neue Kategorie anlegen:** Gib einen Namen ein → „Hinzufügen" → Kategorie erscheint in der Liste und ist danach im Meldeformular verfügbar
- [ ] **Kategorie löschen:** Löschen-Button → Kategorie verschwindet

### 5.5 Was der Admin NICHT soll (prüfen ob geblockt)

- [ ] Öffne `/disponent/` in der Adresszeile → Admin darf das sehen (das ist gewollt)
- [ ] Öffne `http://localhost:5000/auth/login` während du eingeloggt bist → Weiterleitung zum Dashboard (nicht zweimal Login zeigen)

---

## 6. Test-Checkliste – Disponent-Rolle

Melde dich mit `disponent1` / `Test1234` an.

### 6.1 Dashboard

- [ ] Nach dem Login landest du direkt auf dem **Disponent-Dashboard** (nicht auf Admin)
- [ ] Vier farbige Kacheln werden angezeigt: „Gesamt", „In Wartung", „Reserviert", „Verfügbar"
- [ ] Darunter erscheint die Tabelle der nicht verfügbaren Geräte

### 6.2 Kacheln anklicken

- [ ] Klicke auf **„In Wartung"** → du siehst nur Geräte mit Status „Wartung"
- [ ] Klicke auf **„Verfügbar"** → du siehst nur verfügbare Geräte
- [ ] Klicke auf **„Alle Geräte"** → du siehst alle Geräte
- [ ] Der **„Zurück"**-Button bringt dich zurück zum Dashboard

### 6.3 Geräteübersicht

- [ ] Klicke oben auf **„Geräte"** → Liste aller Geräte mit Status erscheint
- [ ] Du kannst **nichts verändern** – keine Buttons zum Löschen oder Bearbeiten sichtbar

### 6.4 Verfügbarkeitsbericht

- [ ] Klicke oben auf **„Verfügbarkeit"**
- [ ] Wähle einen Datumsbereich (z.B. heute bis in 2 Wochen) → Klicke „Anzeigen"
- [ ] Defekte aus diesem Zeitraum erscheinen in der Tabelle
- [ ] Klicke auf **„CSV exportieren"** → eine CSV-Datei wird heruntergeladen (mit Excel öffnbar)

### 6.5 Was der Disponent NICHT darf (prüfen ob geblockt)

- [ ] Gib in der Adresszeile `http://localhost:5000/admin/` ein → **Fehlermeldung „Zugriff verweigert"** erscheint (roter Kasten) – das ist korrekt
- [ ] Gib `http://localhost:5000/admin/benutzer` ein → ebenfalls Zugriff verweigert

### 6.6 Hilfe-Seite

- [ ] Klicke oben auf **„Hilfe"** → Hilfeseite öffnet sich (kein Fehler)

---

## 7. Test-Checkliste – Community-User (Techniker)

Melde dich mit `techniker1` / `Test1234` an.

### 7.1 Was der Community-User sieht

- [ ] Nach dem Login landest du auf der **Defektliste** (`/admin/alle-defekte`)
- [ ] Du siehst alle gemeldeten Defekte (Lesezugriff)

### 7.2 Was der Community-User NICHT darf (prüfen ob geblockt)

- [ ] Gib `http://localhost:5000/admin/benutzer` in der Adresszeile ein → **„Zugriff verweigert"**
- [ ] Gib `http://localhost:5000/disponent/` ein → **„Zugriff verweigert"**

---

## 8. Test-Checkliste – QR-Code-Scan (Gerät melden)

Dieser Test prüft den Hauptworkflow: ein Techniker scannt einen QR-Code und meldet einen Defekt.

### 8.1 Vorbereitung

1. Melde dich als **admin** an
2. Lege ein Testgerät an (z.B. `CAM-QR-TEST`)
3. Rufe den QR-Code dieses Geräts ab (Admin → Gerät anklicken → QR-Code)
4. **Wichtig für Handy-Tests:** Stelle sicher, dass `APP_BASE_URL` in der `.env` auf die IP-Adresse deines Computers zeigt, z.B.:
   ```
   APP_BASE_URL=http://192.168.1.100:5000
   ```
   So kann dein Handy die gleiche App erreichen.

### 8.2 QR-Code scannen und Defekt melden

- [ ] Scanne den QR-Code mit dem Handy (oder öffne die URL `http://localhost:5000/bericht/CAM-QR-TEST` im Browser)
- [ ] Das **Meldeformular** erscheint – du siehst den Gerätenamen oben
- [ ] Fülle alle Pflichtfelder aus:
  - Kategorie wählen (Pflicht)
  - Beschreibung eingeben (Pflicht)
  - Dein Name (Pflicht)
  - Event-Name und Projektnummer (Pflicht)
- [ ] Klicke auf **„Defekt melden"**
- [ ] Erfolgsseite erscheint mit der Bestätigung

### 8.3 Was danach passiert (als Admin prüfen)

- [ ] Melde dich als **admin** an
- [ ] In der Defektliste erscheint der neue Defekt mit Status **„Offen"**
- [ ] Das Gerät `CAM-QR-TEST` hat jetzt den Status **„Wartung"**
- [ ] Im Server-Log (Terminal) sollte eine Meldung erscheinen, dass eine E-Mail versucht wurde zu senden (kein Fehler – nur unterdrückt wegen `MAIL_SUPPRESS_SEND=true`)

### 8.4 Defekt beheben

- [ ] Als **admin**: Klicke auf den Defekt → „Als behoben markieren"
- [ ] Gerät springt zurück auf **„Verfügbar"**
- [ ] Defekt-Status zeigt **„Behoben"**

---

## 9. Was du NICHT tun musst

Folgendes ist beim Testen einer neuen Version **nicht erforderlich** und kann übersprungen werden:

- ~~API-Endpunkte direkt aufrufen~~ (macht der Entwickler)
- ~~Datenbank direkt bearbeiten~~
- ~~FileMaker konfigurieren~~ (optionale Integration, nicht Kern des Tests)
- ~~Prometheus / Grafana prüfen~~ (Monitoring, nicht funktional)
- ~~E-Mail-Versand verifizieren~~ (E-Mails sind im Test-Modus deaktiviert)

---

## 10. Fehler melden – was du notieren sollst

Wenn etwas nicht funktioniert wie erwartet, notiere bitte:

1. **Was wolltest du tun?**
   Beispiel: „Ich wollte als Disponent auf `/admin/benutzer` zugreifen."

2. **Was ist passiert?**
   Beispiel: „Statt 'Zugriff verweigert' habe ich die Admin-Seite gesehen."

3. **URL in der Adresszeile**
   Beispiel: `http://localhost:5000/admin/benutzer`

4. **Mit welchem Benutzerkonto?**
   Beispiel: `disponent1`

5. **Screenshot** (falls möglich)

6. **Was hast du vorher gemacht?**
   Schritt für Schritt, falls relevant.

---

### Schnell-Referenz: Welche Seiten darf wer sehen?

| Seite | Admin | Disponent | Community |
|---|:---:|:---:|:---:|
| `/admin/` (Dashboard) | ✅ | ❌ | ❌ |
| `/admin/benutzer` | ✅ | ❌ | ❌ |
| `/admin/alle-defekte` | ✅ | ❌ | ✅ |
| `/disponent/` | ✅ | ✅ | ❌ |
| `/disponent/geraete` | ✅ | ✅ | ❌ |
| `/disponent/verfuegbarkeit` | ✅ | ✅ | ❌ |
| `/bericht/<geraet-id>` (QR-Formular) | ✅ | ✅ | ✅ |
| `/auth/hilfe` | ✅ | ✅ | ❌ |

✅ = Zugriff erlaubt · ❌ = „Zugriff verweigert" muss erscheinen

---

*Redline Testanleitung – Stand entspricht Versionsdatei `VERSION`*
