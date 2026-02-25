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
    UnitOfSpeed,
    UnitOfTemperature,
    UnitOfPrecipitationDepth,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SETTLEMENT, CONF_SETTLEMENT_NAME, DOMAIN
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
        key="precipitation_probability",
        name="Precipitation Probability",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
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
        key="wind_direction",
        name="Wind Direction",
        icon="mdi:compass",
    ),
    SensorEntityDescription(
        key="weather_condition",
        name="Weather Condition",
        icon="mdi:weather-partly-cloudy",
    ),
    SensorEntityDescription(
        key="weather_description",
        name="Weather Description",
        icon="mdi:weather-partly-cloudy",
    ),
    SensorEntityDescription(
        key="humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:water-percent",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities for the met.hu forecast."""
    coordinator: MetHuForecastCoordinator = hass.data[DOMAIN][entry.entry_id]
    settlement_name = coordinator.settlement.name

    entities = []
    for description in SENSOR_DESCRIPTIONS:
        entities.append(
            MetHuForecastSensor(
                coordinator=coordinator,
                entry=entry,
                description=description,
                settlement=settlement_name,
            )
        )

    async_add_entities(entities)


def _get_value_from_period(period: ForecastPeriod | None, key: str) -> Any:
    """Extract a value from a ForecastPeriod by attribute key."""
    if period is None:
        return None
    return getattr(period, key, None)


class MetHuForecastSensor(CoordinatorEntity[MetHuForecastCoordinator], SensorEntity):
    """Sensor entity representing a single met.hu forecast parameter."""

    entity_description: SensorEntityDescription

    def __init__(
        self,
        coordinator: MetHuForecastCoordinator,
        entry: ConfigEntry,
        description: SensorEntityDescription,
        settlement: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._settlement = settlement
        self._entry = entry

        slug = settlement.lower().replace(" ", "_").replace("-", "_")
        self._attr_unique_id = f"{DOMAIN}_{slug}_{description.key}"
        self._attr_name = f"{settlement} {description.name}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"HungaroMet: {settlement}",
            manufacturer="HungaroMet",
            model="met.hu Forecast",
            entry_type="service",
            configuration_url=f"https://www.met.hu/idojaras/elorejelzes/magyarorszagi_telepulesek/",
        )

    @property
    def native_value(self) -> Any:
        """Return the current sensor value."""
        if not self.coordinator.data:
            return None
        current: ForecastPeriod | None = self.coordinator.data.current
        return _get_value_from_period(current, self.entity_description.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes including the 6-hourly forecast."""
        attrs: dict[str, Any] = {
            "settlement": self._settlement,
        }

        if not self.coordinator.data:
            return attrs

        data: MetHuForecastData = self.coordinator.data
        key = self.entity_description.key

        # Add current period timestamp
        if data.current and data.current.forecast_time:
            attrs["forecast_time"] = data.current.forecast_time.isoformat()

        # Add the 6-hourly forecast as an attribute
        hourly_forecast = []
        for period in data.hourly[:24]:  # limit to 24 periods (~6 days)
            val = _get_value_from_period(period, key)
            if val is not None:
                entry: dict[str, Any] = {"value": val}
                if period.forecast_time:
                    entry["time"] = period.forecast_time.isoformat()
                hourly_forecast.append(entry)

        if hourly_forecast:
            attrs["hourly_forecast"] = hourly_forecast

        # Add daily summary
        daily_forecast = []
        for period in data.daily:
            val = _get_value_from_period(period, key)
            if val is not None:
                entry = {"value": val}
                if period.forecast_time:
                    entry["date"] = period.forecast_time.date().isoformat()
                daily_forecast.append(entry)

        if daily_forecast:
            attrs["daily_forecast"] = daily_forecast

        if data.last_updated:
            attrs["last_updated"] = data.last_updated.isoformat()

        return attrs

    @property
    def available(self) -> bool:
        """Return True if the coordinator has data."""
        return self.coordinator.last_update_success and self.coordinator.data is not None
