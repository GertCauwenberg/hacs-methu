"""Constants for the HungaroMet (met.hu) Forecast integration."""

DOMAIN = "methu_forecast"

CONF_SETTLEMENT = "settlement"       # user-visible settlement name (for display)
CONF_SETTLEMENT_NAME = "settlement_name"  # resolved canonical name from autocomplete
CONF_KOD = "kod"                    # met.hu settlement code
CONF_LAT = "lat"                    # latitude
CONF_LON = "lon"                    # longitude
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_SCAN_INTERVAL = 60  # minutes
MIN_SCAN_INTERVAL = 30

MAIN_PHP = "https://www.met.hu/idojaras/elorejelzes/magyarorszagi_telepulesek/main.php"
AC_PHP   = "https://www.met.hu/idojaras/elorejelzes/magyarorszagi_telepulesek/ac.php"

ATTR_SETTLEMENT = "settlement"
ATTR_FORECAST_TIME = "forecast_time"
ATTR_TEMPERATURE = "temperature"
ATTR_TEMPERATURE_MIN = "temperature_min"
ATTR_TEMPERATURE_MAX = "temperature_max"
ATTR_WEATHER_CONDITION = "weather_condition"
ATTR_PRECIPITATION = "precipitation"
ATTR_PRECIPITATION_PROBABILITY = "precipitation_probability"
ATTR_WIND_SPEED = "wind_speed"
ATTR_WIND_DIRECTION = "wind_direction"
ATTR_HUMIDITY = "humidity"

# Weather condition icon mapping (met.hu icon codes to HA conditions)
CONDITION_MAP = {
    "01": "sunny",          # clear sky day
    "02": "partlycloudy",   # few clouds day
    "03": "cloudy",         # scattered clouds
    "04": "cloudy",         # broken clouds
    "09": "rainy",          # shower rain
    "10": "rainy",          # rain
    "11": "lightning-rainy", # thunderstorm
    "13": "snowy",          # snow
    "50": "fog",            # mist/fog
    "n01": "clear-night",   # clear sky night
    "n02": "partlycloudy",  # few clouds night
}

SENSOR_TYPES = {
    "temperature": {
        "name": "Temperature",
        "unit": "°C",
        "icon": "mdi:thermometer",
        "device_class": "temperature",
        "state_class": "measurement",
    },
    "temperature_min": {
        "name": "Temperature Min",
        "unit": "°C",
        "icon": "mdi:thermometer-chevron-down",
        "device_class": "temperature",
        "state_class": "measurement",
    },
    "temperature_max": {
        "name": "Temperature Max",
        "unit": "°C",
        "icon": "mdi:thermometer-chevron-up",
        "device_class": "temperature",
        "state_class": "measurement",
    },
    "precipitation": {
        "name": "Precipitation",
        "unit": "mm",
        "icon": "mdi:weather-rainy",
        "device_class": None,
        "state_class": "measurement",
    },
    "precipitation_probability": {
        "name": "Precipitation Probability",
        "unit": "%",
        "icon": "mdi:water-percent",
        "device_class": None,
        "state_class": "measurement",
    },
    "wind_speed": {
        "name": "Wind Speed",
        "unit": "km/h",
        "icon": "mdi:weather-windy",
        "device_class": "wind_speed",
        "state_class": "measurement",
    },
    "wind_direction": {
        "name": "Wind Direction",
        "unit": None,
        "icon": "mdi:compass",
        "device_class": None,
        "state_class": None,
    },
    "weather_condition": {
        "name": "Weather Condition",
        "unit": None,
        "icon": "mdi:weather-partly-cloudy",
        "device_class": None,
        "state_class": None,
    },
}
