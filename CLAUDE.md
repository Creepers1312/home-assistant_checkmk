# Project standards for `home-assistant_checkmk`

A Home Assistant custom integration that polls the Checkmk REST API and
exposes hosts, services, performance metrics and a few write-back service
calls (acknowledge / downtime / recheck).

## Repository layout

```
custom_components/checkmk/
  __init__.py            # async_setup_entry, platform forwarding, service registration
  api.py                 # async wrapper around the Checkmk REST API (aiohttp)
  binary_sensor.py       # site-wide + per-host/service problem sensors
  config_flow.py         # user / reauth / options flows
  const.py
  coordinator.py         # DataUpdateCoordinator, hosts + services fetched in parallel
  diagnostics.py
  manifest.json
  parsing.py             # HA-free helpers (parse_perf_data, is_problem) - testable in isolation
  sensor.py              # summary + host status + service status + metric sensors
  metrics.py             # METRIC_SPECS catalog: perfdata metric name -> HA unit + device_class + state_class
  services.py            # checkmk.acknowledge / schedule_downtime
  services.yaml
  strings.json           # source of truth for translations - copy verbatim to translations/en.json
  translations/
    de.json
    en.json
  brand/                 # icon.png + icon@2x.png + logo.png + logo@2x.png (HACS reads from here)
tests/
  conftest.py            # pulls in pytest-homeassistant-custom-component + enable_custom_integrations autouse
  test_api.py            # mocked aiohttp session
  test_binary_sensor.py  # (planned)
  test_config_flow.py    # uses the real hass fixture
  test_parsing.py        # pure unit tests, no HA dependency
  test_services.py       # registers services through a MockConfigEntry, asserts API calls
docker-compose.yml       # HA + Checkmk Raw Edition for live local testing
.github/workflows/validate.yml
hacs.json
```

## Code conventions

- Python 3.13+, `from __future__ import annotations` at the top of every module.
- Type hints on every public function. `dict[...]`/`list[...]` style, no `Dict`/`List`.
- Pure helpers (parsing, math, transformation) live in `parsing.py`. **No HA imports.** This is what lets the unit tests run without the heavy HA stack.
- Comments only when *why* is non-obvious. Default to none.
- One `_LOGGER = logging.getLogger(__name__)` per module that logs.
- Coordinator + Entity pattern from HA. Discovery callback on the coordinator adds new entities as hosts/services appear in Checkmk - no restart needed.

## Home Assistant gotchas (we have actually hit these)

- **Brand assets**: lives in `custom_components/<domain>/brand/{icon,icon@2x,logo,logo@2x}.png`. HACS validates the path; HA 2026.3+ serves the same files via the Brands Proxy API for any UI surface that uses it. **Do not** open a PR against `home-assistant/brands` for a custom integration - the repo's bot auto-closes those PRs (policy change with HA 2026.3, see [the announcement](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api/)). The HACS update dialog may still show "icon not available" because HACS hasn't switched to the proxy URL yet; that's a HACS-side issue, no code change on our side can fix it.
- **Translations**: hassfest rejects URLs inside `data_description` values. Write `"Base URL of the Checkmk site, including the site name path"` instead of `"e.g. https://..."`. Examples with URLs belong in the README.
- **Tests**: every test that uses the `hass` fixture also needs `enable_custom_integrations`. Conftest applies it autouse - do not remove it, every config-flow test will die with `IntegrationNotFound`.
- **Service registration** lives in `async_setup_entry` and uses `hass.services.has_service` to be idempotent across reloads. Do not unregister on unload - HA keeps services registered for the life of the integration install.
- **Orphan services**: Checkmk sometimes returns a service for a host that didn't appear in the host endpoint. `binary_sensor._discover` / `sensor._discover` build `host_names` from both sources so `via_device` always resolves.
- **404 on the API root** = wrong site URL, not "unknown error". `api._request` maps it to `CheckmkConnectionError` so the config flow can surface `cannot_connect`.
- **No `reschedule_check` service.** Checkmk's REST API does not expose reschedule_check anywhere (verified against the `/openapi-swagger-ui.json` of a 2.4 site - it lives only in the Web UI / Livestatus). Do not re-add it. If a user needs fresher data, shorten the scan interval in the options flow.
- **Perfdata units are mostly missing.** Checkmk's `perf_data` field only carries the value, almost never the unit - the units live in a separate internal registry. `metrics.py` (`METRIC_SPECS`) maps the common metric names to the right HA unit + device class. Add new entries there when you spot a metric showing up as a raw number in the UI.
- **Host/service include + exclude filters** (`config_flow` options → `coordinator`): four multiline glob-pattern fields (`host_include`, `host_exclude`, `service_include`, `service_exclude`) live in the options flow and are applied inside `CheckmkCoordinator._async_update_data` *before* the data reaches any entity, so the discovery callbacks and the summary counters all see the same filtered view. Matching uses `fnmatchcase` - case-sensitive shell globs (`*`, `?`, `[abc]`). Empty include = include everything; excludes always win. The host filter is also enforced when filtering services so an excluded host cannot leak in through its services. Pure helpers live in `parsing.parse_pattern_list` / `parsing.matches_filter`. **Existing entities for now-filtered-out hosts/services do not auto-delete** - they go unavailable in the registry until the user removes them; that's standard HA behavior and is called out in the options-flow description.
- **Entity model mirrors Checkmk's service table**: one row in Checkmk = one entity in HA. Per service we emit a single `CheckmkServiceSensor` (enum sensor: `ok` / `warning` / `critical` / `unknown`), and the plugin-output / ack / downtime state lives in its attributes - the same data Checkmk shows in the "Summary" column. We **do not** create a parallel service-problem binary sensor (it was redundant with the enum's `state != "ok"` check). Host- and site-level `BinarySensorDeviceClass.PROBLEM` sensors are still around because aggregate triggers in HA automations benefit from them.
- **Metric-sensor visibility tiers** (`metrics.visibility_for(name)`): perfdata can still explode into hundreds of values per host, so the per-metric sensors are split into:
  - **Primary** (no `entity_category`, enabled): the ~9 highest-value metrics (`util`, `mem_used_percent`, `fs_used_percent`, `load1`, `in`, `out`, `uptime`, `mem_used`, `fs_used`).
  - **Diagnostic visible** (`EntityCategory.DIAGNOSTIC`, enabled): secondary metrics (`mem_free`, `disk_*_throughput`, TCP `ESTABLISHED/LISTEN/TIME_WAIT`, ...).
  - **Diagnostic hidden** (`EntityCategory.DIAGNOSTIC`, disabled): the long tail of Linux/kernel/per-packet counters - present in the registry so a curious user can enable individually, but invisible by default.
  Unknown metric names default to the hidden tier - safer than dumping arbitrary perfdata into the dashboard. **Important caveat:** entity-registry `enabled_default` only kicks in for *newly discovered* entities. Existing entities keep whatever state the user had after a version bump - tell affected users to remove + re-add the integration if they want the new defaults. Same applies to the service-problem binary sensors removed in 0.4.0: existing ones stay as "unavailable" until manually deleted.

## Release workflow

1. Bump `"version"` in `custom_components/checkmk/manifest.json`.
2. Commit: `chore: bump to X.Y.Z`.
3. Tag: `git tag -a vX.Y.Z -m "vX.Y.Z - short summary"`.
4. Push both: `git push && git push origin vX.Y.Z`.
5. On GitHub: **Releases → Draft a new release → Choose tag vX.Y.Z**, use the auto-generated notes. HACS surfaces the release as an update inside Home Assistant.

## CI requirements (all three jobs must be green)

- **Hassfest** (`home-assistant/actions/hassfest`): manifest + translations validation.
- **HACS** (`hacs/action`): repo + manifest + brand assets + topics.
- **Tests** (`pytest`): runs the suite under Python 3.13 with `pytest-homeassistant-custom-component`.

GitHub repo settings: topics must include `home-assistant`, `hacs`, `integration`, `checkmk`, `monitoring`. Without them the HACS topics check fails.

## Local dev with Docker

```bash
docker compose up -d
# Home Assistant: http://localhost:8123
# Checkmk:        http://localhost:5000/cmk  (cmkadmin / cmkadminpw)
docker restart ha-checkmk-dev    # after a code change
docker compose down              # stop
docker compose down -v && rm -rf config  # nuke state
```

Bind mount on `./custom_components:/config/custom_components` means edits are picked up on the next HA restart - no rebuild needed.

For Checkmk: create an automation user (Setup → Users → Add user, generate Automation secret), then in HA use URL `http://checkmk:5000/cmk` (compose-internal hostname, *not* `localhost`).

## Testing patterns

- Pure logic (perfdata parsing, problem detection): import from `custom_components.checkmk.parsing`, no fixtures needed.
- API client: mock `aiohttp.ClientSession` with `unittest.mock.AsyncMock`; assert on `session.request.call_args` to verify HTTP method, URL, headers and JSON body.
- Config flow: drive `hass.config_entries.flow.async_init` / `async_configure`, patch `CheckmkClient.async_validate` with `AsyncMock` to simulate success / failure modes.
- Services: stage a `MockConfigEntry`, patch `custom_components.checkmk.CheckmkClient` so `async_setup_entry` instantiates the mock, then call `hass.services.async_call(DOMAIN, "...", {...}, blocking=True)` and assert on the mock.
