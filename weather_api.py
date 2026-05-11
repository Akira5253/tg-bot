"""
Модуль для работы с публичным API OpenWeatherMap.

Инкапсулирует всю логику HTTP-запросов и обработки ошибок.
Документация API: https://openweathermap.org/current
"""
import asyncio
import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

# API-ключ читаем из переменных окружения (см. .env.example).
# Никогда не храните ключ в коде и не коммитьте его в репозиторий.
API_KEY = os.getenv("OPENWEATHER_API_KEY")
BASE_URL = "https://api.openweathermap.org/data/2.5/weather"

# Таймаут для всех HTTP-запросов к API (секунды)
REQUEST_TIMEOUT = 10


class WeatherAPIError(Exception):
    """
    Кастомное исключение, описывающее ошибку при обращении к API погоды.

    Атрибуты:
        message — текст ошибки для отображения пользователю.
        code    — HTTP-код ответа (если был получен).
    """

    def __init__(self, message: str, code: Optional[int] = None) -> None:
        self.message = message
        self.code = code
        super().__init__(message)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}" if self.code else self.message


async def _make_request(params: dict) -> dict:
    """
    Внутренняя функция: выполняет GET-запрос к API погоды.

    К переданным `params` автоматически добавляются ключ API,
    единицы измерения (Цельсий) и язык описаний (русский).
    """
    if not API_KEY:
        raise WeatherAPIError(
            "API-ключ OpenWeatherMap не задан. "
            "Установите переменную окружения OPENWEATHER_API_KEY."
        )

    # Базовые параметры запроса
    query = {
        **params,
        "appid": API_KEY,
        "units": "metric",  # температура в градусах Цельсия
        "lang": "ru",       # описания на русском
    }

    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(BASE_URL, params=query) as response:
                # Безопасно парсим JSON, даже при ошибочных статусах
                try:
                    data = await response.json()
                except aiohttp.ContentTypeError:
                    raise WeatherAPIError(
                        "Получен некорректный ответ от API.",
                        code=response.status,
                    )

                if response.status != 200:
                    # OpenWeatherMap в ошибках возвращает поле "message"
                    raise WeatherAPIError(
                        message=data.get("message", "Неизвестная ошибка API"),
                        code=response.status,
                    )

                return data

    except asyncio.TimeoutError as exc:
        raise WeatherAPIError("Превышено время ожидания ответа от API.") from exc
    except aiohttp.ClientError as exc:
        # Сетевые проблемы: DNS, недоступность хоста и т. п.
        raise WeatherAPIError(f"Сетевая ошибка: {exc}") from exc


async def get_weather_by_city(city: str) -> dict:
    """
    Получить текущую погоду по названию города.

    :param city: название города (на русском или английском).
    :return: словарь с данными о погоде в формате OpenWeatherMap.
    :raises WeatherAPIError: при любой ошибке запроса.
    """
    logger.info("Requesting weather by city: %s", city)
    return await _make_request({"q": city})


async def get_weather_by_coords(lat: float, lon: float) -> dict:
    """
    Получить текущую погоду по географическим координатам.

    :param lat: широта.
    :param lon: долгота.
    :return: словарь с данными о погоде в формате OpenWeatherMap.
    :raises WeatherAPIError: при любой ошибке запроса.
    """
    logger.info("Requesting weather by coords: %s, %s", lat, lon)
    return await _make_request({"lat": lat, "lon": lon})
