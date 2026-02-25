"""Sensor platform for HungaroMet (met.hu) Forecast."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfPrecipitationDepth,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MetHuForecastCoordinator
from .scraper import ForecastPeriod, MetHuForecastData

_LOGGER = logging.getLogger(__name__)

SENSOR_DESCRIPTIONS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer",
    ),
    SensorEntityDescription(
        key="temperature_min",
        name="Temperature Min",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-chevron-down",
    ),
    SensorEntityDescription(
        key="temperature_max",
        name="Temperature Max",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:thermometer-chevron-up",
    ),
    SensorEntityDescription(
        key="precipitation",
        name="Precipitation",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-rainy",
    ),
    SensorEntityDescription(
        key="cloud_cover",
        name="Cloud Cover",
        native_unit_of_measurement=PERCENTAGE,
        device_class=None,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-cloudy",
    ),
    SensorEntityDescription(
        key="wind_speed",
        name="Wind Speed",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy",
    ),
    SensorEntityDescription(
        key="wind_gust",
        name="Wind Gust",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:weather-windy-variant",
    ),
    SensorEntityDescription(
        key="wind_bearing",
        name="Wind Bearing",
        native_unit_of_measurement="°",
        icon="mdi:compass",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="wind_direction",
        name="Wind Direction",
        icon="mdi:compass-rose",
    ),
    SensorEntityDescription(
        key="pressure",
        name="Pressure",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gauge",
    ),
    SensorEntityDescription(
        key="weather_condition",
        name="Weather Condition",
        icon="mdi:weather-partly-cloudy",
    ),
    SensorEntityDescription(
        key="weather_description",
        name="Weather Description",
        icon="mdi:text-short",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    coordinator: MetHuForecastCoordinator = hass.data[DOMAIN][entry.entry_id]
    settlement_name = coordinator.settlement.name

    async_add_entities(
        MetHuForecastSensor(coordinator, entry, description, settlement_name)
        for description in SENSOR_DESCRIPTIONS
    )


class MetHuForecastSensor(CoordinatorEntity[MetHuForecastCoordinator], SensorEntity):
    """A single met.hu forecast sensor."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MetHuForecastCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
        settlement: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._settlement = settlement

        slug = settlement.lower().replace(" ", "_").replace("-", "_")
        self._attr_unique_id = f"{DOMAIN}_{slug}_{description.key}"
        self._attr_name = f"{settlement} {description.name}"
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
    def native_value(self) -> Any:
        if not self.coordinator.data or not self.coordinator.data.current:
            return None
        return getattr(self.coordinator.data.current, self.entity_description.key, None)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {"settlement": self._settlement}
        data: MetHuForecastData | None = self.coordinator.data
        if not data:
            return attrs

        key = self.entity_description.key

        if data.current and data.current.forecast_time:
            attrs["forecast_time"] = data.current.forecast_time.isoformat()

        if data.hourly:
            attrs["hourly_forecast"] = [
                {
                    "time": p.forecast_time.isoformat() if p.forecast_time else None,
                    "value": getattr(p, key, None),
                }
                for p in data.hourly
                if getattr(p, key, None) is not None
            ]

        if data.daily:
            attrs["daily_forecast"] = [
                {
                    "date": p.forecast_time.date().isoformat() if p.forecast_time else None,
                    "value": getattr(p, key, None),
                }
                for p in data.daily
                if getattr(p, key, None) is not None
            ]

        if data.last_updated:
            attrs["last_updated"] = data.last_updated.isoformat()

        return attrs

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None
