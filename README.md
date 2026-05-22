# Checkmk für Home Assistant

[![Validate](https://github.com/Creepers1312/checkmk-homeassistant/actions/workflows/validate.yml/badge.svg)](https://github.com/Creepers1312/checkmk-homeassistant/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)

Eine benutzerdefinierte [Home Assistant](https://www.home-assistant.io/)-Integration,
die Monitoring-Daten aus [Checkmk](https://checkmk.com/) über die REST API
(Checkmk 2.1+) abfragt und als Sensoren bereitstellt.

## Funktionen

- **Host-Status** – ein Sensor pro überwachtem Host (`up` / `down` / `unreachable`)
- **Service-Status** – ein Sensor pro Service (`ok` / `warning` / `critical` / `unknown`)
- **Zusammenfassung** – site-weite Zähler: Hosts/Services gesamt, Hosts down/unreachable,
  Services warning/critical/unknown sowie offene (unbestätigte) Probleme
- **Service-Metriken** – numerische Performance-Werte (z. B. CPU-Last, Temperatur,
  Füllstände) werden aus den Checkmk-Perfdaten geparst und als eigene Sensoren angelegt
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
2. Repository `https://github.com/Creepers1312/checkmk-homeassistant`
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

## Wie es funktioniert

Die Integration ruft zyklisch die Monitoring-Endpunkte der Checkmk REST API ab:

- `GET /domain-types/host/collections/all` – Status aller Hosts
- `GET /domain-types/service/collections/all` – Status aller Services

Die Authentifizierung erfolgt per `Authorization: Bearer <user> <secret>`-Header.
Es werden ausschließlich lesende Anfragen gestellt (`iot_class: local_polling`).

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

## Haftungsausschluss

Dieses Projekt ist ein inoffizielles Community-Projekt und steht in keiner
Verbindung zur Checkmk GmbH. „Checkmk" ist eine Marke ihrer jeweiligen Inhaber.

## Lizenz

[MIT](LICENSE)
