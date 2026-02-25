"""Weather platform for HungaroMet (met.hu) Forecast."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfSpeed, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SETTLEMENT, DOMAIN
from .coordinator import MetHuForecastCoordinator
from .scraper import ForecastPeriod, MetHuForecastData

_LOGGER = logging.getLogger(__name__)

# Map internal condition strings to HA weather conditions
HA_CONDITION_MAP = {
    "sunny": "sunny",
    "clear-night": "clear-night",
    "partlycloudy": "partlycloudy",
    "cloudy": "cloudy",
    "fog": "fog",
    "rainy": "rainy",
    "snowy": "snowy",
    "lightning-rainy": "lightning-rainy",
    "pouring": "pouring",
    "windy": "windy",
    "windy-variant": "windy-variant",
    "hail": "hail",
    "snowy-rainy": "snowy-rainy",
    "exceptional": "exceptional",
    "unknown": "exceptional",
}


def _period_to_forecast(period: ForecastPeriod) -> Forecast:
    """Convert a ForecastPeriod to a HA Forecast dict."""
    fc: Forecast = {}

    if period.forecast_time:
        fc["datetime"] = period.forecast_time.isoformat()

    condition = period.weather_condition or "unknown"
    fc["condition"] = HA_CONDITION_MAP.get(condition, "exceptional")

    if period.temperature is not None:
        fc["temperature"] = period.temperature
    if period.temperature_min is not None:
        fc["templow"] = period.temperature_min
    if period.precipitation is not None:
        fc["precipitation"] = period.precipitation
    if period.precipitation_probability is not None:
        fc["precipitation_probability"] = period.precipitation_probability
    if period.wind_speed is not None:
        fc["wind_speed"] = period.wind_speed
    if period.wind_direction is not None:
        fc["wind_bearing"] = _direction_to_bearing(period.wind_direction)

    return fc


def _direction_to_bearing(direction: str | None) -> float | None:
    """Convert compass direction string to degrees."""
    if not direction:
        return None
    bearings = {
        "N": 0.0, "NNE": 22.5, "NE": 45.0, "ENE": 67.5,
        "E": 90.0, "ESE": 112.5, "SE": 135.0, "SSE": 157.5,
        "S": 180.0, "SSW": 202.5, "SW": 225.0, "WSW": 247.5,
        "W": 270.0, "WNW": 292.5, "NW": 315.0, "NNW": 337.5,
    }
    return bearings.get(direction.upper())


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the weather entity."""
    coordinator: MetHuForecastCoordinator = hass.data[DOMAIN][entry.entry_id]
    settlement_name = coordinator.settlement.name

    async_add_entities([MetHuWeatherEntity(coordinator, entry, settlement_name)])


class MetHuWeatherEntity(CoordinatorEntity[MetHuForecastCoordinator], WeatherEntity):
    """Weather entity for met.hu forecast."""

    _attr_attribution = "Weather data from HungaroMet (met.hu)"
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(
        self,
        coordinator: MetHuForecastCoordinator,
        entry: ConfigEntry,
        settlement: str,
    ) -> None:
        """Initialize the weather entity."""
        super().__init__(coordinator)
        self._settlement = settlement
        self._entry = entry

        self._attr_name = f"HungaroMet {settlement}"
        slug = settlement.lower().replace(" ", "_").replace("-", "_")
        self._attr_unique_id = f"{DOMAIN}_{slug}_weather"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"HungaroMet: {settlement}",
            manufacturer="HungaroMet",
            model="met.hu Forecast",
            entry_type="service",
            configuration_url="https://www.met.hu/idojaras/elorejelzes/magyarorszagi_telepulesek/",
        )

    @property
    def _data(self) -> MetHuForecastData | None:
        return self.coordinator.data

    @property
    def condition(self) -> str | None:
        """Return the current weather condition."""
        if not self._data or not self._data.current:
            return None
        cond = self._data.current.weather_condition or "unknown"
        return HA_CONDITION_MAP.get(cond, "exceptional")

    @property
    def native_temperature(self) -> float | None:
        """Return the current temperature."""
        if not self._data or not self._data.current:
            return None
        return self._data.current.temperature

    @property
    def native_wind_speed(self) -> float | None:
        """Return the current wind speed."""
        if not self._data or not self._data.current:
            return None
        return self._data.current.wind_speed

    @property
    def wind_bearing(self) -> float | str | None:
        """Return the wind bearing."""
        if not self._data or not self._data.current:
            return None
        return _direction_to_bearing(self._data.current.wind_direction)

    @property
    def native_precipitation(self) -> float | None:
        """Return the precipitation."""
        if not self._data or not self._data.current:
            return None
        return self._data.current.precipitation

    @property
    def humidity(self) -> int | None:
        """Return the humidity."""
        if not self._data or not self._data.current:
            return None
        return self._data.current.humidity

    @property
    def available(self) -> bool:
        """Return True if data is available."""
        return self.coordinator.last_update_success and self._data is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        attrs: dict[str, Any] = {"settlement": self._settlement}
        if self._data and self._data.last_updated:
            attrs["last_updated"] = self._data.last_updated.isoformat()
        if self._data and self._data.current and self._data.current.weather_description:
            attrs["weather_description_hu"] = self._data.current.weather_description
        return attrs

    async def async_forecast_daily(self) -> list[Forecast] | None:
        """Return the daily forecast."""
        if not self._data:
            return None
        return [_period_to_forecast(p) for p in self._data.daily]

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        """Return the hourly/6-hourly forecast."""
        if not self._data:
            return None
        return [_period_to_forecast(p) for p in self._data.hourly]
