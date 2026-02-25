# HungaroMet (met.hu) Forecast - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that fetches weather forecast data from the Hungarian Meteorological Service ([met.hu](https://www.met.hu)) for any of the 3000+ Hungarian settlements.

## Features

- 🌡️ **Temperature** — current, min, and max
- 🌧️ **Precipitation** — amount (mm) and probability (%)
- 💨 **Wind speed** (km/h) and direction
- 💧 **Humidity** (%)
- ☁️ **Weather condition** — mapped to Home Assistant standard conditions
- 📅 **Hourly forecast** (6-hourly periods from met.hu)
- 📅 **Daily forecast** (aggregated from 6-hourly data)
- 🗺️ Full **Weather entity** with forecast support
- 🔧 Configurable **update interval**
- 🔄 Supports **Options flow** to change update interval without re-adding

## Installation

### Via HACS (recommended)

1. Open **HACS** in Home Assistant
2. Go to **Integrations**
3. Click the three-dot menu → **Custom repositories**
4. Add this repository URL and set category to **Integration**
5. Search for "HungaroMet" and click **Install**
6. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/methu_forecast/` folder to your Home Assistant `custom_components/` directory
2. Restart Home Assistant

## How it works

The integration uses two met.hu endpoints:

1. **Autocomplete** (`ac.php?term=<name>`) — resolves the settlement name to its internal identifiers: `kod` (settlement code), `lt` (latitude), `n` (longitude).
2. **Forecast** (`main.php` via HTTP POST) — submits `kod`, `lt`, `n`, `tel` and receives an HTML forecast table covering the next several days in 6-hourly periods.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **HungaroMet Forecast**
3. Enter the settlement name with correct Hungarian spelling (e.g. `Siófok`, `Pécs`, `Várpalota`, `Győr`)
4. Set the desired update interval (default: 60 minutes, minimum: 30 minutes)
5. The integration auto-resolves the name via met.hu's autocomplete API. If that fails, a fallback screen lets you enter the `kod`, latitude and longitude manually.

### Finding parameters manually (if auto-resolve fails)

1. Open [met.hu settlement forecast](https://www.met.hu/idojaras/elorejelzes/magyarorszagi_telepulesek/) in your browser
2. Open DevTools → **Network** tab → filter by `main.php`
3. Type your settlement name and select it from the dropdown
4. Look at the POST request payload — it contains `kod=`, `lt=`, `n=`, `tel=`

## Entities Created

For each configured settlement, the following entities are created:

| Entity | Type | Description |
|--------|------|-------------|
| `weather.hungaromet_{settlement}` | Weather | Full weather entity with daily & hourly forecast |
| `sensor.{settlement}_temperature` | Sensor | Current temperature (°C) |
| `sensor.{settlement}_temperature_min` | Sensor | Daily minimum temperature (°C) |
| `sensor.{settlement}_temperature_max` | Sensor | Daily maximum temperature (°C) |
| `sensor.{settlement}_precipitation` | Sensor | Precipitation amount (mm) |
| `sensor.{settlement}_precipitation_probability` | Sensor | Precipitation probability (%) |
| `sensor.{settlement}_wind_speed` | Sensor | Wind speed (km/h) |
| `sensor.{settlement}_wind_direction` | Sensor | Wind direction (N, NE, E, SE, S, SW, W, NW) |
| `sensor.{settlement}_weather_condition` | Sensor | HA weather condition string |
| `sensor.{settlement}_weather_description` | Sensor | Human-readable Hungarian description |
| `sensor.{settlement}_humidity` | Sensor | Relative humidity (%) |

### Forecast Attributes

Each sensor also includes `hourly_forecast` and `daily_forecast` as extra state attributes, which can be used in automations and Lovelace dashboards.

## Dashboard Example

```yaml
type: weather-forecast
entity: weather.hungaromet_budapest
forecast_type: daily
```

## Automation Example

```yaml
automation:
  - alias: "Rain alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.budapest_precipitation_probability
        above: 70
    action:
      - service: notify.mobile_app
        data:
          message: "Rain is likely in Budapest today!"
```

## Notes

- Data is sourced from the publicly available met.hu website. No API key is required.
- The integration scrapes the HTML forecast page, so if met.hu changes their website structure, the parser may need to be updated.
- The forecast is based on ECMWF model data, automatically generated without human intervention (as noted on met.hu).
- Updates are rate-limited to a minimum of 30 minutes to be respectful to the met.hu servers.

## Troubleshooting

**Settlement not found:** Make sure you use the exact name with correct Hungarian characters (á, é, í, ó, ö, ő, ú, ü, ű). Check the settlement at https://www.met.hu/idojaras/elorejelzes/magyarorszagi_telepulesek/

**No data / unavailable sensors:** Check the Home Assistant logs for errors. The met.hu website may be temporarily down or the page structure may have changed.

**Sensors show "unknown":** The first data fetch may not have extracted all values if the page structure differs from expected. Check the logs and file an issue with the raw HTML content.

## License

GNUv3 License — see [LICENSE](LICENSE) file.

## Credits

Weather data provided by [HungaroMet Magyar Meteorológiai Szolgáltató Nonprofit Zrt.](https://www.met.hu)
