# Checkmk for Home Assistant

[![Validate](https://github.com/Creepers1312/home-assistant_checkmk/actions/workflows/validate.yml/badge.svg)](https://github.com/Creepers1312/home-assistant_checkmk/actions/workflows/validate.yml)
[![hacs](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)

A custom [Home Assistant](https://www.home-assistant.io/) integration that
polls a [Checkmk](https://checkmk.com/) site through its REST API
(Checkmk 2.1+) and exposes hosts, services, and selected performance
metrics as Home Assistant entities.

## Features

- **Host entities** — one device per monitored host, with a status sensor
  (`up` / `down` / `unreachable`) and a host-level problem binary sensor
  ideal for "anything unhandled on this machine?" automations.
- **Service entities** — one status sensor per Checkmk service
  (`ok` / `warning` / `critical` / `unknown`). Mirrors Checkmk's service
  table: one row in Checkmk = one entity in Home Assistant.
- **Site-wide aggregates** — counters for hosts/services total, hosts
  down/unreachable, services warning/critical/unknown, and unhandled
  open problems, plus a single `Problems` binary sensor that's on while
  *any* unhandled problem exists anywhere.
- **Service performance metrics** — numeric values from Checkmk's perfdata
  (CPU load, filesystem usage, throughput, …) are parsed and exposed as
  separate sensors with HA-native units and device classes.
- **Host and service filters** — exclude noisy hosts (e.g. the Checkmk
  site itself) or self-monitoring services (`Check_MK*`, `NTP*`, …) using
  shell-style glob patterns in the options flow.
- **Write-back services** — `checkmk.acknowledge` and
  `checkmk.schedule_downtime` for use from automations or scripts.
- Configuration is fully UI-driven (config flow), including re-auth.
- Hosts and services are discovered automatically — new ones appear
  without restarting Home Assistant.

## Requirements

- Home Assistant 2024.12 or newer
- Checkmk 2.1 or newer with a reachable REST API
- A Checkmk user with an **Automation secret**

### Creating an automation user in Checkmk

1. **Setup → Users → Add user**
2. Create the user and generate an **Automation secret** under
   *Authentication*.
3. Assign a role with read access to the monitoring view (e.g. `monitor`).

## Installation

### Via HACS (recommended)

1. HACS → **Integrations** → top-right menu → **Custom repositories**
2. Add `https://github.com/Creepers1312/home-assistant_checkmk` with
   category **Integration**.
3. Search for "Checkmk", install, then restart Home Assistant.

### Manual

Copy the `custom_components/checkmk` folder into the `custom_components`
directory of your Home Assistant configuration and restart Home Assistant.

## Setup

1. **Settings → Devices & Services → Add Integration → Checkmk**
2. Fill in:

   | Field | Example |
   | --- | --- |
   | Site URL | `https://monitoring.example.com/mysite` |
   | Automation user | `automation` |
   | Automation secret | the secret generated in Checkmk |
   | Verify SSL certificate | leave on, unless your certificate is self-signed |

The site URL is the base URL **including the site name**, but without
`/check_mk/...`.

## Options

Open **Configure** on the integration to access:

- **Update interval (seconds)** — poll cadence. Default 60, minimum 15.
- **Create sensors for service performance metrics** — toggles the
  perfdata-derived metric sensors. Turn off if you only care about
  service status and not the underlying numbers.
- **Include hosts / Exclude hosts** — shell-style glob patterns, one
  per line, that limit which monitored hosts the integration exposes.
  Empty include = include everything; excludes always win over includes.
- **Include services / Exclude services** — same, applied to service
  descriptions.

Patterns use `*` (any chars), `?` (one char), and `[abc]` (a character
from the set). They are case-sensitive — Checkmk's own naming is too.

> **Heads up:** existing entities for hosts/services that no longer
> match a filter stay in the entity registry as **unavailable** until
> you remove them manually (Settings → Devices & Services → entity →
> Delete). Home Assistant does not auto-delete entities, even on a
> breaking change.

### How entities are laid out on a device

Each monitored host becomes its own Home Assistant device. Below the
device, entities are split into two visibility tiers to keep the page
usable on hosts with hundreds of perfdata metrics:

| Tier | Section | Default | Examples |
| --- | --- | --- | --- |
| **Primary** | "Sensors" | enabled | host `Status`, host `Problem`, **every Checkmk service** (state enum), plus the highest-signal metrics: `util`, `mem_used_percent`, `fs_used_percent`, `load1`, interface `in` / `out`, `uptime`, `mem_used`, `fs_used` |
| **Diagnostic (visible)** | "Diagnostic" | enabled | a small set of secondary metrics that primary doesn't cover: `disk_read_throughput`, `disk_write_throughput`, `disk_latency`, `disk_utilization`, `mem_available`, `swap_used`, `pagefile_used_percent` |
| **Diagnostic (hidden)** | "Diagnostic" | disabled | the long tail — memory submetrics (`zswap`, `dirty`, …), kernel counters, TCP state breakdown, interface packet counters, etc. |

Hidden entities still exist in the entity registry — you can enable
individual ones under **Settings → Devices & Services → Entities**
(filter "Status: Disabled").

### Reducing entity count

Even with the trimmed tiers, a typical Linux host in Checkmk can show
up with 150+ entities in Home Assistant — most of them disabled
hidden-tier metric sensors. Those don't poll, don't write to the
recorder, and don't drive automations, so they cost effectively
nothing at runtime. They do show up in selectors and the registry
count, though, which can feel noisy.

If you want a smaller registry, the highest-impact moves are:

- **Exclude the Checkmk site host itself.** Checkmk monitors its own
  server extensively (Apache, Postfix queue, all site components).
  In most cases you don't need any of that in Home Assistant. Add the
  hostname (often `localhost`) to **Exclude hosts**.
- **Exclude noisy self-monitoring services.** A reasonable starter
  pattern set for **Exclude services**:
  ```
  Check_MK*
  NTP*
  Kernel*
  TCP Connections
  Mount options of *
  Systemd Service Summary
  Systemd Socket Summary
  ```
- **Turn off perfdata sensors entirely** by unchecking *Create sensors
  for service performance metrics*. You keep host/service status but
  lose the numeric graphs.

### Cleaning up leftover entities

Whenever you change host/service filters, toggle the perfdata-sensor
option, or upgrade across a tier-default change, Home Assistant
leaves the old entities in the registry as **"unavailable"** instead
of deleting them. This is HA's standard behavior for every
integration — it protects automations from being silently broken if a
device disappears for a moment.

Same thing happens if Checkmk itself stops reporting a metric you
used to see (plugin update, service renamed, host removed from the
Checkmk site): the entity that used to back it stays in the registry,
showing "unavailable" with the source-missing icon.

Two ways to clean it up:

- **Per entity** — Settings → Devices & Services → device → click the
  unavailable entity → gear icon → *Delete*. Fine for a handful of
  leftovers.
- **Full reset** — Settings → Devices & Services → Checkmk → ⋮ →
  *Delete*, then re-add the integration with the same site URL and
  credentials and re-enter your filters. The fresh discovery only
  creates entities that match the *current* tier defaults and your
  *current* filters. Fastest way back to a minimal registry after a
  big filter change or a major-version upgrade.

The integration deliberately does **not** delete entities on its own.
A short Checkmk outage would otherwise wipe configured automations,
which would feel much worse than a few "unavailable" badges.

### Upgrading

Home Assistant applies new visibility defaults only to *newly
discovered* entities. If you want the post-upgrade layout to take
effect on a host that already had entities in an earlier version,
remove and re-add the integration (see *Cleaning up leftover entities*
above) — or selectively delete the entities you don't want via the
entity registry.

**v0.4.0 specifically** dropped the per-service `*_problem` binary
sensors (one entity per Checkmk service is enough — `state != "ok"`
already encodes "problem", and ack/downtime are exposed as attributes).
Automations triggering on `binary_sensor.<host>_<service>_problem` must
switch to either the service status sensor (`state != "ok"`) or the
host-level `binary_sensor.<host>_problem`. The old binary sensors stay
in the registry as **unavailable** until you remove them — easiest via
the full reset above.

## Services

The integration registers two services that you can call from
automations or via the **Developer Tools → Services** UI:

### `checkmk.acknowledge`

Acknowledges a host or service problem in Checkmk.

```yaml
service: checkmk.acknowledge
data:
  host: db01
  service: CPU load     # omit to acknowledge the host itself
  comment: "investigating"
```

### `checkmk.schedule_downtime`

Schedules a fixed downtime. Provide either `end_time` or `duration`
(in minutes, default 60) — not both.

```yaml
service: checkmk.schedule_downtime
data:
  host: db01
  services: ["CPU load", "Memory"]   # omit for a host-level downtime
  duration: 30
  comment: "maintenance"
```

If multiple Checkmk integrations are configured, also pass
`config_entry_id` to disambiguate.

> **Note:** A "reschedule check" service is intentionally not provided —
> Checkmk's REST API does not expose that action (it lives in the web UI
> and Livestatus only). To get fresher data, shorten the **Update
> interval** in the options flow.

## How it works

The integration polls two REST endpoints on each update cycle:

- `GET /domain-types/host/collections/all` — state of all hosts
- `GET /domain-types/service/collections/all` — state of all services

Authentication uses the `Authorization: Bearer <user> <secret>` header.
The write-back services (acknowledge, downtime) call the corresponding
`POST` endpoints. The integration is `iot_class: local_polling` — by
default it only reads; writes happen exclusively when you explicitly
call one of the services.

Filtering is applied inside the data update coordinator, *before* any
entity is created. Both the per-service entities and the site-wide
summary counters always reflect the filtered view.

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| `invalid_auth` | Wrong username or secret, or the user has no monitoring access |
| `cannot_connect` | Wrong URL or port, firewall, or SSL verification failing |
| No entities | Check that the user can see the monitoring view in Checkmk |

Enable detailed logs in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.checkmk: debug
```

Diagnostics can be downloaded from the integration page (the secret is
redacted automatically).

## Local development with Docker

The repo ships a [`docker-compose.yml`](docker-compose.yml) that starts
a Home Assistant container and a Checkmk Raw Edition container side by
side. The `custom_components/checkmk` folder is bind-mounted into the
HA container, so code edits take effect after a single HA restart.

```bash
docker compose up -d
```

This creates a `./config/` directory for the HA state (covered by
`.gitignore`). Both containers need about 30 seconds for the first start.

### Initialise the Checkmk site

1. Open <http://localhost:5000/cmk> and log in as `cmkadmin` /
   `cmkadminpw` (see `CMK_PASSWORD` in the compose file).
2. **Setup → Users → Add user**, create a user `automation`.
3. Under *Authentication*, generate an **Automation secret** and copy
   it. Give the user the role `monitor` (or higher).
4. Click **Activate pending changes** in the top-right.
5. Optionally, **Setup → Hosts → Add host** and run a service discovery
   so you have something to monitor.

### Configure the integration in Home Assistant

1. Open <http://localhost:8123> and walk through HA's onboarding.
2. **Settings → Devices & Services → Add Integration → Checkmk**.
3. Fill in:
   - Site URL: `http://checkmk:5000/cmk` (compose-internal hostname,
     **not** `localhost`)
   - Automation user: `automation`
   - Automation secret: the secret you just generated
4. After saving, the hub, host, and service entities appear.

### Useful commands

| Purpose | Command |
| --- | --- |
| Tail integration logs | `docker logs -f ha-checkmk-dev` |
| Reload HA after a code change | `docker restart ha-checkmk-dev` |
| Stop the stack | `docker compose down` |
| Stop and wipe state | `docker compose down -v && rm -rf config` |

## Disclaimer

This is an unofficial community project, not affiliated with Checkmk
GmbH. "Checkmk" is a trademark of its respective owners.

## License

[MIT](LICENSE)
