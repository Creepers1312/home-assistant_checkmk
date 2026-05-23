# Checkmk für Home Assistant

[![Validate](https://github.com/Creepers1312/home-assistant_checkmk/actions/workflows/validate.yml/badge.svg)](https://github.com/Creepers1312/home-assistant_checkmk/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)

Eine benutzerdefinierte [Home Assistant](https://www.home-assistant.io/)-Integration,
die Monitoring-Daten aus [Checkmk](https://checkmk.com/) über die REST API
(Checkmk 2.1+) abfragt und als Sensoren bereitstellt.

## Funktionen

- **Host-Status** – ein Sensor pro überwachtem Host (`up` / `down` / `unreachable`)
- **Service-Status** – ein Sensor pro Service (`ok` / `warning` / `critical` / `unknown`)
- **Binary Sensors** – `problem` pro Host und pro Service sowie ein
  site-weiter `has_problems`-Sensor – ideal für Automationen
- **Zusammenfassung** – site-weite Zähler: Hosts/Services gesamt, Hosts down/unreachable,
  Services warning/critical/unknown sowie offene (unbestätigte) Probleme
- **Service-Metriken** – numerische Performance-Werte (z. B. CPU-Last, Temperatur,
  Füllstände) werden aus den Checkmk-Perfdaten geparst und als eigene Sensoren angelegt
- **Services** – `checkmk.acknowledge` und `checkmk.schedule_downtime`
  für Automationen und Skripte
- Konfiguration vollständig über die Oberfläche (Config Flow), inkl. Re-Auth
- Hosts und Services werden automatisch erkannt – neue Objekte erscheinen ohne Neustart
- Jeder Host wird als eigenes Gerät dargestellt; seine Services hängen daran

## Voraussetzungen

- Home Assistant 2024.12 oder neuer
- Checkmk 2.1 oder neuer mit erreichbarer REST API
- Ein Checkmk-Benutzer mit **Automation Secret**

### Automationsbenutzer in Checkmk anlegen

1. In Checkmk: **Setup → Users → Add user**
2. Einen Benutzer anlegen und unter *Authentication* ein **Automation secret** erzeugen
3. Dem Benutzer eine Rolle mit Leserechten auf das Monitoring geben (z. B. `monitor`)

## Installation

### Über HACS (empfohlen)

1. HACS → **Integrationen** → Menü oben rechts → **Benutzerdefinierte Repositories**
2. Repository `https://github.com/Creepers1312/home-assistant_checkmk`
   mit Kategorie **Integration** hinzufügen
3. „Checkmk" suchen, installieren und Home Assistant neu starten

### Manuell

Den Ordner `custom_components/checkmk` in das `custom_components`-Verzeichnis
deiner Home-Assistant-Konfiguration kopieren und Home Assistant neu starten.

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Checkmk**
2. Felder ausfüllen:
   | Feld | Beispiel |
   | --- | --- |
   | Site-URL | `https://monitoring.example.com/mysite` |
   | Automationsbenutzer | `automation` |
   | Automations-Secret | das in Checkmk erzeugte Secret |
   | SSL-Zertifikat prüfen | aktiviert lassen, außer bei selbstsignierten Zertifikaten |

Die Site-URL ist die Basis-URL **inklusive Site-Namen**, aber ohne `/check_mk/...`.

## Optionen

Über **Konfigurieren** an der Integration:

- **Aktualisierungsintervall** – Abfrageintervall in Sekunden (Standard 60, Minimum 15)
- **Sensoren für Service-Performance-Metriken erstellen** – legt fest, ob aus den
  Checkmk-Perfdaten zusätzliche numerische Sensoren erzeugt werden

> **Hinweis:** Große Checkmk-Installationen haben sehr viele Services und Metriken.
> Bei Performance-Problemen das Metrik-Feature deaktivieren oder das
> Aktualisierungsintervall erhöhen. Nicht benötigte Sensoren lassen sich in
> Home Assistant deaktivieren.

## Services

Die Integration registriert drei Services, die per Automation oder im
Entwicklerwerkzeug aufgerufen werden können:

### `checkmk.acknowledge`

Bestätigt ein Host- oder Service-Problem.

```yaml
service: checkmk.acknowledge
data:
  host: db01
  service: CPU load     # weglassen, um den Host selbst zu bestätigen
  comment: "wird gerade untersucht"
```

### `checkmk.schedule_downtime`

Plant eine feste Downtime. Entweder `end_time` oder `duration` (in Minuten,
Standard 60) angeben – nicht beides.

```yaml
service: checkmk.schedule_downtime
data:
  host: db01
  services: ["CPU load", "Memory"]   # weglassen für eine Host-Downtime
  duration: 30
  comment: "Wartung"
```

Sind mehrere Checkmk-Integrationen konfiguriert, muss zusätzlich
`config_entry_id` angegeben werden.

> **Hinweis:** Ein „Reschedule check"-Service ist bewusst nicht enthalten —
> Checkmks REST API exponiert diese Funktion nicht (sie ist nur über die
> Weboberfläche oder Livestatus verfügbar). Bei Bedarf neue Daten lieber über
> ein kürzeres **Aktualisierungsintervall** in den Optionen ziehen.

## Wie es funktioniert

Die Integration ruft zyklisch die Monitoring-Endpunkte der Checkmk REST API ab:

- `GET /domain-types/host/collections/all` – Status aller Hosts
- `GET /domain-types/service/collections/all` – Status aller Services

Die Authentifizierung erfolgt per `Authorization: Bearer <user> <secret>`-Header.
Service-Aufrufe (Acknowledge, Downtime) verwenden zusätzlich die entsprechenden
`POST`-Endpunkte. Standard ist nur lesender Zugriff (`iot_class: local_polling`);
die schreibenden Aufrufe entstehen ausschließlich durch explizit aufgerufene
Services.

## Fehlerbehebung

| Problem | Ursache / Lösung |
| --- | --- |
| `invalid_auth` | Benutzername oder Secret falsch, oder Benutzer ohne Monitoring-Rechte |
| `cannot_connect` | URL/Port falsch, Firewall, oder SSL-Prüfung schlägt fehl |
| Keine Sensoren | Prüfen, ob der Benutzer das Monitoring sehen darf |

Detaillierte Logs aktivieren in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.checkmk: debug
```

Diagnosedaten lassen sich über die Integrationsseite herunterladen
(das Secret wird dabei geschwärzt).

## Lokal mit Docker testen

Im Repo liegt eine [`docker-compose.yml`](docker-compose.yml), die parallel
einen Home‑Assistant‑Container und eine Checkmk Raw Edition startet. Der
`custom_components/checkmk`‑Ordner wird live in den HA‑Container gemountet,
sodass Code‑Änderungen nach einem HA‑Neustart sofort wirken.

```bash
docker compose up -d
```

Das legt einen `./config/`‑Ordner für den HA‑State an (von `.gitignore`
abgedeckt). Beide Container brauchen beim ersten Start ~30 Sekunden.

### Checkmk-Site initialisieren

1. http://localhost:5000/cmk öffnen, einloggen als `cmkadmin` /
   `cmkadminpw` (siehe `CMK_PASSWORD` in der Compose‑Datei).
2. **Setup → Users → Add user** und einen Benutzer `automation` anlegen.
3. Unter *Authentication* ein **Automation secret** generieren und
   kopieren. Die Rolle `monitor` (oder höher) zuweisen.
4. Oben rechts **Activate pending changes** klicken.
5. Optional: damit überhaupt ein Host überwacht wird, **Setup → Hosts →
   Add host** ausführen und ein Service Discovery durchlaufen.

### Integration in Home Assistant einrichten

1. http://localhost:8123 öffnen und das HA‑Onboarding durchklicken.
2. **Einstellungen → Geräte & Dienste → Integration hinzufügen → Checkmk**.
3. Felder:
   - Site‑URL: `http://checkmk:5000/cmk` (über den compose‑internen Namen,
     nicht `localhost`)
   - Automationsbenutzer: `automation`
   - Automations‑Secret: das eben erzeugte Secret
4. Nach dem Speichern erscheinen die Hub‑, Host‑ und Service‑Geräte.

### Nützliche Befehle

| Zweck | Befehl |
| --- | --- |
| Logs der Integration | `docker logs -f ha-checkmk-dev` |
| HA nach Code‑Änderung neu laden | `docker restart ha-checkmk-dev` |
| Stack stoppen | `docker compose down` |
| Stack inkl. State löschen | `docker compose down -v && rm -rf config` |

## Haftungsausschluss

Dieses Projekt ist ein inoffizielles Community-Projekt und steht in keiner
Verbindung zur Checkmk GmbH. „Checkmk" ist eine Marke ihrer jeweiligen Inhaber.

## Lizenz

[MIT](LICENSE)
