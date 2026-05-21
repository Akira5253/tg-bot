import io
import os
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 900, 540

_FONT_CANDIDATES_REGULAR = [
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]
_FONT_CANDIDATES_BOLD = [
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\calibrib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
]


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = _FONT_CANDIDATES_BOLD if bold else _FONT_CANDIDATES_REGULAR
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()

_BACKGROUNDS = {
    "clear_day": ((74, 144, 217), (135, 206, 235)),
    "clear_night": ((26, 26, 62), (52, 52, 95)),
    "clouds_day": ((107, 123, 140), (155, 168, 181)),
    "clouds_night": ((52, 58, 74), (78, 86, 102)),
    "rain": ((74, 90, 106), (107, 123, 140)),
    "thunder": ((44, 44, 62), (74, 74, 94)),
    "snow": ((168, 192, 208), (216, 228, 236)),
    "mist": ((138, 154, 165), (176, 188, 196)),
}


def _pick_scheme(weather_main: str, is_night: bool) -> str:
    if weather_main == "Clear":
        return "clear_night" if is_night else "clear_day"
    if weather_main == "Clouds":
        return "clouds_night" if is_night else "clouds_day"
    if weather_main in ("Rain", "Drizzle"):
        return "rain"
    if weather_main == "Thunderstorm":
        return "thunder"
    if weather_main == "Snow":
        return "snow"
    return "mist"


def _gradient_background(scheme: str) -> Image.Image:
    top, bottom = _BACKGROUNDS.get(scheme, _BACKGROUNDS["mist"])
    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    for y in range(HEIGHT):
        ratio = y / HEIGHT
        r = int(top[0] + (bottom[0] - top[0]) * ratio)
        g = int(top[1] + (bottom[1] - top[1]) * ratio)
        b = int(top[2] + (bottom[2] - top[2]) * ratio)
        draw.line([(0, y), (WIDTH, y)], fill=(r, g, b))
    return img

def _draw_sun(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    yellow = (255, 214, 102)
    import math
    for i in range(12):
        angle = math.radians(i * 30)
        x1 = cx + int((r + 12) * math.cos(angle))
        y1 = cy + int((r + 12) * math.sin(angle))
        x2 = cx + int((r + 34) * math.cos(angle))
        y2 = cy + int((r + 34) * math.sin(angle))
        draw.line([(x1, y1), (x2, y2)], fill=yellow, width=6)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=yellow)


def _draw_moon(draw: ImageDraw.ImageDraw, cx: int, cy: int, r: int) -> None:
    light = (235, 235, 245)
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=light)
    offset = int(r * 0.6)
    draw.ellipse(
        [cx - r + offset, cy - r - 4, cx + r + offset, cy + r - 4],
        fill=(40, 40, 75),
    )

def _draw_cloud(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    scale: float = 1.0,
    color: Tuple[int, int, int] = (240, 240, 245),
) -> None:
    s = scale
    draw.ellipse(
        [cx - int(70 * s), cy - int(25 * s),
         cx + int(10 * s), cy + int(45 * s)],
        fill=color,
    )
    draw.ellipse(
        [cx - int(30 * s), cy - int(50 * s),
         cx + int(50 * s), cy + int(30 * s)],
        fill=color,
    )
    draw.ellipse(
        [cx + int(10 * s), cy - int(25 * s),
         cx + int(80 * s), cy + int(45 * s)],
        fill=color,
    )
    draw.rectangle(
        [cx - int(60 * s), cy + int(10 * s),
         cx + int(70 * s), cy + int(45 * s)],
        fill=color,
    )


def _draw_rain_drops(
    draw: ImageDraw.ImageDraw, cx: int, cy: int
) -> None:
    blue = (120, 170, 220)
    for dx in (-40, -10, 20, 50):
        draw.line(
            [(cx + dx, cy + 55), (cx + dx - 8, cy + 90)],
            fill=blue, width=6,
        )


def _draw_snowflakes(
    draw: ImageDraw.ImageDraw, cx: int, cy: int
) -> None:
    white = (245, 248, 252)
    for dx in (-40, -5, 30, 55):
        x, y = cx + dx, cy + 75
        draw.line([(x - 9, y), (x + 9, y)], fill=white, width=4)
        draw.line([(x, y - 9), (x, y + 9)], fill=white, width=4)
        draw.line([(x - 6, y - 6), (x + 6, y + 6)], fill=white, width=4)
        draw.line([(x - 6, y + 6), (x + 6, y - 6)], fill=white, width=4)


def _draw_lightning(
    draw: ImageDraw.ImageDraw, cx: int, cy: int
) -> None:
    yellow = (255, 221, 87)
    draw.polygon(
        [
            (cx + 5, cy + 50), (cx - 20, cy + 95),
            (cx + 2, cy + 95), (cx - 12, cy + 130),
            (cx + 28, cy + 80), (cx + 6, cy + 80),
        ],
        fill=yellow,
    )

def _draw_mist(draw: ImageDraw.ImageDraw, cx: int, cy: int) -> None:
    grey = (220, 224, 228)
    for i, dy in enumerate((-20, 5, 30, 55)):
        x_off = 10 if i % 2 else -10
        draw.line(
            [(cx - 70 + x_off, cy + dy), (cx + 70 + x_off, cy + dy)],
            fill=grey, width=8,
        )

def _draw_weather_icon(
    draw: ImageDraw.ImageDraw,
    weather_main: str,
    is_night: bool,
    cx: int,
    cy: int,
) -> None:
    if weather_main == "Clear":
        if is_night:
            _draw_moon(draw, cx, cy, 55)
        else:
            _draw_sun(draw, cx, cy, 50)
    elif weather_main == "Clouds":
        if not is_night:
            _draw_sun(draw, cx - 40, cy - 40, 32)
        _draw_cloud(draw, cx, cy)
    elif weather_main in ("Rain", "Drizzle"):
        _draw_cloud(draw, cx, cy, color=(200, 206, 214))
        _draw_rain_drops(draw, cx, cy)
    elif weather_main == "Thunderstorm":
        _draw_cloud(draw, cx, cy, color=(170, 176, 188))
        _draw_lightning(draw, cx, cy)
    elif weather_main == "Snow":
        _draw_cloud(draw, cx, cy, color=(225, 232, 240))
        _draw_snowflakes(draw, cx, cy)
    else: 
        _draw_mist(draw, cx, cy)

def _draw_centered(
    draw: ImageDraw.ImageDraw,
    text: str,
    cx: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: Tuple[int, int, int] = (255, 255, 255),
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text((cx - w // 2, y), text, font=font, fill=fill)

def render_weather_card(
    data: dict, precip_probability: int | None = None
) -> bytes:
    city = data.get("name", "—")
    country = data.get("sys", {}).get("country", "")
    location = f"{city}, {country}" if country else city

    weather = data["weather"][0]
    weather_main = weather.get("main", "")
    description = weather["description"].capitalize()
    icon_code = weather.get("icon", "01d")
    is_night = icon_code.endswith("n")

    main = data["main"]
    temp = main["temp"]
    feels_like = main["feels_like"]
    humidity = main["humidity"]
    wind_speed = data.get("wind", {}).get("speed", 0)

    scheme = _pick_scheme(weather_main, is_night)
    img = _gradient_background(scheme)
    draw = ImageDraw.Draw(img)

    light_bg = scheme in ("snow", "mist")
    text_color = (40, 50, 60) if light_bg else (255, 255, 255)
    sub_color = (70, 80, 90) if light_bg else (225, 230, 238)

    font_city = _load_font(46, bold=True)
    _draw_centered(draw, location, WIDTH // 2, 40, font_city, text_color)

    _draw_weather_icon(draw, weather_main, is_night, 230, 250)

    font_temp = _load_font(130, bold=True)
    temp_str = f"{round(temp):+d}°"
    bbox = draw.textbbox((0, 0), temp_str, font=font_temp)
    tw = bbox[2] - bbox[0]
    draw.text((620 - tw // 2, 175), temp_str, font=font_temp, fill=text_color)

    font_desc = _load_font(34)
    _draw_centered(draw, description, WIDTH // 2, 340, font_desc, sub_color)

    panel_top = 410
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rounded_rectangle(
        [40, panel_top, WIDTH - 40, HEIGHT - 30],
        radius=24,
        fill=(0, 0, 0, 70),
    )
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    panel_label_color = (205, 212, 222)
    panel_value_color = (255, 255, 255)

    font_label = _load_font(22)
    font_value = _load_font(32, bold=True)

    stats = [
        ("Ощущается", f"{round(feels_like):+d}°C"),
        ("Влажность", f"{humidity}%"),
        ("Ветер", f"{wind_speed} м/с"),
    ]
    if precip_probability is not None:
        stats.append(("Осадки", f"{precip_probability}%"))

    col_count = len(stats)
    col_width = (WIDTH - 80) // col_count
    for i, (label, value) in enumerate(stats):
        cx = 40 + col_width * i + col_width // 2
        _draw_centered(
            draw, label, cx, panel_top + 24, font_label, panel_label_color
        )
        _draw_centered(
            draw, value, cx, panel_top + 54, font_value, panel_value_color
        )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()