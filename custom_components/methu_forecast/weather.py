"""Weather platform for HungaroMet (met.hu) Forecast."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MetHuForecastCoordinator
from .scraper import ForecastPeriod, MetHuForecastData

_LOGGER = logging.getLogger(__name__)

# Our internal condition strings are already valid HA condition strings
# (sunny, partlycloudy, cloudy, rainy, snowy, etc.) — pass through directly.
VALID_HA_CONDITIONS = {
    "clear-night", "cloudy", "exceptional", "fog", "hail", "lightning",
    "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
    "snowy-rainy", "sunny", "windy", "windy-variant",
}


def _to_ha_condition(condition: str | None) -> str | None:
    if condition in VALID_HA_CONDITIONS:
        return condition
    return "exceptional"


def _period_to_forecast(p: ForecastPeriod) -> Forecast:
    fc: Forecast = {}
    if p.forecast_time:
        fc["datetime"] = p.forecast_time.isoformat()
    fc["condition"] = _to_ha_condition(p.weather_condition)
    if p.temperature is not None:
        fc["temperature"] = p.temperature
    if p.temperature_min is not None:
        fc["templow"] = p.temperature_min
    if p.precipitation is not None:
        fc["precipitation"] = p.precipitation
    if p.wind_speed is not None:
        fc["wind_speed"] = p.wind_speed
    if p.wind_bearing is not None:
        fc["wind_bearing"] = p.wind_bearing
    if p.cloud_cover is not None:
        fc["cloud_coverage"] = p.cloud_cover
    if p.pressure is not None:
        fc["pressure"] = p.pressure
    return fc


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MetHuForecastCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [MetHuWeatherEntity(coordinator, entry, coordinator.settlement.name)]
    )


class MetHuWeatherEntity(CoordinatorEntity[MetHuForecastCoordinator], WeatherEntity):
    """Weather entity backed by met.hu forecast data."""

    _attr_attribution = "Weather data © HungaroMet (met.hu)"
    _attr_native_temperature_unit      = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit    = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit       = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_pressure_unit         = UnitOfPressure.HPA
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(
        self,
        coordinator: MetHuForecastCoordinator,
        entry: ConfigEntry,
        settlement: str,
    ) -> None:
        super().__init__(coordinator)
        self._settlement = settlement
        slug = settlement.lower().replace(" ", "_").replace("-", "_")
        self._attr_unique_id = f"{DOMAIN}_{slug}_weather"
        self._attr_name = f"HungaroMet {settlement}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"HungaroMet: {settlement}",
            manufacturer="HungaroMet",
            model="met.hu Forecast",
            entry_type="service",
            configuration_url=(
                "https://www.met.hu/idojaras/elorejelzes/magyarorszagi_telepulesek/"
            ),
        )

    @property
    def _current(self) -> ForecastPeriod | None:
        return self.coordinator.data.current if self.coordinator.data else None

    @property
    def condition(self) -> str | None:
        return _to_ha_condition(self._current.weather_condition if self._current else None)

    @property
    def native_temperature(self) -> float | None:
        return self._current.temperature if self._current else None

    @property
    def native_wind_speed(self) -> float | None:
        return self._current.wind_speed if self._current else None

    @property
    def wind_bearing(self) -> float | None:
        return self._current.wind_bearing if self._current else None

    @property
    def native_precipitation(self) -> float | None:
        return self._current.precipitation if self._current else None

    @property
    def cloud_coverage(self) -> int | None:
        return self._current.cloud_cover if self._current else None

    @property
    def native_pressure(self) -> float | None:
        return self._current.pressure if self._current else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"settlement": self._settlement}
        if self.coordinator.data and self.coordinator.data.last_updated:
            attrs["last_updated"] = self.coordinator.data.last_updated.isoformat()
        if self._current and self._current.weather_description:
            attrs["weather_description_hu"] = self._current.weather_description
        if self._current and self._current.wind_gust is not None:
            attrs["wind_gust_kmh"] = self._current.wind_gust
        if self._current and self._current.wind_direction:
            attrs["wind_direction"] = self._current.wind_direction
        return attrs

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    async def async_forecast_daily(self) -> list[Forecast] | None:
        if not self.coordinator.data:
            return None
        return [_period_to_forecast(p) for p in self.coordinator.data.daily]

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        if not self.coordinator.data:
            return None
        return [_period_to_forecast(p) for p in self.coordinator.data.hourly]
