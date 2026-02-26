# Redline – QR-Code-basiertes Defektmeldesystem

Webbasiertes Qualitätssicherungssystem für **Redline Event Engineering**. Techniker scannen einen QR-Code am Gerät, füllen das Defektmeldeformular aus und senden den vorausgefüllten Bericht direkt über ihren nativen E-Mail-Client an die konfigurierten Empfänger. Defekte werden parallel in der lokalen Datenbank protokolliert und sind über die rollenbasierten Dashboards auswertbar.

**Version:** v0.1b

---

## Rollen & Zugang

| Rolle | Gerät | Einstiegspunkt |
|-------|-------|----------------|
| **Admin** | PC-Browser | `/admin/` |
| **Disponent** | PC-Browser | `/disponent/` |
| **Werkstatt** | PC-Browser / Tablet | `/werkstatt/` |
| **Community** (Techniker) | Smartphone / iPhone | QR-Code scannen → `/report/<geräte-id>` |
| **API-User** | Skript / externes System | `/api/v1/` (kein Web-UI) |

Vollständige Berechtigungsmatrix → **[docs/ROLLEN.md](docs/ROLLEN.md)**

---

## Dokumentation

| Dokument | Inhalt |
|----------|--------|
| [Rollen-Übersicht](docs/ROLLEN.md) | Alle Rollen, Berechtigungsmatrix, Rollen anlegen |
| [API-Referenz](docs/API.md) | Alle REST-Endpunkte, Authentifizierung, Request/Response-Format, curl-Beispiele |
| [Technische Dokumentation](docs/TECHNICAL.md) | Architektur, Datenbankschema, Sicherheit, Deployment, NFR-Übersicht |
| [Installations-Anleitung](docs/INSTALLATION.md) | Lokale Entwicklung, Docker Compose, Hostinger + Cloudflare (Nicht-Techniker), Bare-Metal, Migrationen |
| [Fachliche Dokumentation](docs/BUSINESS.md) | Geschäftsprozesse, Anwendungsfälle, Rollen, Datenstrategie, Glossar |
| [Test-Dokumentation](docs/TESTING.md) | Teststruktur, pytest-Fixtures, alle Testdateien, Tests ausführen |
| [Changelog](CHANGELOG.md) | Versionshistorie mit allen Änderungen |

---

## Features

### Für Techniker (Smartphone / iPhone)
- **QR-Code scannen** → direkt zum Meldeformular des jeweiligen Geräts
- **Defekt melden** – Kategorie (Dropdown), Beschreibung, Eventname, Projektnummer
- **E-Mail-Client öffnet automatisch** – vorausgefüllter Bericht, bereit zum Abschicken
- Gerätestatus wird sofort auf **Wartung** gesetzt

### Admin-Bereich (PC-Browser)
- **Geräteverwaltung** – Geräte anlegen, QR-Codes generieren & herunterladen, Produktkategorien zuweisen
- **Defektübersicht** – alle Meldungen, filterbar nach Status & Event
- **Defekthistorie** – pro Gerät, paginiert, mit Reparatur-Workflow
- **E-Mail-Empfänger** – Adressen für die Defektmeldungs-E-Mail pflegen (aktivieren/deaktivieren)
- **Defektkategorien** – Dropdown-Optionen im Meldeformular verwalten & sortieren
- **Produktkategorien** – Geräte-Kategorisierung mit Farbkodierung
- **Benutzerverwaltung** – alle Rollen anlegen (Admin, Disponent, Werkstatt, API-User)
- **Ereignisberichte** – Post-Event-Zusammenfassung aller Defekte per E-Mail

### Disponent-Dashboard (PC-Browser)
- **4 Kacheln** – Alle Geräte / Verfügbar / Nicht verfügbar / Reserviert
- **Geräteverfügbarkeit** – Datumsbereichsfilter + Produktkategorie-Filter
- **CSV-Export** der Defektdaten

### Werkstatt-Dashboard (PC-Browser / Tablet)
- **Offene Defekte** – Karten-Ansicht aller Defekte mit Werkstatt-Status
- **Werkstatt-Status** – `Ausstehend` / `In Bearbeitung` / `Warten auf Teile` / `Abgeschlossen`
- **Kommentar-System** – Text + Fotos (JPEG/PNG/GIF/WebP, max. 5 MB) mit Autor und Zeitstempel

### Technisch
- Mobile-first Design im **Redline Brand** (schwarz/rot, Barlow Condensed)
- SQLite-Datenbank (austauschbar via `DATABASE_URL`)
- REST JSON API unter `/api/v1/` mit Swagger UI
- Rollenbasierte Zugriffskontrolle (Admin, Disponent, Werkstatt, Community, API-User)
- Prometheus-Metriken + Grafana-Dashboard

---

## Workflow

```
1. Admin legt Gerät an  →  QR-Code generieren & drucken
2. Techniker scannt QR-Code am Gerät
3. Techniker füllt Formular aus (Kategorie, Beschreibung, Event, Projektnr.)
4. Absenden  →  Defekt wird in lokaler DB gespeichert, Gerätestatus → „Wartung"
5. E-Mail-Client öffnet automatisch mit vorausgefülltem Bericht
6. Techniker schickt E-Mail ab  →  Empfänger erhalten die Meldung
7. Werkstatt öffnet Dashboard, setzt Werkstatt-Status, hinterlässt Kommentar/Foto
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
| `disponent`  | `disp2025` | Disponent         |
| `werkstatt`  | `werk2025` | Werkstatt         |
| `team_login` | `team2025` | Community-User    |
| `api`        | `api2025`  | API-User (kein Web-UI) |

---

## Konfiguration

Alle Einstellungen werden über eine `.env`-Datei gesteuert:

| Variable              | Beschreibung                                                                 | Standard                  |
|-----------------------|------------------------------------------------------------------------------|---------------------------|
| `SECRET_KEY`          | Flask Session Secret (in Produktion ändern!)                                 | `change-me-…`             |
| `DATABASE_URL`        | Datenbankverbindung                                                          | SQLite `redline.db`       |
| `APP_BASE_URL`        | Öffentliche URL der Anwendung (Basis für QR-Links) – **muss in Produktion gesetzt werden, sonst sind alle QR-Codes unbrauchbar** | `http://localhost:5000`   |
| `WORKSHOP_EMAIL`      | Initiale Empfänger-Adresse – wird beim ersten Start automatisch angelegt     | `werkstatt@redline.local` |
| `MAIL_SERVER`         | SMTP-Server – **nur für Ereignisberichte** benötigt                          | `smtp.gmail.com`          |
| `MAIL_PORT`           | SMTP-Port                                                                    | `587`                     |
| `MAIL_USERNAME`       | SMTP-Benutzername                                                            | –                         |
| `MAIL_PASSWORD`       | SMTP-Passwort                                                                | –                         |
| `MAIL_DEFAULT_SENDER` | Absenderadresse für Ereignisberichte                                         | `noreply@redline.local`   |

> **Hinweis:** SMTP wird **nur** für den Versand von Ereignisberichten benötigt.
> Defektmeldungs-E-Mails laufen über den nativen E-Mail-Client des Technikers – kein SMTP-Setup erforderlich.

---

## Projektstruktur

```
Redline-/
├── app.py                        # App-Factory (create_app), Fehlerhandler, Seed
├── config.py                     # DevelopmentConfig / ProductionConfig / TestConfig
├── extensions.py                 # Flask-Limiter, Flask-Migrate (shared instances)
├── models.py                     # SQLAlchemy-Modelle + DB-Instanz
├── api.py                        # REST API Blueprint (/api/v1/*)
├── notifications.py              # E-Mail-Helfer (Defektmeldung, Ereignisbericht)
├── filemaker.py                  # FileMaker-Data-API-Client (optional)
├── VERSION                       # Versionsnummer (z.B. 0.1b)
├── CHANGELOG.md                  # Versionshistorie
├── requirements.txt
├── .env.example
├── Dockerfile                    # Multi-Stage Production Image
├── docker-compose.yml            # Docker Compose Deployment
│
├── routes/                       # Web-UI-Blueprints
│   ├── auth.py                   # /auth/login, /auth/logout
│   ├── report.py                 # /report/<device_id>
│   ├── admin.py                  # /admin/* + admin_required-Decorator
│   ├── disponent.py              # /disponent/* + disponent_required-Decorator
│   └── werkstatt.py              # /werkstatt/* + werkstatt_required-Decorator
│
├── static/
│   ├── css/style.css             # Redline Brand CSS (schwarz/rot, Barlow Condensed)
│   ├── js/main.js                # Auto-dismiss Alerts, Bestätigungsdialoge
│   ├── img/logo.svg              # Redline Wortmarke (SVG)
│   ├── openapi.yaml              # OpenAPI 3.0 Spezifikation (Swagger-Quelle)
│   ├── qrcodes/                  # Generierte QR-Code-Bilder
│   └── uploads/                  # Hochgeladene Werkstatt-Fotos
│
├── templates/
│   ├── base.html                 # Layout (Navbar, Footer mit Logo + Version)
│   ├── login.html                # Login-Seite (schwarzes Branding + Version)
│   ├── api_docs.html             # Swagger UI (standalone, mit Zurück-Navigation)
│   ├── report_defect.html        # Defektmeldeformular (mobil-optimiert)
│   ├── defect_success.html       # Erfolgsseite mit mailto:-Button & Auto-Open
│   ├── error.html
│   ├── admin/
│   │   ├── dashboard.html        # Admin-Übersicht mit Schnellzugriff
│   │   ├── devices.html          # Geräteverwaltung + Produktkategorie-Filter
│   │   ├── device_categories.html# Produktkategorie-Verwaltung
│   │   ├── qr_page.html          # QR-Code anzeigen & herunterladen
│   │   ├── device_history.html   # Defekthistorie pro Gerät + Kommentare
│   │   ├── all_defects.html      # Alle Defekte (Filter, Pagination)
│   │   ├── users.html            # Benutzerverwaltung (alle Rollen)
│   │   ├── event_report.html     # Ereignisbericht versenden
│   │   ├── categories.html       # Defektkategorien verwalten
│   │   └── recipients.html       # E-Mail-Empfänger verwalten
│   ├── disponent/
│   │   ├── dashboard.html        # Disponent-Dashboard (4 Kacheln)
│   │   ├── tile_detail.html      # Kachel-Detailansicht
│   │   ├── devices.html          # Geräteliste (read-only)
│   │   └── availability.html     # Geräteverfügbarkeit + CSV-Export
│   └── werkstatt/
│       ├── dashboard.html        # Werkstatt-Dashboard (offene Defekte)
│       └── defect_detail.html    # Defektdetail + Kommentar/Foto-Upload
│
├── docs/
│   ├── ROLLEN.md                 # Vollständige Rollen-Übersicht + Berechtigungsmatrix
│   ├── API.md                    # REST API Referenz
│   ├── TECHNICAL.md              # Technische Architektur & NFR
│   ├── INSTALLATION.md           # Installation & Deployment
│   └── BUSINESS.md               # Fachliche Dokumentation & Prozesse
│
└── tests/
    ├── conftest.py               # Fixtures, TestConfig, clean_db
    ├── test_auth.py              # Authentifizierungs-Tests
    ├── test_models.py            # ORM-Unit-Tests
    ├── test_api.py               # REST-API-Vertrags-Tests (api_user-Rolle)
    ├── test_admin.py             # Admin-Routen-Tests
    ├── test_disponent.py         # Disponent-Rollen-Tests
    ├── test_werkstatt.py         # Werkstatt-Rollen-Tests
    ├── test_device_categories.py # Produktkategorie-Tests
    ├── test_roles.py             # Rollenbasiertes Routing & Zugriffskontrolle
    ├── test_report.py            # Defektformular-Tests
    ├── test_notifications.py     # E-Mail-Tests
    ├── test_nfr.py               # Nicht-funktionale Anforderungen
    ├── test_security.py          # Sicherheits-Tests (OWASP Top 10)
    └── test_business.py          # End-to-End-Geschäftsprozesse
```

---

## Datenbankmodelle

| Modell           | Beschreibung                                                              |
|------------------|---------------------------------------------------------------------------|
| `User`           | Alle Benutzerkonten; Flags: `is_admin`, `is_disponent`, `is_werkstatt`, `is_api_user` |
| `Device`         | Geräte mit ID, Name, Status (`Verfügbar` / `Wartung` / `Reserviert`), Produktkategorie |
| `DeviceCategory` | Produktkategorien für Geräte (Name + Farbe)                               |
| `Defect`         | Defektmeldungen mit Kategorie, Beschreibung, Status, Reporter, Werkstatt-Status |
| `DefectCategory` | Kategorien für das Dropdown im Meldeformular (sortierbar)                 |
| `Comment`        | Werkstatt-Kommentare (Text + optionales Foto, Autor, Rolle, Zeitstempel)  |
| `EmailRecipient` | E-Mail-Adressen für den `mailto:`-Link (aktivierbar)                      |

---

## REST JSON API

Vollständige REST API unter `/api/v1/`, interaktive Dokumentation (Swagger UI) unter `/api/docs`.

### Authentifizierung

Die API verwendet **HTTP Basic Auth** mit einem dedizierten **api_user**-Account.
Web-UI-Accounts (admin, disponent, werkstatt, team_login) erhalten **403 Forbidden** auf allen API-Endpunkten.

```bash
# Nur api_user-Accounts können die API nutzen
curl -u api:api2025 http://localhost:5000/api/v1/devices
```

### Endpunktübersicht

| Methode  | Pfad                              | Beschreibung                       |
|----------|-----------------------------------|------------------------------------|
| `GET`    | `/api/v1/devices`                 | Alle Geräte (Filter: `?status=`)  |
| `POST`   | `/api/v1/devices`                 | Gerät anlegen                      |
| `GET`    | `/api/v1/devices/{id}`            | Einzelnes Gerät                    |
| `PATCH`  | `/api/v1/devices/{id}`            | Gerät aktualisieren                |
| `DELETE` | `/api/v1/devices/{id}`            | Gerät löschen                      |
| `GET`    | `/api/v1/devices/{id}/qr`         | QR-Code PNG herunterladen          |
| `GET`    | `/api/v1/defects`                 | Defekte (Filter: status, event, …) |
| `POST`   | `/api/v1/defects`                 | Defekt melden                      |
| `GET`    | `/api/v1/defects/{id}`            | Einzelner Defekt                   |
| `PATCH`  | `/api/v1/defects/{id}/resolve`    | Defekt als behoben markieren       |
| `GET`    | `/api/v1/events`                  | Alle Events auflisten              |
| `GET`    | `/api/v1/events/{project_number}` | Defekte eines Events               |

Vollständige Dokumentation → **[docs/API.md](docs/API.md)**
