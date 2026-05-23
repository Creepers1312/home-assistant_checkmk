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

- **Brand assets**: HACS looks for `custom_components/<domain>/brand/icon.png`, *not* the integration root. HA core 2026.3+ also reads them from this `brand/` subdirectory.
- **Translations**: hassfest rejects URLs inside `data_description` values. Write `"Base URL of the Checkmk site, including the site name path"` instead of `"e.g. https://..."`. Examples with URLs belong in the README.
- **Tests**: every test that uses the `hass` fixture also needs `enable_custom_integrations`. Conftest applies it autouse - do not remove it, every config-flow test will die with `IntegrationNotFound`.
- **Service registration** lives in `async_setup_entry` and uses `hass.services.has_service` to be idempotent across reloads. Do not unregister on unload - HA keeps services registered for the life of the integration install.
- **Orphan services**: Checkmk sometimes returns a service for a host that didn't appear in the host endpoint. `binary_sensor._discover` / `sensor._discover` build `host_names` from both sources so `via_device` always resolves.
- **404 on the API root** = wrong site URL, not "unknown error". `api._request` maps it to `CheckmkConnectionError` so the config flow can surface `cannot_connect`.
- **No `reschedule_check` service.** Checkmk's REST API does not expose reschedule_check anywhere (verified against the `/openapi-swagger-ui.json` of a 2.4 site - it lives only in the Web UI / Livestatus). Do not re-add it. If a user needs fresher data, shorten the scan interval in the options flow.
- **Perfdata units are mostly missing.** Checkmk's `perf_data` field only carries the value, almost never the unit - the units live in a separate internal registry. `metrics.py` (`METRIC_SPECS`) maps the common metric names to the right HA unit + device class. Add new entries there when you spot a metric showing up as a raw number in the UI.

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
