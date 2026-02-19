# Redline – QR-Code-basiertes Defektmeldesystem

Ein webbasiertes Qualitätssicherungssystem für Redline Enterprise. Techniker scannen einen QR-Code an einem Gerät, melden Defekte über eine mobile Webseite, und das System setzt den Gerätestatus automatisch auf „Wartung" – mit Benachrichtigung der Werkstatt und Integration in FileMaker.

---

## Features

- **QR-Code-Scanning** – Direktlink zur Defektmeldungsseite pro Gerät
- **Defekt melden** – Kategorie, Beschreibung, Eventname & Projektnummer
- **FileMaker-Integration** – Gerätestatus & Defektdaten via REST API
- **E-Mail-Benachrichtigungen** – Sofortige Meldung an die Werkstatt
- **Ereignisberichte** – Post-Event-Zusammenfassung aller Defekte
- **Defekthistorie** – Pro Gerät, paginiert
- **Reparatur-Workflow** – Defekte als behoben markieren, Status zurücksetzen
- **Benutzerverwaltung** – Admin + Gemeinschaftsuser `team_login`
- **Mobile-first UI** – iOS-inspiriertes Design, grosse Schriften

---

## Schnellstart

### Voraussetzungen

- Python 3.10+
- pip

### Installation

```bash
# 1. In das Projektverzeichnis wechseln
cd Redline-

# 2. Virtuelle Umgebung erstellen und aktivieren
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 3. Abhängigkeiten installieren
pip install -r requirements.txt

# 4. Konfigurationsdatei anlegen
cp .env.example .env
# .env nach Bedarf anpassen (E-Mail, FileMaker, etc.)

# 5. Anwendung starten
python app.py
```

Die Anwendung läuft auf http://localhost:5000.

### Standard-Zugangsdaten (sofort ändern!)

| Benutzername | Passwort   | Rolle              |
|--------------|------------|--------------------|
| `admin`      | `admin123` | Administrator      |
| `team_login` | `team2025` | Gemeinschaftsuser  |

---

## Projektstruktur

```
Redline-/
├── app.py              # Flask-Anwendung (Blueprints, Routen)
├── models.py           # Datenbankmodelle (User, Device, Defect)
├── config.py           # Konfiguration (Env-Variablen)
├── filemaker.py        # FileMaker Data API Client
├── notifications.py    # E-Mail-Benachrichtigungen
├── requirements.txt    # Python-Abhängigkeiten
├── .env.example        # Beispielkonfiguration
├── static/
│   ├── css/style.css   # Mobile-first CSS
│   ├── js/main.js      # Frontend-JavaScript
│   └── qrcodes/        # Generierte QR-Code-Bilder
└── templates/
    ├── base.html
    ├── login.html
    ├── report_defect.html
    ├── defect_success.html
    ├── error.html
    └── admin/
        ├── dashboard.html
        ├── devices.html
        ├── qr_page.html
        ├── device_history.html
        ├── all_defects.html
        ├── users.html
        └── event_report.html
```

---

## Workflow

1. **Administrator** legt Gerät an (Admin → Geräteverwaltung)
2. **Administrator** generiert QR-Code und druckt ihn aus
3. **Techniker** scannt QR-Code → wird zur Defektmeldungsseite weitergeleitet
4. **Techniker** meldet Defekt (Kategorie, Beschreibung, Event, Projektnummer)
5. **System** setzt Gerätestatus auf „Wartung", schreibt Defekt in FileMaker, sendet E-Mail
6. **Werkstatt** empfängt Benachrichtigung und repariert das Gerät
7. **Werkstatt** markiert Defekt als behoben → Status wechselt zu „Verfügbar"
8. **Nach Event**: Administrator sendet Zusammenfassungsbericht per E-Mail

---

## Konfiguration

Alle Einstellungen werden über eine `.env`-Datei gesteuert (siehe `.env.example`):

| Variable           | Beschreibung                              |
|--------------------|-------------------------------------------|
| `SECRET_KEY`       | Flask Session Secret (zufällig wählen)    |
| `DATABASE_URL`     | Datenbankverbindung (Standard: SQLite)    |
| `MAIL_SERVER`      | SMTP-Server für E-Mail                    |
| `WORKSHOP_EMAIL`   | Empfänger-Adresse der Werkstatt           |
| `FILEMAKER_HOST`   | FileMaker Server URL                      |
| `APP_BASE_URL`     | Öffentliche URL der Anwendung (für QR)    |

---

## FileMaker-Integration

Der Client in `filemaker.py` spricht die **FileMaker Data API v2**.
Im POC-Modus (kein `FILEMAKER_PASSWORD` gesetzt) werden alle API-Aufrufe nur geloggt – kein Fehler.

Benötigte FileMaker-Layouts:
- `Geräte` mit Feldern: `Geräte-ID`, `Status`
- `Defekte` mit Feldern: `Geräte-ID`, `Gerätename`, `Kategorie`, `Beschreibung`, `Eventname`, `Projektnummer`, `Status`, `Gemeldet_Von`
