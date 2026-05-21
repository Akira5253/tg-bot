import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from dotenv import load_dotenv

from weather_api import (
    WeatherAPIError,
    get_forecast,
    get_precip_probability,
    get_weather_by_city,
    get_weather_by_coords,
)
from weather_card import render_weather_card

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError(
        "Переменная окружения BOT_TOKEN не установлена. "
        "Создайте файл .env по образцу .env.example"
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()

class ThrottlingMiddleware(BaseMiddleware):

    def __init__(self, rate_limit: float = 1.5) -> None:
        self.rate_limit = rate_limit
        self._last_call: dict[int, float] = {}
        self._last_warn: dict[int, float] = {}
        super().__init__()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)

        now = time.monotonic()
        last = self._last_call.get(user.id, 0.0)

        if now - last < self.rate_limit:
            warned = self._last_warn.get(user.id, 0.0)
            if now - warned >= self.rate_limit:
                self._last_warn[user.id] = now
                if isinstance(event, Message):
                    await event.answer(
                        "Слишком часто! Подождите пару секунд "
                        "перед следующим запросом."
                    )
                elif isinstance(event, CallbackQuery):
                    await event.answer(
                        "Слишком часто, подождите пару секунд.",
                        show_alert=False,
                    )
            logger.info("Throttled user %s", user.id)
            return  

        self._last_call[user.id] = now
        return await handler(event, data)

_throttling = ThrottlingMiddleware(rate_limit=1.5)
dp.message.middleware(_throttling)
dp.callback_query.middleware(_throttling)

WELCOME_TEXT = (
    "👋 <b>Привет!</b> Я бот, который показывает текущую погоду.\n\n"
    "Просто отправь мне название города или поделись геолокацией — "
    "и я расскажу, какая там погода, и подскажу, что надеть.\n\n"
    "Кнопкой ниже можно сразу узнать погоду рядом с тобой.\n"
    "Подробнее: /help"
)

HELP_TEXT = (
    "<b>Что я умею:</b>\n\n"
    "▫️ /start — приветственное сообщение\n"
    "▫️ /help — эта справка\n"
    "▫️ /weather <i>город</i> — погода в указанном городе\n"
    "  Пример: <code>/weather Москва</code>\n\n"
    "  Также можно просто отправить:\n"
    "▫️ Название города текстом (например, <i>Краков</i>)\n"
    "▫️ Геолокацию через кнопку или скрепку 📎\n\n"
    "Под ответом будет кнопка <b>«Прогноз на завтра»</b> — "
    "покажу погоду на утро, день и вечер.\n\n"
    "В сводке: температура, влажность, давление, ветер, облачность, "
    "видимость, вероятность осадков, восход/закат и советы по одежде."
)

BTN_HELP = "Помощь"
BTN_LOCATION = "Погода рядом"

def main_reply_keyboard() -> Any:
    kb = ReplyKeyboardBuilder()
    kb.button(text=BTN_LOCATION, request_location=True)
    kb.button(text=BTN_HELP)
    kb.adjust(2)
    return kb.as_markup(resize_keyboard=True)


def forecast_keyboard_city(city: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    safe_city = city[:50]
    kb.button(text="📅 Прогноз на завтра", callback_data=f"fc_city:{safe_city}")
    return kb.as_markup()


def forecast_keyboard_geo(lat: float, lon: float) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="📅 Прогноз на завтра",
        callback_data=f"fc_geo:{lat:.4f}:{lon:.4f}",
    )
    return kb.as_markup()

@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    logger.info("User %s started the bot", message.from_user.id)
    await message.answer(WELCOME_TEXT, reply_markup=main_reply_keyboard())


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@dp.message(Command("weather"))
async def cmd_weather(message: Message) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Пожалуйста, укажите название города.\n"
            "Пример: <code>/weather Москва</code>"
        )
        return

    city = parts[1].strip()
    await _reply_with_weather_by_city(message, city)

@dp.message(F.text == BTN_HELP)
async def btn_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@dp.message(F.location)
async def location_handler(message: Message) -> None:
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info("Location from %s: %s, %s", message.from_user.id, lat, lon)
    await _reply_with_weather_by_coords(message, lat, lon)


@dp.message(F.text)
async def text_handler(message: Message) -> None:
    city = message.text.strip()
    if not city:
        return
    await _reply_with_weather_by_city(message, city)


@dp.message()
async def fallback_handler(message: Message) -> None:
    await message.answer(
        "Я понимаю только текст с названием города, "
        "команду /weather или геолокацию.\n"
        "Введите /help для справки."
    )

@dp.callback_query(F.data.startswith("fc_city:"))
async def cb_forecast_city(callback: CallbackQuery) -> None:
    city = callback.data.split(":", 1)[1]
    await callback.answer() 
    try:
        forecast = await get_forecast({"q": city})
        await callback.message.answer(format_tomorrow(forecast))
    except WeatherAPIError as e:
        await callback.message.answer(
            f"Не удалось получить прогноз: {e.message}"
        )
        logger.warning("Forecast error for city '%s': %s", city, e)
    except Exception:
        await callback.message.answer(
            "Не удалось получить прогноз. Попробуйте позже."
        )
        logger.exception("Unexpected error in forecast (city)")


@dp.callback_query(F.data.startswith("fc_geo:"))
async def cb_forecast_geo(callback: CallbackQuery) -> None:
    try:
        _, lat_s, lon_s = callback.data.split(":")
        lat, lon = float(lat_s), float(lon_s)
    except ValueError:
        await callback.answer("Некорректные координаты", show_alert=True)
        return

    await callback.answer()
    try:
        forecast = await get_forecast({"lat": lat, "lon": lon})
        await callback.message.answer(format_tomorrow(forecast))
    except WeatherAPIError as e:
        await callback.message.answer(
            f"Не удалось получить прогноз: {e.message}"
        )
        logger.warning("Forecast error for coords: %s", e)
    except Exception:
        await callback.message.answer(
            "Не удалось получить прогноз. Попробуйте позже."
        )
        logger.exception("Unexpected error in forecast (geo)")

async def _reply_with_weather_by_city(message: Message, city: str) -> None:
    try:
        data = await get_weather_by_city(city)
        pop = await get_precip_probability({"q": city})
        png = render_weather_card(data, pop)
        photo = BufferedInputFile(png, filename="weather.png")
        await message.answer_photo(
            photo=photo,
            caption=format_weather(data, pop),
            reply_markup=forecast_keyboard_city(city),
        )
    except WeatherAPIError as e:
        if e.code == 404:
            text = f"Город «{city}» не найден. Проверьте написание."
        elif e.code == 401:
            text = "Ошибка авторизации в сервисе погоды. Свяжитесь с администратором."
        else:
            text = f"Не удалось получить погоду: {e.message}"
        await message.answer(text)
        logger.warning("API error for city '%s': %s", city, e)
    except Exception:
        await message.answer(
            "Произошла непредвиденная ошибка. Попробуйте ещё раз чуть позже."
        )
        logger.exception("Unexpected error while fetching weather by city")

async def _reply_with_weather_by_coords(
    message: Message, lat: float, lon: float
) -> None:
    try:
        data = await get_weather_by_coords(lat, lon)
        pop = await get_precip_probability({"lat": lat, "lon": lon})
        png = render_weather_card(data, pop)
        photo = BufferedInputFile(png, filename="weather.png")
        await message.answer_photo(
            photo=photo,
            caption=format_weather(data, pop),
            reply_markup=forecast_keyboard_geo(lat, lon),
        )
    except WeatherAPIError as e:
        await message.answer(f"Не удалось получить погоду: {e.message}")
        logger.warning("API error for coords (%s, %s): %s", lat, lon, e)
    except Exception:
        await message.answer(
            "Произошла непредвиденная ошибка. Попробуйте ещё раз чуть позже."
        )
        logger.exception("Unexpected error while fetching weather by coords")

WEATHER_ICONS = {
    "Clear": "☀️", "Clouds": "☁️", "Rain": "🌧", "Drizzle": "🌦",
    "Thunderstorm": "⛈", "Snow": "❄️", "Mist": "🌫", "Fog": "🌫",
    "Haze": "🌫", "Smoke": "🌫", "Dust": "🌫", "Sand": "🌫",
    "Ash": "🌫", "Squall": "💨", "Tornado": "🌪",
}

WIND_DIRECTIONS = [
    "С", "ССВ", "СВ", "ВСВ", "В", "ВЮВ", "ЮВ", "ЮЮВ",
    "Ю", "ЮЮЗ", "ЮЗ", "ЗЮЗ", "З", "ЗСЗ", "СЗ", "ССЗ",
]


def _hpa_to_mmhg(hpa: int) -> int:
    return round(hpa * 0.75006)


def _wind_direction(deg: float) -> str:
    return WIND_DIRECTIONS[round(deg / 22.5) % 16]


def _format_local_time(unix_ts: int, tz_offset_sec: int) -> str:
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc) + timedelta(
        seconds=tz_offset_sec
    )
    return dt.strftime("%H:%M")

CLOTHING_TIERS = [
    (
        28, "Очень жарко",
        "лёгкое платье или шорты с топом, открытая обувь, "
        "солнцезащитные очки и головной убор",
        "футболка и шорты, лёгкие кроссовки или сандалии, "
        "кепка и очки от солнца",
    ),
    (
        23, "Тепло",
        "платье, юбка или лёгкие брюки с футболкой, лёгкая обувь",
        "футболка и лёгкие брюки или шорты, кроссовки",
    ),
    (
        17, "Комфортно",
        "джинсы или брюки с футболкой/блузкой, на вечер пригодится лёгкая кофта",
        "джинсы и футболка либо рубашка, лёгкая кофта про запас",
    ),
    (
        12, "Прохладно",
        "джинсы, свитер или джинсовка, закрытая обувь",
        "джинсы, свитшот или лёгкая куртка, кроссовки",
    ),
    (
        6, "Свежо",
        "тёплая кофта или свитер плюс куртка, джинсы, ботинки",
        "куртка или худи, джинсы, ботинки либо плотные кроссовки",
    ),
    (
        0, "Холодно",
        "тёплая куртка или пальто, свитер, шарф, тёплая закрытая обувь",
        "тёплая куртка, свитер, шапка, закрытая утеплённая обувь",
    ),
    (
        -8, "Мороз",
        "зимнее пальто или пуховик, тёплый свитер, шапка, шарф, "
        "перчатки, зимние сапоги",
        "зимняя куртка или пуховик, свитер, шапка, перчатки, "
        "тёплая зимняя обувь",
    ),
    (
        -100, "Сильный мороз",
        "тёплый пуховик, термобельё, шапка, шарф, варежки, "
        "зимняя обувь с тёплым носком — без необходимости лучше "
        "не выходить надолго",
        "тёплый пуховик, термобельё, шапка, перчатки, зимняя обувь — "
        "минимизируйте время на улице",
    ),
]


def _clothing_advice(
    feels_like: float, weather_main: str, wind_speed: float
) -> str:
    tier = next(t for t in CLOTHING_TIERS if feels_like >= t[0])
    _, title, advice_woman, advice_man = tier

    extras = []
    if weather_main in ("Rain", "Drizzle", "Thunderstorm"):
        extras.append("возьмите зонт и наденьте непромокаемую обувь ☔")
    if weather_main == "Snow":
        extras.append("обувь должна быть тёплой и непромокаемой ❄️")
    if wind_speed >= 8:
        extras.append(
            "ветер сильный — пригодится ветрозащитная куртка, "
            "по ощущениям будет холоднее"
        )

    text = (
        f"\n\n<b>Что надеть</b> ({title})\n"
        f"Девушке: {advice_woman}.\n"
        f"Парню: {advice_man}."
    )
    if extras:
        text += "\n⚠️ Также: " + "; ".join(extras) + "."
    return text

def format_weather(data: dict, precip_probability: int | None = None) -> str:
    city = data.get("name", "—")
    country = data.get("sys", {}).get("country", "")

    weather = data["weather"][0]
    weather_main = weather.get("main", "")
    description = weather["description"].capitalize()
    icon = WEATHER_ICONS.get(weather_main, "🌡")

    main = data["main"]
    temp = main["temp"]
    feels_like = main["feels_like"]
    temp_min = main.get("temp_min", temp)
    temp_max = main.get("temp_max", temp)
    humidity = main["humidity"]
    pressure = main["pressure"]

    wind = data.get("wind", {})
    wind_speed = wind.get("speed", 0)
    wind_gust = wind.get("gust")
    wind_deg = wind.get("deg")

    clouds = data.get("clouds", {}).get("all")
    visibility = data.get("visibility")

    sys = data.get("sys", {})
    tz_offset = data.get("timezone", 0)

    location = f"{city}, {country}" if country else city

    lines = [
        f"{icon} <b>Погода в {location}</b>",
        "",
        f"🌡 Температура: <b>{temp:+.1f}°C</b> "
        f"(ощущается как <b>{feels_like:+.1f}°C</b>)",
        f"📉 Мин/макс: {temp_min:+.1f}°C / {temp_max:+.1f}°C",
        f"☁️ {description}",
        f"💧 Влажность: {humidity}%",
        f"📊 Давление: {_hpa_to_mmhg(pressure)} мм рт. ст.",
    ]

    wind_line = f"💨 Ветер: {wind_speed} м/с"
    if wind_deg is not None:
        wind_line += f", {_wind_direction(wind_deg)}"
    if wind_gust:
        wind_line += f" (порывы до {wind_gust} м/с)"
    lines.append(wind_line)

    if clouds is not None:
        lines.append(f"🌥 Облачность: {clouds}%")
    if visibility is not None:
        lines.append(f"👁 Видимость: {visibility / 1000:.1f} км")
    if precip_probability is not None:
        lines.append(f"🌧 Вероятность осадков: {precip_probability}%")

    rain = data.get("rain", {})
    snow = data.get("snow", {})
    if rain.get("1h"):
        lines.append(f"☔ Дождь: {rain['1h']} мм/ч")
    if snow.get("1h"):
        lines.append(f"🌨 Снег: {snow['1h']} мм/ч")

    if sys.get("sunrise") and sys.get("sunset"):
        sunrise = _format_local_time(sys["sunrise"], tz_offset)
        sunset = _format_local_time(sys["sunset"], tz_offset)
        lines.append(f"🌅 Восход: {sunrise}   🌇 Закат: {sunset}")

    text = "\n".join(lines)
    text += _clothing_advice(feels_like, weather_main, wind_speed)
    return text

DAY_PARTS = [
    ("Утро", 9, "🌅"),
    ("День", 15, "🌤"),
    ("Вечер", 21, "🌆"),
]

RU_MONTHS = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def format_tomorrow(forecast: dict) -> str:
    city_info = forecast.get("city", {})
    city = city_info.get("name", "—")
    country = city_info.get("country", "")
    tz_offset = city_info.get("timezone", 0)

    items = forecast.get("list", [])
    if not items:
        return "Прогноз на завтра пока недоступен."

    now_local = datetime.now(timezone.utc) + timedelta(seconds=tz_offset)
    tomorrow = (now_local + timedelta(days=1)).date()

    by_hour: dict[int, dict] = {}
    for item in items:
        dt_local = datetime.fromtimestamp(
            item["dt"], tz=timezone.utc
        ) + timedelta(seconds=tz_offset)
        if dt_local.date() == tomorrow:
            by_hour[dt_local.hour] = item

    if not by_hour:
        return "Прогноз на завтра пока недоступен."

    location = f"{city}, {country}" if country else city
    header = (
        f"📅 <b>Прогноз на завтра</b> "
        f"({tomorrow.day} {RU_MONTHS[tomorrow.month]})\n"
        f"{location}\n"
    )

    lines = [header]
    for label, target_hour, emoji in DAY_PARTS:
        nearest_hour = min(
            by_hour.keys(), key=lambda h: abs(h - target_hour)
        )
        item = by_hour[nearest_hour]

        temp = item["main"]["temp"]
        feels = item["main"]["feels_like"]
        desc = item["weather"][0]["description"].capitalize()
        w_main = item["weather"][0].get("main", "")
        w_icon = WEATHER_ICONS.get(w_main, "🌡")
        pop = round(item.get("pop", 0) * 100)

        lines.append(
            f"\n{emoji} <b>{label}</b> (~{nearest_hour:02d}:00)\n"
            f"   {w_icon} {desc}\n"
            f"   🌡 {temp:+.1f}°C (ощущается {feels:+.1f}°C)\n"
            f"   🌧 Вероятность осадков: {pop}%"
        )

    return "".join(lines)

async def main() -> None:
    logger.info("Bot is starting…")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
