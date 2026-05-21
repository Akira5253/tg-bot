import asyncio
import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

REQUEST_TIMEOUT = 10

class WeatherAPIError(Exception):

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        self.message = message
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}" if self.code else self.message


async def _make_request(url: str, params: dict) -> dict:
    API_KEY = os.getenv("OPENWEATHER_API_KEY")

    if not API_KEY:
        raise WeatherAPIError(
            "API-ключ OpenWeatherMap не задан. "
            "Установите переменную окружения OPENWEATHER_API_KEY."
        )

    query = {
        **params,
        "appid": API_KEY,
        "units": "metric",  
        "lang": "ru",      
    }

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=query) as response:
                try:
                    data = await response.json()
                except aiohttp.ContentTypeError:
                    raise WeatherAPIError(
                        "Получен некорректный ответ от API.",
                        code=response.status,
                    )

                if response.status != 200:
                    raise WeatherAPIError(
                        message=data.get("message", "Неизвестная ошибка API"),
                        code=response.status,
                    )

                return data

    except asyncio.TimeoutError as exc:
        raise WeatherAPIError("Превышено время ожидания ответа от API.") from exc
    except aiohttp.ClientError as exc:
        raise WeatherAPIError(f"Сетевая ошибка: {exc}") from exc

async def get_weather_by_city(city: str) -> dict:
    logger.info("Requesting weather by city: %s", city)
    return await _make_request(WEATHER_URL, {"q": city})


async def get_weather_by_coords(lat: float, lon: float) -> dict:
    logger.info("Requesting weather by coords: %s, %s", lat, lon)
    return await _make_request(WEATHER_URL, {"lat": lat, "lon": lon})

async def get_precip_probability(params: dict) -> Optional[int]:
    try:
        data = await _make_request(FORECAST_URL, params)
        forecast_list = data.get("list", [])
        if not forecast_list:
            return None
        pop = forecast_list[0].get("pop")
        if pop is None:
            return None
        return round(pop * 100)
    except WeatherAPIError as exc:
        logger.warning("Could not fetch precipitation probability: %s", exc)
        return None


async def get_forecast(params: dict) -> dict:
    logger.info("Requesting full forecast: %s", params)
    return await _make_request(FORECAST_URL, params)