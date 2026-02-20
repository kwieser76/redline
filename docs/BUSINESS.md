# Redline – Business Documentation

**Produkt:** Redline Defektmeldesystem
**Betreiber:** Redline Event Engineering
**Version:** 1.0.0
**Sprache:** Deutsch (Fachbegriffe im System auf Deutsch)

---

## Inhaltsverzeichnis

1. [Geschäftlicher Kontext](#1-geschäftlicher-kontext)
2. [Stakeholder](#2-stakeholder)
3. [Benutzerrollen & Zugriffsrechte](#3-benutzerrollen--zugriffsrechte)
4. [Kernprozesse](#4-kernprozesse)
5. [Anwendungsfälle (Use Cases)](#5-anwendungsfälle-use-cases)
6. [Datenstrategie](#6-datenstrategie)
7. [E-Mail-Kommunikation](#7-e-mail-kommunikation)
8. [FileMaker-Integration](#8-filemaker-integration)
9. [Berichte & Auswertungen](#9-berichte--auswertungen)
10. [Nicht-funktionale Anforderungen (Geschäftssicht)](#10-nicht-funktionale-anforderungen-geschäftssicht)
11. [Glossar](#11-glossar)

---

## 1. Geschäftlicher Kontext

Redline Event Engineering setzt bei Veranstaltungen eine grosse Anzahl an technischen Geräten (Kameras, Lichtequipment, Tontechnik, etc.) ein. Bisher wurden Defekte mündlich oder per Textnachricht gemeldet, was zu Informationsverlusten, fehlender Nachvollziehbarkeit und lückenhafter Dokumentation führte.

**Das Redline Defektmeldesystem löst folgende Probleme:**

| Problem (vorher) | Lösung (jetzt) |
|------------------|----------------|
| Defektmeldungen gehen verloren | Zentrale Datenbank, jeder Defekt wird persistiert |
| Keine Nachverfolgung, wer was wann gemeldet hat | Reporter, Zeitstempel und Projektzuordnung werden automatisch erfasst |
| Werkstatt weiss nicht, welche Geräte auf Reparatur warten | Gerätestatus `Wartung` / `Verfügbar` in Echtzeit |
| Keine Post-Event-Auswertung | Ereignisberichte per E-Mail nach Projektabschluss |
| Techniker müssen ein separates Tool erlernen | QR-Code scannen genügt – kein App-Download, kein Login-Setup |

---

## 2. Stakeholder

| Stakeholder | Rolle im System | Interesse |
|-------------|----------------|-----------|
| **Techniker** | Meldet Defekte via Smartphone | Schnelle, unkomplizierte Meldung; kein Aufwand |
| **Werkstatt / Technikverantwortlicher** | Empfängt Meldungen, repariert Geräte | Vollständige Informationen zur Fehlerdiagnose |
| **Administrator** | Verwaltet System, schliesst Defekte ab | Überblick über Gerätestatus, Auswertungen |
| **Projektleitung** | Erhält Ereignisberichte | Dokumentation für Post-Event-Analyse |
| **IT-Betrieb** | Betreibt die Anwendung | Stabilität, Sicherheit, Wartbarkeit |

---

## 3. Benutzerrollen & Zugriffsrechte

### Rollenmatrix

| Funktion | Techniker (`team_login`) | Administrator (`admin`) |
|----------|--------------------------|------------------------|
| QR-Code scannen & Defekt melden | ✓ | ✓ |
| Defektliste einsehen | ✓ | ✓ |
| Defekt als behoben markieren | – | ✓ |
| Gerät anlegen / löschen | – | ✓ |
| QR-Code generieren & herunterladen | – | ✓ |
| Benutzer verwalten | – | ✓ |
| E-Mail-Empfänger verwalten | – | ✓ |
| Defektkategorien verwalten | – | ✓ |
| Ereignisbericht versenden | – | ✓ |
| REST API lesen | ✓ | ✓ |
| REST API schreiben (Defekt melden) | ✓ | ✓ |
| REST API Admin-Funktionen | – | ✓ |

### Benutzerkonten

Das System unterstützt zwei Kontentypen:

- **Admin-Account** (`is_admin=True`): Vollzugriff auf alle Funktionen. Jeder Admin-Mitarbeiter sollte einen eigenen Account haben, um Aktionen nachverfolgen zu können.
- **Community-Account** (`is_community=True`): Ein gemeinsam genutzter Account für Techniker. Der Standard-Account `team_login` wird beim ersten Start angelegt. Passwort sollte nach jedem Projekt gewechselt werden.

---

## 4. Kernprozesse

### Prozess 1: Defektmeldung (Standardfall)

```
┌────────────────────────────────────────────────────────────────┐
│ 1. Admin legt Gerät an & generiert QR-Code                     │
│    → QR-Code wird am Gerät angebracht (Aufkleber / Anhänger)   │
└──────────────────────────────────┬─────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────┐
│ 2. Techniker entdeckt Defekt während des Events                │
│    → Smartphone: QR-Code am Gerät scannen                      │
│    → Browser öffnet Meldeformular direkt (kein App-Download)   │
└──────────────────────────────────┬─────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────┐
│ 3. Techniker füllt Formular aus                                │
│    ┌─────────────────────────────────────────┐                 │
│    │ • Kategorie (Dropdown)                  │                 │
│    │ • Beschreibung (Freitext)               │                 │
│    │ • Eventname                             │                 │
│    │ • Projektnummer                         │                 │
│    └─────────────────────────────────────────┘                 │
└──────────────────────────────────┬─────────────────────────────┘
                                   │ POST /report/<device_id>
┌──────────────────────────────────▼─────────────────────────────┐
│ 4. System (automatisch)                                        │
│    • Defekt in Datenbank gespeichert (Status: Offen)           │
│    • Gerätestatus → Wartung                                    │
│    • Erfolgsseite mit mailto:-Button angezeigt                 │
└──────────────────────────────────┬─────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────┐
│ 5. Techniker tippt auf „E-Mail senden"-Button                  │
│    → Nativer Mail-Client öffnet sich mit vorausgefülltem       │
│      Bericht (Gerät, Kategorie, Beschreibung, Event, Zeit)     │
│    → Techniker sendet E-Mail an konfigurierte Empfänger        │
└──────────────────────────────────┬─────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────┐
│ 6. Werkstatt empfängt E-Mail & beginnt Reparatur               │
└──────────────────────────────────┬─────────────────────────────┘
                                   │
┌──────────────────────────────────▼─────────────────────────────┐
│ 7. Admin markiert Defekt als behoben (Admin → Gerät → Reparier)│
│    • Defektstatus → Behoben                                    │
│    • Reparaturnotiz wird gespeichert                           │
│    • Falls keine offenen Defekte mehr: Gerät → Verfügbar       │
└────────────────────────────────────────────────────────────────┘
```

### Prozess 2: Post-Event-Bericht

```
1. Event ist abgeschlossen
2. Admin öffnet Admin → Ereignisbericht
3. Admin wählt Event & Projektnummer aus Dropdown
4. Admin gibt Empfänger-E-Mail-Adresse ein
5. Klick auf „Bericht senden"
6. System sendet E-Mail mit vollständiger Defektliste (offen + behoben)
   via konfigurierten SMTP-Server
7. Empfänger (z.B. Projektleitung) erhält Zusammenfassung
```

### Prozess 3: Neues Gerät onboarden

```
1. Admin → Geräteverwaltung → Neues Gerät anlegen
   (Geräte-ID, Name, Beschreibung)
2. Admin → QR-Code anzeigen → QR-Code herunterladen
3. QR-Code drucken und am Gerät befestigen
4. Gerät ist ab sofort im System erfasst und für Meldungen bereit
```

---

## 5. Anwendungsfälle (Use Cases)

### UC-01: Defekt melden (Techniker)

| Attribut | Beschreibung |
|----------|-------------|
| **Akteur** | Techniker (Smartphone) |
| **Vorbedingung** | Gerät ist im System registriert; Techniker ist angemeldet |
| **Auslöser** | Techniker entdeckt Defekt am Gerät |
| **Ablauf** | QR-Code scannen → Formular ausfüllen → Absenden → E-Mail senden |
| **Ergebnis** | Defekt in DB (Status: Offen); Gerät auf Wartung; Werkstatt informiert |
| **Fehlerfall** | Gerät nicht gefunden → Fehlermeldung; Pflichtfeld leer → Validierungsfehler |

### UC-02: Defekt beheben (Admin)

| Attribut | Beschreibung |
|----------|-------------|
| **Akteur** | Administrator |
| **Vorbedingung** | Defekt existiert mit Status „Offen" |
| **Ablauf** | Admin → Defekthistorie → Reparieren → Notiz eingeben → Bestätigen |
| **Ergebnis** | Defekt Status „Behoben"; ggf. Gerät → „Verfügbar" |

### UC-03: Gerät anlegen (Admin)

| Attribut | Beschreibung |
|----------|-------------|
| **Akteur** | Administrator |
| **Vorbedingung** | Admin ist angemeldet |
| **Ablauf** | Admin → Geräte → Hinzufügen → Geräte-ID + Name eingeben → Speichern |
| **Ergebnis** | Gerät in DB; QR-Code kann generiert werden |
| **Fehlerfall** | Geräte-ID bereits vergeben → Fehlermeldung |

### UC-04: QR-Code generieren & drucken (Admin)

| Attribut | Beschreibung |
|----------|-------------|
| **Akteur** | Administrator |
| **Ablauf** | Admin → Geräte → QR-Code-Symbol → PNG herunterladen → Drucken |
| **Ergebnis** | QR-Code-PNG mit eingebetteter Meldeformular-URL |

### UC-05: Ereignisbericht versenden (Admin)

| Attribut | Beschreibung |
|----------|-------------|
| **Akteur** | Administrator |
| **Vorbedingung** | Defekte für das Event vorhanden; SMTP konfiguriert |
| **Ablauf** | Admin → Ereignisbericht → Event auswählen → Empfänger eingeben → Senden |
| **Ergebnis** | E-Mail mit Defektliste an Empfänger versandt |

### UC-06: Empfänger verwalten (Admin)

| Attribut | Beschreibung |
|----------|-------------|
| **Akteur** | Administrator |
| **Ablauf** | Admin → E-Mail-Empfänger → Hinzufügen / Deaktivieren / Löschen |
| **Ergebnis** | Nur aktive Empfänger erhalten `mailto:`-Links auf der Erfolgsseite |

### UC-07: Defekte filtern & auswerten (Admin)

| Attribut | Beschreibung |
|----------|-------------|
| **Akteur** | Administrator |
| **Ablauf** | Admin → Alle Defekte → Filter nach Status / Eventname anwenden |
| **Ergebnis** | Gefilterte, paginierte Defektliste |

---

## 6. Datenstrategie

### Welche Daten werden erfasst?

| Datenpunkt | Quelle | Zweck |
|-----------|--------|-------|
| Geräte-ID | Admin (Anlage) | Identifikation, QR-Code-URL |
| Defektkategorie | Techniker (Dropdown) | Klassifikation, Auswertung |
| Beschreibung | Techniker (Freitext) | Diagnose durch Werkstatt |
| Eventname | Techniker | Projektzuordnung |
| Projektnummer | Techniker | Projektzuordnung, Berichte |
| Reporter | System (Login-Name) | Nachvollziehbarkeit |
| Zeitstempel | System (UTC) | Chronologie, SLA-Messung |
| Reparaturnotiz | Admin | Dokumentation der Massnahme |
| Behebungszeitpunkt | System (UTC) | Ausfallzeit berechnen |

### Datenhaltung

- **Primärdatenbank:** SQLite (Entwicklung/kleine Deployments) oder PostgreSQL (Produktion)
- **Datenspeicherort:** Lokal auf dem Server / Docker Volume
- **Retention:** Keine automatische Löschung; Defekte werden dauerhaft archiviert
- **Backup:** Tägliches Datenbank-Backup empfohlen (siehe INSTALLATION.md)

### DSGVO-Hinweis

Das System speichert den **Benutzernamen** des Melders. Falls Benutzernamen personenbezogen sind (z.B. Vor- und Nachname), ist die DSGVO-Konformität zu prüfen. Empfehlung: Community-Account `team_login` verwenden (kein Personenbezug).

---

## 7. E-Mail-Kommunikation

### Zwei unabhängige E-Mail-Wege

| Weg | Technologie | Zweck | SMTP nötig? |
|-----|-------------|-------|-------------|
| **Defektmeldung** | `mailto:` Link | Werkstatt sofort informieren | **Nein** |
| **Ereignisbericht** | Flask-Mail (SMTP) | Post-Event-Dokumentation | **Ja** |

### Defektmeldungs-E-Mail (mailto:)

- Server baut URL auf: `mailto:empf1@example.com,empf2@example.com?subject=...&body=...`
- Techniker tippt auf Button → nativer Mail-Client öffnet sich
- E-Mail-Versand erfolgt durch den **Mail-Client des Technikers**
- Inhalt: Gerätename, Kategorie, Beschreibung, Eventname, Projektnummer, Zeitstempel, Reporter

### Empfänger verwalten

Empfänger werden im Admin-Bereich gepflegt:
- **Aktiv:** Erscheinen im `mailto:`-Link
- **Inaktiv:** Werden übersprungen (z.B. bei Abwesenheit)
- Beim ersten App-Start wird `WORKSHOP_EMAIL` automatisch als erster Empfänger angelegt

---

## 8. FileMaker-Integration

Das System kann optional mit einer bestehenden **FileMaker**-Datenbank synchronisieren.

### Synchronisierte Daten

| Ereignis | FileMaker-Aktion |
|----------|-----------------|
| Defekt gemeldet (API) | Neuer Datensatz im Layout `Defekte` |
| Defekt gemeldet (API) | Gerätestatus im Layout `Geräte` → `Wartung` |
| Defekt behoben (API) | Gerätestatus im Layout `Geräte` → `Verfügbar` |

### POC-Modus

Solange `FILEMAKER_PASSWORD` leer ist, läuft die Integration im **POC-Modus**:
- Keine Netzwerkverbindung zu FileMaker
- Aktionen werden als INFO-Log ausgegeben: `[POC] Would set FileMaker device ...`
- Gesamtsystem funktioniert uneingeschränkt

### Ausfallsicherheit

FileMaker-Fehler sind **nicht-blockierend**. Sie werden geloggt, aber der Defekt wird in jedem Fall in der lokalen Datenbank gespeichert.

---

## 9. Berichte & Auswertungen

### Verfügbare Auswertungen

| Auswertung | Zugang | Format |
|-----------|--------|--------|
| Dashboard (Geräteübersicht) | Admin → Dashboard | Web |
| Defektliste gefiltert | Admin → Alle Defekte | Web (paginiert) |
| Defekthistorie pro Gerät | Admin → Geräte → Historie | Web (paginiert) |
| Ereignisbericht | Admin → Ereignisbericht | E-Mail (Text) |
| Ereignisabfrage (API) | `GET /api/v1/events/{project_number}` | JSON |

### KPIs, die das System ermöglicht

| KPI | Datenquelle |
|-----|-------------|
| Anzahl offener Defekte | `Defect.status = "Offen"` |
| Anzahl Geräte in Wartung | `Device.status = "Wartung"` |
| Defekte pro Event / Projekt | `Defect.project_number` Filter |
| Durchschnittliche Reparaturzeit | `resolved_at - created_at` |
| Häufigste Defektkategorien | Aggregation auf `Defect.category` |
| Defektrate pro Gerät | Anzahl Defekte gruppiert nach `device_id` |

---

## 10. Nicht-funktionale Anforderungen (Geschäftssicht)

| Anforderung | Beschreibung | Massnahme |
|-------------|-------------|-----------|
| **Verfügbarkeit** | System muss während Veranstaltungen erreichbar sein | Docker mit `restart: unless-stopped`; Health-Check |
| **Reaktionszeit** | Meldeformular lädt in < 2 Sekunden auf Smartphone | Optimiertes CSS, keine externen Abhängigkeiten für Formular |
| **Offline-Fähigkeit** | E-Mail-Versand auch ohne App-Verbindung möglich | `mailto:` Link (nativer Client) – unabhängig vom App-Server |
| **Datensicherheit** | Keine unautorisierten Zugriffe auf Defektdaten | Login-Pflicht, Rollen-Kontrolle, HTTPS |
| **Datenverlust-Prävention** | Kein Verlust von Defektmeldungen | Persistente Datenbank; kein reiner In-Memory-Betrieb |
| **Auditierbarkeit** | Wer hat wann was gemeldet? | `reporter` + `created_at` in jedem Defekt |
| **Skalierbarkeit** | Mehrere Events gleichzeitig | Projektnummer-Filter ermöglicht parallele Projektbearbeitung |
| **Wartbarkeit** | System muss durch IT ohne Code-Kenntnisse betrieben werden können | `.env`-Konfiguration; Docker-Deployment; keine manuelle DB-Einrichtung |

---

## 11. Glossar

| Begriff | Bedeutung |
|---------|-----------|
| **Defekt** | Schadensmeldung für ein Gerät (Kategorie, Beschreibung, Status) |
| **Gerät** | Technisches Equipment (Kamera, Licht, Ton etc.) mit eindeutiger Geräte-ID |
| **Geräte-ID** | Eindeutiger Bezeichner eines Geräts (z.B. `CAM-001`) |
| **QR-Code** | Maschinenlesbarer Code, der die Meldeformular-URL des Geräts enkodiert |
| **Wartung** | Gerätestatus: Defekt vorhanden, Gerät nicht einsatzbereit |
| **Verfügbar** | Gerätestatus: Kein offener Defekt, Gerät einsatzbereit |
| **Offen** | Defektstatus: Defekt noch nicht behoben |
| **Behoben** | Defektstatus: Defekt wurde repariert und abgeschlossen |
| **Ereignisbericht** | Post-Event-E-Mail-Zusammenfassung aller Defekte eines Projekts |
| **Projektnummer** | Eindeutige Projektreferenz (z.B. `PRJ-2025-042`) |
| **Eventname** | Bezeichnung der Veranstaltung (z.B. `Sommerfestival 2025`) |
| **Empfänger** | E-Mail-Adresse(n) für Defektbenachrichtigungen via `mailto:` |
| **FileMaker** | Externes Datenbankprogramm, optionale Synchronisationsschnittstelle |
| **mailto:** | URL-Schema zum Öffnen des nativen E-Mail-Clients mit vorausgefüllten Feldern |
| **Community-Account** | Gemeinsam genutzter Login für Techniker (`team_login`) |
