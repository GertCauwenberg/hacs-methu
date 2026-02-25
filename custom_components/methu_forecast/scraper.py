"""Scraper for met.hu settlement weather forecast data.

The met.hu forecast page works as follows:
1. User types a settlement name into an autocomplete field.
2. The autocomplete queries an endpoint  returning
   JSON with {kod, lt, n, tel} for each matching settlement.
3. Selecting a settlement POSTs to main.php with:
     srctext=&valtozatlan=true&kod=<code>&lt=<lat>&n=<lon>&tel=<name>&kepid=
4. The server returns an HTML fragment with the forecast table, which is
   injected into the page via AJAX.

This module handles both the settlement lookup and the forecast fetch.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any

import aiohttp
from bs4 import BeautifulSoup, Tag

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://www.met.hu"
MAIN_PHP = f"{BASE_URL}/idojaras/elorejelzes/magyarorszagi_telepulesek/main.php"
# The autocomplete endpoint – jQuery UI autocomplete typically hits ?term=<query>
AC_URL = f"{BASE_URL}/jquery/search.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
    "Referer": f"{BASE_URL}/idojaras/elorejelzes/magyarorszagi_telepulesek/",
    "Origin": BASE_URL,
}

# Hungarian wind direction abbreviations → standard compass
WIND_DIR_MAP = {
    "É": "N", "ÉÉK": "NNE", "ÉK": "NE", "KÉK": "ENE",
    "K": "E", "KDK": "ESE", "DK": "SE", "DDK": "SSE",
    "D": "S", "DDNy": "SSW", "DNy": "SW", "NyDNy": "WSW",
    "Ny": "W", "NyÉNy": "WNW", "ÉNy": "NW", "ÉÉNy": "NNW",
    "szélcsend": "calm", "változó": "variable",
}

# met.hu icon filename codes → HA weather conditions
CONDITION_MAP = {
    "01": "sunny", "02": "partlycloudy", "03": "partlycloudy",
    "04": "cloudy", "05": "cloudy", "06": "rainy",
    "07": "rainy", "08": "pouring", "09": "lightning-rainy",
    "10": "snowy", "11": "snowy-rainy", "12": "fog",
    "13": "windy", "14": "hail",
    # Night variants
    "n01": "clear-night", "n02": "partlycloudy", "n03": "partlycloudy",
    "n04": "cloudy", "n05": "cloudy", "n06": "rainy",
    "n07": "rainy", "n08": "pouring", "n09": "lightning-rainy",
    "n10": "snowy", "n11": "snowy-rainy", "n12": "fog",
}


@dataclass
class Settlement:
    """A Hungarian settlement with its met.hu identifiers."""
    name: str
    kod: str
    lat: float
    lon: float


@dataclass
class ForecastPeriod:
    """A single 6-hourly forecast period."""
    forecast_time: datetime | None = None
    temperature: float | None = None
    temperature_min: float | None = None
    temperature_max: float | None = None
    weather_condition: str | None = None
    weather_description: str | None = None
    precipitation: float | None = None
    precipitation_probability: int | None = None
    wind_speed: float | None = None
    wind_direction: str | None = None
    humidity: int | None = None


@dataclass
class MetHuForecastData:
    """All scraped forecast data for a settlement."""
    settlement: str = ""
    settlement_found: bool = False
    current: ForecastPeriod | None = None
    hourly: list[ForecastPeriod] = field(default_factory=list)
    daily: list[ForecastPeriod] = field(default_factory=list)
    last_updated: datetime | None = None


# ---------------------------------------------------------------------------
# Settlement lookup
# ---------------------------------------------------------------------------

async def lookup_settlement(
    session: aiohttp.ClientSession, name: str
) -> Settlement | None:
    """
    Resolve a settlement name to its met.hu identifiers via the autocomplete API.

    Returns the first (best) match, or None if not found.
    """
    try:
        async with session.get(
            AC_URL,
            params={"term": name},
            headers=HEADERS,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            _LOGGER.debug("Autocomplete response for '%s': %s", name, data)
    except aiohttp.ClientError as exc:
        _LOGGER.error("Settlement lookup failed for '%s': %s", name, exc)
        raise
    except Exception as exc:
        _LOGGER.error("Unexpected error during settlement lookup for '%s': %s", name, exc)
        raise

    if not data or not isinstance(data, list):
        return None

    # The autocomplete returns a list of dicts.
    # Typical fields: {"label": "Siófok", "value": "Siófok",
    #                  "kod": "3078", "lt": "46.917", "n": "18.12"}
    # Try to find an exact or close match first.
    name_lower = name.lower().strip()
    for entry in data:
        entry_label = (entry.get("label") or entry.get("value") or entry.get("tel") or "").lower()
        if entry_label == name_lower:
            return _entry_to_settlement(entry)

    # Fall back to first result
    if data:
        return _entry_to_settlement(data[0])

    return None


def _entry_to_settlement(entry: dict) -> Settlement | None:
    """Convert an autocomplete JSON entry to a Settlement object."""
    try:
        name = entry.get("label") or entry.get("value") or entry.get("tel") or ""
        kod = str(entry.get("kod") or entry.get("id") or "")
        lat = float(entry.get("lt") or entry.get("lat") or 0)
        lon = float(entry.get("n") or entry.get("lon") or 0)
        if not kod:
            return None
        return Settlement(name=name, kod=kod, lat=lat, lon=lon)
    except (ValueError, TypeError) as exc:
        _LOGGER.warning("Could not parse settlement entry %s: %s", entry, exc)
        return None


# ---------------------------------------------------------------------------
# Forecast fetch & parse
# ---------------------------------------------------------------------------

async def fetch_forecast(
    session: aiohttp.ClientSession, settlement: Settlement
) -> MetHuForecastData:
    """
    POST to main.php and parse the returned HTML forecast fragment.

    POST body (application/x-www-form-urlencoded):
        srctext=&valtozatlan=true&kod=3078&lt=46.917&n=18.12&tel=Siófok&kepid=
    """
    payload = {
        "srctext": "",
        "valtozatlan": "true",
        "kod": settlement.kod,
        "lt": str(settlement.lat),
        "n": str(settlement.lon),
        "tel": settlement.name,
        "kepid": "",
    }

    _LOGGER.debug("POSTing forecast request for %s (kod=%s)", settlement.name, settlement.kod)

    try:
        async with session.post(
            MAIN_PHP,
            data=payload,
            headers={
                **HEADERS,
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            html = await resp.text(encoding="utf-8", errors="replace")
    except aiohttp.ClientError as exc:
        _LOGGER.error("Error fetching forecast for %s: %s", settlement.name, exc)
        raise

    _LOGGER.debug("Received %d bytes for %s", len(html), settlement.name)

    data = _parse_html(html, settlement.name)
    data.last_updated = datetime.now()
    return data


def _parse_html(html: str, settlement_name: str) -> MetHuForecastData:
    """Parse the forecast HTML fragment returned by main.php."""
    result = MetHuForecastData(settlement=settlement_name)
    soup = BeautifulSoup(html, "html.parser")

    # Sanity check — if the response is just "idojaras" or empty, nothing found
    text = soup.get_text(strip=True)
    if not text or text.lower() in ("idojaras", "időjárás"):
        _LOGGER.warning("Empty or placeholder response for '%s'", settlement_name)
        result.settlement_found = False
        return result

    # Find the main forecast table
    table = _find_forecast_table(soup)
    if table is None:
        _LOGGER.warning(
            "No forecast table found in response for '%s'. "
            "Page may have changed structure.",
            settlement_name,
        )
        result.settlement_found = False
        return result

    result.settlement_found = True
    periods = _parse_table(table)
    result.hourly = periods
    result.daily = _aggregate_daily(periods)
    result.current = periods[0] if periods else None

    return result


def _find_forecast_table(soup: BeautifulSoup) -> Tag | None:
    """Locate the main forecast data table in the HTML."""
    # Try by class names commonly used on met.hu
    for class_hint in ["tabl", "forecast", "elorejelzes", "pred"]:
        t = soup.find("table", class_=re.compile(class_hint, re.I))
        if t:
            return t

    # Fall back: any table containing temperature data
    for t in soup.find_all("table"):
        if re.search(r"°C|hőmérséklet|csapadék", t.get_text()):
            return t

    return None


def _parse_table(table: Tag) -> list[ForecastPeriod]:
    """
    Parse the met.hu forecast table.

    The table layout is typically:
      Row 0: date headers (spanning multiple columns, one per day)
      Row 1: time-of-day labels (00, 06, 12, 18 or éjjel/reggel/délben/este)
      Row 2: weather icons
      Row 3: temperature (°C)
      Row 4: precipitation (mm)
      Row 5: precipitation probability (%)
      Row 6: wind speed (km/h or m/s)
      Row 7: wind direction
      Row 8: humidity (%)   [optional]

    The first cell of each row is a label cell.
    """
    rows = table.find_all("tr")
    if not rows:
        return []

    # ---------- step 1: build the time axis ----------
    time_axis = _build_time_axis(rows)
    n = len(time_axis)
    if n == 0:
        _LOGGER.debug("Could not determine time axis; trying column-based fallback")
        return _parse_columns_fallback(rows)

    # ---------- step 2: classify rows ----------
    icon_cells: list[Tag] = []
    temp_cells: list[Tag] = []
    prec_cells: list[Tag] = []
    prob_cells: list[Tag] = []
    wind_cells: list[Tag] = []
    dir_cells:  list[Tag] = []
    hum_cells:  list[Tag] = []

    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(strip=True).lower()
        data_cells = cells[1:]  # skip the label cell

        # Icons
        if any(c.find("img") for c in data_cells):
            imgs = [c for c in data_cells if c.find("img")]
            if len(imgs) >= max(2, n // 2):
                icon_cells = data_cells
                continue

        row_text = row.get_text()

        # Temperature
        if re.search(r"hőmérséklet|temp", label) or (
            "°C" in row_text and not icon_cells and not temp_cells
        ):
            if re.search(r"-?\d", row_text):
                temp_cells = data_cells
            continue

        # Precipitation amount
        if re.search(r"csapadék(?!.*való)", label) or (
            "mm" in row_text and not prec_cells
            and "valószínűség" not in label
        ):
            if re.search(r"\d", row_text):
                prec_cells = data_cells
            continue

        # Precipitation probability
        if re.search(r"való|prob|%", label) or (
            "%" in row_text and not prob_cells
            and "szél" not in label and "nedv" not in label
        ):
            if re.search(r"\d", row_text):
                prob_cells = data_cells
            continue

        # Wind speed
        if re.search(r"szélseb|wind.?sp|km/h|m/s", label) or (
            re.search(r"km/h|m/s", row_text)
            and not wind_cells
            and "irány" not in label
        ):
            if re.search(r"\d", row_text):
                wind_cells = data_cells
            continue

        # Wind direction
        if re.search(r"szélirány|wind.?dir|irány", label):
            dir_cells = data_cells
            continue

        # Humidity
        if re.search(r"nedv|humid", label):
            if re.search(r"\d", row_text):
                hum_cells = data_cells
            continue

    # ---------- step 3: build period objects ----------
    periods = []
    for i, dt in enumerate(time_axis):
        p = ForecastPeriod(forecast_time=dt)

        # Condition from icon
        if icon_cells:
            data_col = _nth_data_cell(icon_cells, i)
            if data_col is not None:
                img = data_col.find("img")
                if img:
                    p.weather_condition = _icon_to_condition(
                        img.get("src", ""), img.get("alt", "")
                    )
                    p.weather_description = img.get("alt", "")

        p.temperature          = _cell_number(temp_cells,  i)
        p.precipitation        = _cell_number(prec_cells,  i)
        p.wind_speed           = _cell_number(wind_cells,  i)

        prob = _cell_number(prob_cells, i)
        if prob is not None:
            p.precipitation_probability = int(prob)

        hum = _cell_number(hum_cells, i)
        if hum is not None:
            p.humidity = int(hum)

        if dir_cells:
            dc = _nth_data_cell(dir_cells, i)
            if dc is not None:
                p.wind_direction = _parse_wind_dir(dc)

        periods.append(p)

    return periods


# ---------------------------------------------------------------------------
# Time-axis helpers
# ---------------------------------------------------------------------------

def _build_time_axis(rows: list[Tag]) -> list[datetime]:
    """
    Extract an ordered list of datetime objects from the date/time header rows.

    met.hu uses two header rows:
      - A "date" row with colspan'd cells like "2026. február 25."
      - A "time" row with cells like "00", "06", "12", "18" or
        "éjjel", "reggel", "délben", "este"
    """
    date_row: Tag | None = None
    time_row: Tag | None = None

    for row in rows:
        cells = row.find_all(["td", "th"])
        text = row.get_text()
        if date_row is None and _is_date_row(text, cells):
            date_row = row
        elif time_row is None and _is_time_row(text, cells):
            time_row = row
        if date_row and time_row:
            break

    if not time_row:
        return []

    # Build day sequence from date row
    day_sequence: list[date] = _expand_date_row(date_row) if date_row else []

    # Parse time cells (with colspan expansion)
    time_cells = time_row.find_all(["td", "th"])
    slots: list[datetime] = []
    day_idx = 0
    current_day = day_sequence[0] if day_sequence else date.today()

    for cell in time_cells:
        text = cell.get_text(strip=True)
        hour = _time_label_to_hour(text)
        if hour is None:
            continue

        # Detect day rollover
        if slots and hour <= (slots[-1].hour if slots[-1] else 24):
            day_idx += 1
            if day_idx < len(day_sequence):
                current_day = day_sequence[day_idx]
            else:
                from datetime import timedelta
                current_day = current_day + timedelta(days=1)

        colspan = int(cell.get("colspan", 1))
        try:
            dt = datetime(current_day.year, current_day.month, current_day.day, hour, 0)
        except ValueError:
            continue

        for _ in range(colspan):
            slots.append(dt)

    return slots


def _is_date_row(text: str, cells: list[Tag]) -> bool:
    HU_MONTHS = [
        "január", "február", "március", "április", "május", "június",
        "július", "augusztus", "szeptember", "október", "november", "december",
    ]
    HU_DAYS = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
    t = text.lower()
    return (
        any(m in t for m in HU_MONTHS + HU_DAYS)
        or bool(re.search(r"\d{4}\.\s*\w", text))
        or bool(re.search(r"\d{2}\.\d{2}\.", text))
    )


def _is_time_row(text: str, cells: list[Tag]) -> bool:
    TIME_WORDS = ["éjjel", "reggel", "délelőtt", "délben", "délután", "este", "éjszaka"]
    return (
        bool(re.search(r"\b(00|06|12|18|0|6)\b", text))
        or any(w in text.lower() for w in TIME_WORDS)
        or bool(re.search(r"\b\d{1,2}:\d{2}\b", text))
    )


def _expand_date_row(row: Tag) -> list[date]:
    """Turn a date header row into a flat list of date objects (one per column)."""
    result: list[date] = []
    year = datetime.now().year

    for cell in row.find_all(["td", "th"]):
        text = cell.get_text(strip=True)
        d = _try_parse_date(text, year)
        if d is None:
            continue
        colspan = int(cell.get("colspan", 1))
        for _ in range(colspan):
            result.append(d)

    return result if result else [date.today()]


def _try_parse_date(text: str, year: int) -> date | None:
    HU_MONTH_MAP = {
        "január": 1, "február": 2, "március": 3, "április": 4,
        "május": 5, "június": 6, "július": 7, "augusztus": 8,
        "szeptember": 9, "október": 10, "november": 11, "december": 12,
    }
    # "2026. február 25." or "február 25."
    for month_hu, month_num in HU_MONTH_MAP.items():
        m = re.search(rf"{month_hu}\s+(\d{{1,2}})", text.lower())
        if m:
            try:
                return date(year, month_num, int(m.group(1)))
            except ValueError:
                pass

    # "2026. 02. 25." or "02.25." or "02/25"
    m = re.search(r"(\d{4})[.\s/]+(\d{1,2})[.\s/]+(\d{1,2})", text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    m = re.search(r"(\d{1,2})[.\s/]+(\d{1,2})", text)
    if m:
        try:
            return date(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    # "hétfő", "kedd" etc. – compute from today
    HU_DAYS_DOW = {
        "hétfő": 0, "kedd": 1, "szerda": 2, "csütörtök": 3,
        "péntek": 4, "szombat": 5, "vasárnap": 6,
    }
    from datetime import timedelta
    today = date.today()
    for day_hu, dow in HU_DAYS_DOW.items():
        if day_hu in text.lower():
            delta = (dow - today.weekday()) % 7
            return today + timedelta(days=delta)

    return None


def _time_label_to_hour(text: str) -> int | None:
    """Convert a met.hu time label to an integer hour (0-23)."""
    TIME_WORDS_TO_HOUR = {
        "éjjel": 0, "éjfél": 0, "hajnal": 3,
        "reggel": 6, "délelőtt": 9,
        "délben": 12, "dél": 12,
        "délután": 15, "este": 18, "éjszaka": 21,
    }
    t = text.lower().strip()
    for word, h in TIME_WORDS_TO_HOUR.items():
        if word in t:
            return h

    m = re.match(r"^(\d{1,2})(?::00)?h?$", t)
    if m:
        h = int(m.group(1))
        if 0 <= h <= 23:
            return h

    return None


# ---------------------------------------------------------------------------
# Cell helpers
# ---------------------------------------------------------------------------

def _nth_data_cell(cells: list[Tag], n: int) -> Tag | None:
    """Return the nth non-label data cell."""
    if n < len(cells):
        return cells[n]
    return None


def _cell_number(cells: list[Tag], n: int) -> float | None:
    """Extract a number from the nth data cell."""
    cell = _nth_data_cell(cells, n)
    if cell is None:
        return None
    text = cell.get_text(strip=True)
    return _parse_number(text)


def _parse_number(text: str) -> float | None:
    if not text:
        return None
    text = text.replace(",", ".").replace("−", "-").replace("–", "-").replace("\xa0", "")
    m = re.search(r"-?\d+\.?\d*", text)
    if m:
        try:
            return float(m.group())
        except ValueError:
            pass
    return None


def _parse_wind_dir(cell: Tag) -> str | None:
    """Extract wind direction from a table cell (may contain text or an img alt)."""
    # Some sites use images for wind direction arrows with alt text
    img = cell.find("img")
    if img:
        alt = img.get("alt", "")
        return WIND_DIR_MAP.get(alt, alt or None)

    text = cell.get_text(strip=True)
    return WIND_DIR_MAP.get(text, text or None)


def direction_to_bearing(direction: str | None) -> float | None:
    """Convert compass abbreviation to degrees (0–360)."""
    if not direction:
        return None
    BEARINGS = {
        "N": 0, "NNE": 22.5, "NE": 45, "ENE": 67.5,
        "E": 90, "ESE": 112.5, "SE": 135, "SSE": 157.5,
        "S": 180, "SSW": 202.5, "SW": 225, "WSW": 247.5,
        "W": 270, "WNW": 292.5, "NW": 315, "NNW": 337.5,
    }
    return BEARINGS.get(direction.upper())


def _icon_to_condition(src: str, alt: str) -> str:
    """Map a met.hu icon filename to an HA weather condition string."""
    # Extract icon code from filename, e.g. "n02.gif" → "n02", "04.gif" → "04"
    m = re.search(r"/(n?\d{2})\.(?:gif|png|jpg)", src, re.I)
    if m:
        code = m.group(1).lower()
        if code in CONDITION_MAP:
            return CONDITION_MAP[code]

    # Keyword fallback using alt text
    a = alt.lower()
    if any(w in a for w in ["zivatar", "thunder"]):
        return "lightning-rainy"
    if any(w in a for w in ["hó", "havaz", "snow"]):
        return "snowy"
    if any(w in a for w in ["eső", "esik", "rain", "csapadék"]):
        return "rainy"
    if any(w in a for w in ["köd", "fog"]):
        return "fog"
    if any(w in a for w in ["derült", "napos", "clear", "sunny"]):
        return "sunny"
    if any(w in a for w in ["felhős", "borult", "cloud"]):
        return "cloudy"
    if any(w in a for w in ["változékony", "részben felhős", "partly"]):
        return "partlycloudy"
    return "exceptional"


# ---------------------------------------------------------------------------
# Daily aggregation
# ---------------------------------------------------------------------------

def _aggregate_daily(periods: list[ForecastPeriod]) -> list[ForecastPeriod]:
    """Group 6-hourly periods into daily summary objects."""
    from collections import defaultdict
    from datetime import timedelta

    groups: dict[str, list[ForecastPeriod]] = defaultdict(list)
    for p in periods:
        key = p.forecast_time.strftime("%Y-%m-%d") if p.forecast_time else "unknown"
        groups[key].append(p)

    daily = []
    for key, day_periods in groups.items():
        s = ForecastPeriod()
        if day_periods[0].forecast_time:
            s.forecast_time = day_periods[0].forecast_time.replace(
                hour=12, minute=0, second=0, microsecond=0
            )

        temps = [p.temperature for p in day_periods if p.temperature is not None]
        if temps:
            s.temperature = round(sum(temps) / len(temps), 1)
            s.temperature_min = min(temps)
            s.temperature_max = max(temps)

        prec = [p.precipitation for p in day_periods if p.precipitation is not None]
        if prec:
            s.precipitation = round(sum(prec), 1)

        probs = [p.precipitation_probability for p in day_periods if p.precipitation_probability is not None]
        if probs:
            s.precipitation_probability = max(probs)

        winds = [p.wind_speed for p in day_periods if p.wind_speed is not None]
        if winds:
            s.wind_speed = max(winds)

        mid = day_periods[len(day_periods) // 2]
        s.weather_condition = mid.weather_condition
        s.weather_description = mid.weather_description
        s.wind_direction = mid.wind_direction
        s.humidity = mid.humidity

        daily.append(s)

    return daily


# ---------------------------------------------------------------------------
# Fallback parser
# ---------------------------------------------------------------------------

def _parse_columns_fallback(rows: list[Tag]) -> list[ForecastPeriod]:
    """
    Last-resort parser: treats each column (excluding first label col) as a period.
    Tries to extract temperature, precipitation, wind speed by matching keywords
    in the row label cell.
    """
    _LOGGER.debug("Using column-based fallback parser")
    if not rows:
        return []

    max_cols = max(len(r.find_all(["td", "th"])) for r in rows)
    periods = [ForecastPeriod() for _ in range(max_cols - 1)]

    for row in rows:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        label = cells[0].get_text(strip=True).lower()
        data = cells[1:]

        for i, cell in enumerate(data):
            if i >= len(periods):
                break
            text = cell.get_text(strip=True)
            val = _parse_number(text)

            if re.search(r"hőmérséklet|temp", label) and val is not None:
                periods[i].temperature = val
            elif re.search(r"csapadék(?!.*való)", label) and val is not None:
                periods[i].precipitation = val
            elif re.search(r"való|prob", label) and val is not None:
                periods[i].precipitation_probability = int(val)
            elif re.search(r"szélseb|wind.?sp|km/h|m/s", label) and val is not None:
                periods[i].wind_speed = val
            elif re.search(r"nedv|humid", label) and val is not None:
                periods[i].humidity = int(val)
            elif re.search(r"szélirány|wind.?dir", label):
                periods[i].wind_direction = _parse_wind_dir(cell)

    return [p for p in periods if any([p.temperature, p.precipitation, p.wind_speed])]
