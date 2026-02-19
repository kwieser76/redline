# Redline – QR-Code-basiertes Defektmeldesystem

Webbasiertes Qualitätssicherungssystem für **Redline Event Engineering**. Techniker scannen einen QR-Code am Gerät, füllen das Defektmeldeformular aus und senden den vorausgefüllten Bericht direkt über ihren nativen E-Mail-Client an die konfigurierten Empfänger. Defekte werden parallel in der Datenbank protokolliert und sind über den Admin-Bereich auswertbar.

---

## Features

### Für Techniker (mobil)
- **QR-Code scannen** → direkt zum Meldeformular des jeweiligen Geräts
- **Defekt melden** – Kategorie (Dropdown), Beschreibung, Eventname, Projektnummer
- **E-Mail-Client öffnet automatisch** – vorausgefüllter Bericht, bereit zum Abschicken
- Gerätestatus wird sofort auf **Wartung** gesetzt

### Admin-Bereich
- **Geräteverwaltung** – Geräte anlegen, QR-Codes generieren & herunterladen
- **Defektübersicht** – alle Meldungen, filterbar nach Status & Event
- **Defekthistorie** – pro Gerät, paginiert, mit Reparatur-Workflow
- **E-Mail-Empfänger** – Adressen für die Defektmeldungs-E-Mail pflegen (aktivieren/deaktivieren)
- **Defektkategorien** – Dropdown-Optionen im Meldeformular verwalten & sortieren
- **Benutzerverwaltung** – Admin- und Gemeinschafts-Accounts
- **Ereignisberichte** – Post-Event-Zusammenfassung aller Defekte per E-Mail

### Technisch
- Mobile-first Design im **Redline Brand** (schwarz/rot, Barlow Condensed)
- SQLite-Datenbank (austauschbar via `DATABASE_URL`)
- REST JSON API unter `/api/v1/` mit Swagger UI
- Keine externe Abhängigkeit für die Defektmeldung – E-Mail läuft über den Client des Technikers

---

## Workflow

```
1. Admin legt Gerät an  →  QR-Code generieren & drucken
2. Techniker scannt QR-Code am Gerät
3. Techniker füllt Formular aus (Kategorie, Beschreibung, Event, Projektnr.)
4. Absenden  →  Defekt wird in DB gespeichert, Gerät → „Wartung"
5. E-Mail-Client öffnet automatisch mit vorausgefülltem Bericht
6. Techniker schickt E-Mail ab  →  Empfänger erhalten die Meldung
7. Werkstatt repariert das Gerät
8. Admin markiert Defekt als behoben  →  Gerät → „Verfügbar"
9. Optional: Admin sendet Ereignisbericht nach dem Event
```

---

## Schnellstart

### Voraussetzungen

- Python 3.10+
- pip

### Installation

```bash
# 1. Virtuelle Umgebung erstellen und aktivieren
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Abhängigkeiten installieren
pip install -r requirements.txt

# 3. Konfigurationsdatei anlegen
cp .env.example .env
# .env anpassen (mind. SECRET_KEY und APP_BASE_URL setzen)

# 4. Anwendung starten
python app.py
```

Die Anwendung ist unter **http://localhost:5000** erreichbar.
Datenbank, Standard-Benutzer, Kategorien und erster Empfänger werden beim ersten Start automatisch angelegt.

### Standard-Zugangsdaten (sofort ändern!)

| Benutzername | Passwort   | Rolle             |
|--------------|------------|-------------------|
| `admin`      | `admin123` | Administrator     |
| `team_login` | `team2025` | Gemeinschaftsuser |

---

## Konfiguration

Alle Einstellungen werden über eine `.env`-Datei gesteuert:

| Variable              | Beschreibung                                                                 | Standard                  |
|-----------------------|------------------------------------------------------------------------------|---------------------------|
| `SECRET_KEY`          | Flask Session Secret (in Produktion ändern!)                                 | `change-me-…`             |
| `DATABASE_URL`        | Datenbankverbindung                                                          | SQLite `redline.db`       |
| `APP_BASE_URL`        | Öffentliche URL der Anwendung (Basis für QR-Links)                           | `http://localhost:5000`   |
| `WORKSHOP_EMAIL`      | Initiale Empfänger-Adresse – wird beim ersten Start automatisch angelegt     | `werkstatt@redline.local` |
| `MAIL_SERVER`         | SMTP-Server – **nur für Ereignisberichte** benötigt                          | `smtp.gmail.com`          |
| `MAIL_PORT`           | SMTP-Port                                                                    | `587`                     |
| `MAIL_USERNAME`       | SMTP-Benutzername                                                            | –                         |
| `MAIL_PASSWORD`       | SMTP-Passwort                                                                | –                         |
| `MAIL_DEFAULT_SENDER` | Absenderadresse für Ereignisberichte                                         | `noreply@redline.local`   |

> **Hinweis:** SMTP wird **nur** für den Versand von Ereignisberichten (Post-Event-Zusammenfassung) benötigt.
> Defektmeldungs-E-Mails laufen über den nativen E-Mail-Client des Technikers – kein SMTP-Setup erforderlich.

---

## E-Mail-Empfänger verwalten

Die Empfänger für den `mailto:`-Link werden im Admin-Bereich gepflegt:

**Admin → E-Mail-Empfänger** (`/admin/recipients`)

- Empfänger **hinzufügen** (Name + E-Mail-Adresse)
- Empfänger **aktivieren / deaktivieren** – nur aktive Einträge landen im `mailto:`-Link
- Empfänger **löschen**

Beim ersten App-Start wird `WORKSHOP_EMAIL` aus der `.env` automatisch als erster Empfänger angelegt.

---

## Defektkategorien verwalten

Die Kategorien im Dropdown des Meldeformulars werden im Admin-Bereich verwaltet:

**Admin → Defektkategorien** (`/admin/categories`)

- Kategorien **hinzufügen**, **löschen**
- **Reihenfolge** mit ↑/↓ anpassen (bestimmt die Reihenfolge im Dropdown)

Beim ersten App-Start werden folgende Standard-Kategorien automatisch eingespielt:
`Mechanischer Schaden`, `Elektrischer Fehler`, `Softwareproblem`, `Gehäuseschaden`,
`Kabelproblem`, `Displayschaden`, `Akkuproblem`, `Wasserschaden`, `Sonstiges`

---

## Projektstruktur

```
Redline-/
├── app.py                        # Flask-Anwendung (Blueprints, alle Routen)
├── models.py                     # DB-Modelle (s. unten)
├── config.py                     # Konfiguration & Seed-Daten
├── notifications.py              # Server-E-Mail für Ereignisberichte
├── requirements.txt
├── .env.example
│
├── static/
│   ├── css/style.css             # Redline Brand CSS (schwarz/rot, Barlow Condensed)
│   ├── js/main.js                # Auto-dismiss Alerts, Bestätigungsdialoge
│   ├── img/logo.svg              # Redline Wortmarke (SVG)
│   └── qrcodes/                  # Generierte QR-Code-Bilder
│
└── templates/
    ├── base.html                 # Layout (Navbar mit Logo, Google Fonts)
    ├── login.html                # Login-Seite (schwarzes Branding)
    ├── report_defect.html        # Defektmeldeformular (mobil-optimiert)
    ├── defect_success.html       # Erfolgsseite mit mailto:-Button & Auto-Open
    ├── error.html
    └── admin/
        ├── dashboard.html        # Admin-Übersicht mit Schnellzugriff
        ├── devices.html          # Geräteverwaltung
        ├── qr_page.html          # QR-Code anzeigen & herunterladen
        ├── device_history.html   # Defekthistorie pro Gerät + Reparatur
        ├── all_defects.html      # Alle Defekte (Filter, Pagination)
        ├── users.html            # Benutzerverwaltung
        ├── event_report.html     # Ereignisbericht versenden
        ├── categories.html       # Defektkategorien verwalten
        └── recipients.html       # E-Mail-Empfänger verwalten
```

---

## Datenbankmodelle

| Modell           | Beschreibung                                                |
|------------------|-------------------------------------------------------------|
| `User`           | Admin- und Gemeinschafts-Accounts                           |
| `Device`         | Geräte mit ID, Name, Status (`Verfügbar` / `Wartung`)       |
| `Defect`         | Defektmeldungen mit Kategorie, Beschreibung, Status, Reporter|
| `DefectCategory` | Kategorien für das Dropdown im Meldeformular (sortierbar)   |
| `EmailRecipient` | E-Mail-Adressen für den `mailto:`-Link (aktivierbar)        |

---

## REST JSON API

Vollständige REST API unter `/api/v1/`, interaktive Dokumentation (Swagger UI) unter `/api/docs`.

### Authentifizierung

HTTP Basic Auth – dieselben Zugangsdaten wie die Web-Oberfläche.

```bash
curl -u team_login:team2025 http://localhost:5000/api/v1/devices
```

### Endpunktübersicht

| Methode  | Pfad                              | Beschreibung                       | Admin? |
|----------|-----------------------------------|------------------------------------|--------|
| `GET`    | `/api/v1/devices`                 | Alle Geräte (Filter: `?status=`)  | –      |
| `POST`   | `/api/v1/devices`                 | Gerät anlegen                      | ✓      |
| `GET`    | `/api/v1/devices/{id}`            | Einzelnes Gerät                    | –      |
| `PATCH`  | `/api/v1/devices/{id}`            | Gerät aktualisieren                | ✓      |
| `DELETE` | `/api/v1/devices/{id}`            | Gerät löschen                      | ✓      |
| `GET`    | `/api/v1/devices/{id}/qr`         | QR-Code PNG herunterladen          | ✓      |
| `GET`    | `/api/v1/defects`                 | Defekte (Filter: status, event, …) | –      |
| `POST`   | `/api/v1/defects`                 | Defekt melden                      | –      |
| `GET`    | `/api/v1/defects/{id}`            | Einzelner Defekt                   | –      |
| `PATCH`  | `/api/v1/defects/{id}/resolve`    | Defekt als behoben markieren       | ✓      |
| `GET`    | `/api/v1/events`                  | Alle Events auflisten              | –      |
| `GET`    | `/api/v1/events/{project_number}` | Defekte eines Events               | –      |

### Beispiele

**Defekt melden:**
```bash
curl -u team_login:team2025 -X POST http://localhost:5000/api/v1/defects \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "CAM-001",
    "category": "Gehäuseschaden",
    "description": "Linker Griff gebrochen",
    "event_name": "Sommerfestival 2025",
    "project_number": "PRJ-2025-042"
  }'
```

**Defekte eines Events abrufen:**
```bash
curl -u admin:admin123 http://localhost:5000/api/v1/events/PRJ-2025-042
```

**Defekt als behoben markieren:**
```bash
curl -u admin:admin123 -X PATCH http://localhost:5000/api/v1/defects/42/resolve \
  -H "Content-Type: application/json" \
  -d '{"resolution_notes": "Griff ersetzt und getestet."}'
```
