"""The HungaroMet (met.hu) Forecast integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    CONF_KOD,
    CONF_LAT,
    CONF_LON,
    CONF_SCAN_INTERVAL,
    CONF_SETTLEMENT,
    CONF_SETTLEMENT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import MetHuForecastCoordinator
from .scraper import Settlement

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "weather"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up HungaroMet Forecast from a config entry."""
    # Reconstruct the Settlement object from stored config data
    settlement = Settlement(
        name=entry.data.get(CONF_SETTLEMENT_NAME) or entry.data[CONF_SETTLEMENT],
        kod=entry.data[CONF_KOD],
        lat=float(entry.data[CONF_LAT]),
        lon=float(entry.data[CONF_LON]),
    )

    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL,
        entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    )

    coordinator = MetHuForecastCoordinator(hass, settlement, scan_interval)

    await coordinator.async_config_entry_first_refresh()

    if not coordinator.data:
        raise ConfigEntryNotReady(
            f"Could not fetch initial forecast data for '{settlement.name}'"
        )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update → reload."""
    await hass.config_entries.async_reload(entry.entry_id)
