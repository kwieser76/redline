# Redline – Rollen-Übersicht

Alle Benutzerrollen des Redline Defektmeldesystems auf einen Blick.

---

## Rollenübersicht

| Rolle | Benutzername (Default) | Passwort (Default) | Einstiegspunkt |
|-------|----------------------|-------------------|----------------|
| **Admin** | `admin` | `admin123` | `/admin/` |
| **Disponent** | `disponent` | `disp2025` | `/disponent/` |
| **Werkstatt** | `werkstatt` | `werk2025` | `/werkstatt/` |
| **Community** | `team_login` | `team2025` | `/` (Defektliste) |
| **API-User** | `api` | `api2025` | – (kein Web-UI) |

> **Sicherheitshinweis:** Alle Standard-Passwörter vor dem Produktiveinsatz ändern!

---

## Detaillierte Berechtigungen

### Admin

| Funktion | Berechtigung |
|----------|-------------|
| Geräte anlegen / bearbeiten / löschen | ✅ |
| QR-Codes generieren & herunterladen | ✅ |
| Defekte einsehen (alle) | ✅ |
| Defekte als behoben markieren | ✅ |
| Defekthistorie pro Gerät | ✅ |
| Kommentare schreiben | ✅ |
| Fotos hochladen | ✅ |
| Benutzer anlegen / löschen | ✅ |
| Rollen vergeben (Disponent, Werkstatt, api_user) | ✅ |
| E-Mail-Empfänger verwalten | ✅ |
| Defektkategorien verwalten | ✅ |
| Produktkategorien verwalten | ✅ |
| Ereignisbericht versenden | ✅ |
| Disponent-Dashboard einsehen | ✅ |
| Werkstatt-Dashboard einsehen | ✅ |
| REST API nutzen | ❌ (kein api_user) |

---

### Disponent

| Funktion | Berechtigung |
|----------|-------------|
| Disponent-Dashboard (4 Kacheln) | ✅ |
| Geräteverfügbarkeit einsehen | ✅ |
| Geräteliste (read-only) | ✅ |
| Defekte einsehen (über API, read-only) | ✅ |
| CSV-Export Defektdaten | ✅ |
| Produktkategorie-Filter | ✅ |
| Geräte anlegen / bearbeiten / löschen | ❌ |
| Defekte als behoben markieren | ❌ |
| Kommentare / Fotos | ❌ |
| Admin-Bereich | ❌ (403) |
| Werkstatt-Bereich | ❌ (403) |
| REST API nutzen | ❌ (kein api_user) |

---

### Werkstatt

| Funktion | Berechtigung |
|----------|-------------|
| Werkstatt-Dashboard (offene Defekte) | ✅ |
| Defektdetail einsehen | ✅ |
| Werkstatt-Status eines Defekts ändern | ✅ |
| Textkommentare zum Defekt schreiben | ✅ |
| Fotos zum Defekt hochladen (JPEG/PNG/GIF/WebP, max. 5 MB) | ✅ |
| Defekte als offiziell behoben markieren | ❌ (Admin-Funktion) |
| Geräte anlegen / bearbeiten | ❌ |
| Benutzer verwalten | ❌ |
| Admin-Bereich | ❌ (403) |
| Disponent-Bereich | ❌ (403) |
| REST API nutzen | ❌ (kein api_user) |

---

### Community (team_login)

| Funktion | Berechtigung |
|----------|-------------|
| Defektmeldeformular aufrufen (via QR-Code) | ✅ |
| Defekt melden (Formular) | ✅ |
| Eigene offene Defekte einsehen | ✅ |
| Admin-Bereich | ❌ (403) |
| Disponent-Bereich | ❌ (403) |
| Werkstatt-Bereich | ❌ (403) |
| REST API nutzen | ❌ (kein api_user) |

> **Hinweis:** Der Community-Account `team_login` ist ein gemeinsam genutzter Account für alle Techniker, die QR-Codes scannen und Defekte melden.

---

### API-User

| Funktion | Berechtigung |
|----------|-------------|
| REST API – alle Endpunkte lesen | ✅ |
| REST API – Geräte anlegen / bearbeiten / löschen | ✅ |
| REST API – Defekte melden | ✅ |
| REST API – Defekte als behoben markieren | ✅ |
| REST API – QR-Code herunterladen | ✅ |
| REST API – Ereignisse abrufen | ✅ |
| Web-Oberfläche (Admin/Disponent/Werkstatt/Login) | ❌ (sofort ausgeloggt) |

> **Sicherheit:** API-User sind ausschliesslich für die maschinelle Nutzung (Integrations, Skripte, externe Systeme) vorgesehen.
> Web-UI-Accounts (admin, disponent, werkstatt, team_login) können die REST API **nicht** nutzen und erhalten `403 Forbidden`.

---

## Rollenmatrix (Kurzform)

| Bereich / Funktion | admin | disponent | werkstatt | community | api_user |
|-------------------|:-----:|:---------:|:---------:|:---------:|:--------:|
| `/admin/*` | ✅ | ❌ | ❌ | ❌ | ❌ |
| `/disponent/*` | ✅ | ✅ | ❌ | ❌ | ❌ |
| `/werkstatt/*` | ✅ | ❌ | ✅ | ❌ | ❌ |
| `/report/<id>` (Defekt melden) | ✅ | ✅ | ✅ | ✅ | ❌ |
| `/api/v1/*` (REST API) | ❌ | ❌ | ❌ | ❌ | ✅ |
| Gerät anlegen/löschen | ✅ | ❌ | ❌ | ❌ | ✅ via API |
| Defekt melden | ✅ | ❌ | ❌ | ✅ | ✅ via API |
| Defekt beheben (offiziell) | ✅ | ❌ | ❌ | ❌ | ✅ via API |
| Werkstatt-Status ändern | ✅ | ❌ | ✅ | ❌ | ❌ |
| Kommentare / Fotos | ✅ | ❌ | ✅ | ❌ | ❌ |
| Benutzer verwalten | ✅ | ❌ | ❌ | ❌ | ❌ |

---

## Rollen anlegen

Neue Benutzer mit spezifischen Rollen werden im Admin-Bereich angelegt:

**Admin → Benutzerverwaltung** (`/admin/users`)

1. Benutzername und Passwort eingeben
2. Entsprechende Rolle auswählen:
   - **Administrator**: Checkbox „Administrator"
   - **Disponent**: Checkbox „Disponent"
   - **Werkstatt**: Checkbox „Werkstatt-Zugang"
   - **API-User**: Checkbox „API-Zugriff"
   - (keine Checkbox = Community-User)
3. Speichern

> Jeder User kann nur **eine** Rolle haben. Wenn mehrere Checkboxen gewählt werden, gilt die Prioritätsreihenfolge: Admin > Disponent > Werkstatt > API-User > Community.
