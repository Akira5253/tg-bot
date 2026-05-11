"""
Telegram-бот для получения погоды через OpenWeatherMap API.

Поддерживает:
- Команды /start, /help, /weather <город>
- Получение погоды по геолокации
- Получение погоды по названию города в свободном тексте
"""
import asyncio
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

from weather_api import (
    WeatherAPIError,
    get_weather_by_city,
    get_weather_by_coords,
)

# Загружаем переменные окружения из .env файла
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError(
        "Переменная окружения BOT_TOKEN не установлена. "
        "Создайте файл .env по образцу .env.example"
    )

# Настройка логирования: уровень INFO, формат с временем и уровнем сообщения
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Создаём экземпляры бота и диспетчера
# HTML используется по умолчанию для форматирования сообщений
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


# ---------- Тексты сообщений ----------

WELCOME_TEXT = (
    "👋 <b>Привет!</b> Я бот, который показывает текущую погоду.\n\n"
    "Просто отправь мне название города или поделись геолокацией — "
    "и я расскажу, какая там погода.\n\n"
    "Подробнее о возможностях: /help"
)

HELP_TEXT = (
    "🌤 <b>Что я умею:</b>\n\n"
    "▫️ /start — приветственное сообщение\n"
    "▫️ /help — эта справка\n"
    "▫️ /weather <i>город</i> — погода в указанном городе\n"
    "    Пример: <code>/weather Москва</code>\n\n"
    "📍 Также можно просто отправить:\n"
    "▫️ Название города текстом (например, <i>Краков</i>)\n"
    "▫️ Геолокацию через скрепку — 📎"
)


# ---------- Обработчики команд ----------

@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start."""
    logger.info("User %s started the bot", message.from_user.id)
    await message.answer(WELCOME_TEXT)


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Обработчик команды /help."""
    await message.answer(HELP_TEXT)


@dp.message(Command("weather"))
async def cmd_weather(message: Message) -> None:
    """
    Обработчик команды /weather <город>.
    Извлекает название города из аргументов команды.
    """
    # Разбиваем сообщение на саму команду и её аргументы
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "❌ Пожалуйста, укажите название города.\n"
            "Пример: <code>/weather Москва</code>"
        )
        return

    city = parts[1].strip()
    await _reply_with_weather_by_city(message, city)


# ---------- Обработчики прочих сообщений ----------

@dp.message(F.location)
async def location_handler(message: Message) -> None:
    """Обработчик геолокации от пользователя."""
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info("Location from %s: %s, %s", message.from_user.id, lat, lon)
    await _reply_with_weather_by_coords(message, lat, lon)


@dp.message(F.text)
async def text_handler(message: Message) -> None:
    """
    Обработчик произвольного текста.
    Рассматриваем любой текст как название города.
    """
    city = message.text.strip()
    if not city:
        return
    await _reply_with_weather_by_city(message, city)


@dp.message()
async def fallback_handler(message: Message) -> None:
    """Обработчик всех остальных типов сообщений (стикеры, фото и т. п.)."""
    await message.answer(
        "🤖 Я понимаю только текст с названием города, "
        "команду /weather или геолокацию.\n"
        "Введите /help для справки."
    )


# ---------- Вспомогательные функции отправки ответа ----------

async def _reply_with_weather_by_city(message: Message, city: str) -> None:
    """Получает погоду по названию города и отправляет пользователю."""
    try:
        data = await get_weather_by_city(city)
        await message.answer(format_weather(data))
    except WeatherAPIError as e:
        # Различные понятные сообщения в зависимости от типа ошибки API
        if e.code == 404:
            text = f"❌ Город «{city}» не найден. Проверьте написание."
        elif e.code == 401:
            text = "❌ Ошибка авторизации в сервисе погоды. Свяжитесь с администратором."
        else:
            text = f"❌ Не удалось получить погоду: {e.message}"
        await message.answer(text)
        logger.warning("API error for city '%s': %s", city, e)
    except Exception:
        # Любая непредвиденная ошибка не должна обрушить бота
        await message.answer(
            "❌ Произошла непредвиденная ошибка. Попробуйте ещё раз чуть позже."
        )
        logger.exception("Unexpected error while fetching weather by city")


async def _reply_with_weather_by_coords(
    message: Message, lat: float, lon: float
) -> None:
    """Получает погоду по координатам и отправляет пользователю."""
    try:
        data = await get_weather_by_coords(lat, lon)
        await message.answer(format_weather(data))
    except WeatherAPIError as e:
        await message.answer(f"❌ Не удалось получить погоду: {e.message}")
        logger.warning("API error for coords (%s, %s): %s", lat, lon, e)
    except Exception:
        await message.answer(
            "❌ Произошла непредвиденная ошибка. Попробуйте ещё раз чуть позже."
        )
        logger.exception("Unexpected error while fetching weather by coords")


# ---------- Форматирование ответа ----------

# Сопоставление погодных условий и эмодзи
WEATHER_ICONS = {
    "Clear": "☀️",
    "Clouds": "☁️",
    "Rain": "🌧",
    "Drizzle": "🌦",
    "Thunderstorm": "⛈",
    "Snow": "❄️",
    "Mist": "🌫",
    "Fog": "🌫",
    "Haze": "🌫",
    "Smoke": "🌫",
    "Dust": "🌫",
    "Sand": "🌫",
    "Ash": "🌫",
    "Squall": "💨",
    "Tornado": "🌪",
}


def _hpa_to_mmhg(hpa: int) -> int:
    """Перевод давления из гектопаскалей в миллиметры ртутного столба."""
    return round(hpa * 0.75006)


def format_weather(data: dict) -> str:
    """
    Форматирует словарь с данными OpenWeatherMap в читаемое сообщение.

    Извлекает только нужные поля и оформляет в виде HTML-сообщения.
    """
    city = data.get("name", "—")
    country = data.get("sys", {}).get("country", "")

    weather = data["weather"][0]
    description = weather["description"].capitalize()
    icon = WEATHER_ICONS.get(weather.get("main", ""), "🌡")

    main = data["main"]
    temp = main["temp"]
    feels_like = main["feels_like"]
    humidity = main["humidity"]
    pressure = main["pressure"]

    wind_speed = data.get("wind", {}).get("speed", 0)

    location = f"{city}, {country}" if country else city

    return (
        f"{icon} <b>Погода в {location}</b>\n\n"
        f"🌡 Температура: <b>{temp:+.1f}°C</b>\n"
        f"🤔 Ощущается как: <b>{feels_like:+.1f}°C</b>\n"
        f"☁️ {description}\n"
        f"💧 Влажность: {humidity}%\n"
        f"📊 Давление: {_hpa_to_mmhg(pressure)} мм рт. ст.\n"
        f"💨 Ветер: {wind_speed} м/с"
    )


# ---------- Точка входа ----------

async def main() -> None:
    """Запуск бота в режиме long polling."""
    logger.info("Bot is starting…")
    # Удаляем накопившиеся апдейты, чтобы не обрабатывать старые сообщения
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
