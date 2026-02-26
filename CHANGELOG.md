# Changelog

Alle wesentlichen Änderungen werden in dieser Datei dokumentiert.
Format orientiert sich an [Keep a Changelog](https://keepachangelog.com/de/1.0.0/).

---

## [v0.1b] – 2026-02-26

### Neu hinzugefügt

#### Werkstatt-Rolle
- Neue Benutzerrolle `werkstatt` mit dediziertem Dashboard `/werkstatt/`
- Werkstatt sieht alle offenen Defekte (Karten-Ansicht) mit Werkstatt-Status
- Werkstatt-Status je Defekt: `Ausstehend` / `In Bearbeitung` / `Warten auf Teile` / `Abgeschlossen`
- Kommentar-System: Werkstatt kann Textkommentare + Fotos (JPEG/PNG/GIF/WebP, max. 5 MB) an jeden Defekt anhängen
- Kommentare werden mit Autor, Rolle und Zeitstempel gespeichert
- Admin kann Werkstatt-User in der Benutzerverwaltung anlegen

#### Disponent-Rolle
- Neue Benutzerrolle `disponent` mit dediziertem Dashboard `/disponent/`
- 4 klickbare Kacheln: Alle Geräte / Verfügbar / Nicht verfügbar / Reserviert
- Geräteverfügbarkeits-Übersicht mit Datumsbereichsfilter und Kategoriefilter
- Geräteverwaltung (read-only) mit Statusbadges
- CSV-Export der Defektdaten

#### Produktkategorien
- Neue Entität `DeviceCategory` (Name + Farbe) für Geräte
- Admin kann Produktkategorien anlegen, bearbeiten, löschen
- Geräte können einer Produktkategorie zugewiesen werden
- Produktkategorie-Filter in Geräteverwaltung, Disponent-Ansicht und Admin-Übersichten
- Farbige Kategorie-Badges in allen Gerätelisten

#### API-Sicherheit (api_user-Rolle)
- Neue dedizierte Rolle `api_user` (`is_api_user=True` am User-Modell)
- `api_user`-Accounts haben **ausschliesslich** Zugriff auf REST-API-Endpunkte
- Alle anderen Rollen (admin, disponent, werkstatt, community) erhalten `403 Forbidden` auf allen API-Endpunkten
- Standard-API-User `api` (Passwort `api2025`) wird beim ersten Start automatisch angelegt
- Admin-UI: "API-Zugriff"-Checkbox in der Benutzerverwaltung
- Versucht ein `api_user` die Web-Oberfläche zu nutzen, wird er sofort ausgeloggt

#### Navigation & UI
- `api_docs.html`: Sticky Top-Bar mit „← Zurück zur Hauptseite"-Link und `api_user`-Badge
- Prüfung aller Unterseiten auf fehlende Zurück-Navigation

#### Footer
- Neuer Marken-Footer auf **allen** Seiten (Admin, Disponent, Werkstatt, Public)
- Inhalt: Firmenlogo (weiß), Tagline „Defektmeldesystem", Versionsbadge, Copyright-Jahr
- Responsiv (Mobile + Desktop), Farbschema: `--black` (#1a1a1a)

#### Versionsnummer
- `VERSION`-Datei → `0.1b`
- Versionsnummer sichtbar im Footer aller Seiten (`v{{ app_version }}`)
- Versionsnummer sichtbar auf dem Login-Screen

### Geändert

- `models.py`: `User`-Modell um `is_api_user`, `is_disponent`, `is_werkstatt` Felder erweitert
- `models.py`: `User.role`-Property gibt nun `"api"`, `"disponent"`, `"werkstatt"`, `"community"` oder `"admin"` zurück
- `models.py`: Neue Modelle `DeviceCategory`, `Comment`
- `api.py`: `_require_auth`-Decorator prüft jetzt `is_api_user` statt generischer Anmeldung
- `app.py`: Seeding um `disponent`, `werkstatt`, `api` Default-User erweitert; `current_year` im Context-Processor
- `routes/admin.py`: Erstellen von Usern mit Rollen-Flags; Produktkategorie-Verwaltung
- `static/css/style.css`: Footer-Styles, Kachel-Styles (`.stat-card-link`), Kategorie-Badges (`.cat-badge`)
- `static/openapi.yaml`: Authentifizierungs-Abschnitt auf `api_user`-Rolle aktualisiert, Version `0.1b`

### Dokumentation

- `docs/ROLLEN.md`: Neue vollständige Rollen-Übersicht (Tabelle: Rolle / Kann / Kann nicht)
- `docs/API.md`: Auth-Abschnitt und curl-Beispiele auf `api_user` aktualisiert
- `README.md`: Alle neuen Rollen, Zugangsdaten, Datenbankmodelle, Projektstruktur

### Tests

- 524 Tests, alle grün (`pytest`)
- Neue Testdateien: `test_disponent.py`, `test_werkstatt.py`, `test_device_categories.py`, `test_roles.py`
- Bestehende Tests auf `api_headers`-Fixture migriert (`test_api.py`, `test_nfr.py`, `test_security.py`, `test_business.py`)

---

## [v0.0.1] – 2025-01-01

### Neu hinzugefügt

- Grundsystem: QR-Code-basiertes Defektmeldeformular
- Admin-Bereich: Geräteverwaltung, Defektübersicht, Defekthistorie, Benutzerverwaltung
- E-Mail-Empfänger-Verwaltung (activierbar/deaktivierbar)
- Defektkategorien (sortierbar)
- REST JSON API `/api/v1/` mit Swagger UI unter `/api/docs`
- Docker-Compose-Deployment, Prometheus-Metriken
