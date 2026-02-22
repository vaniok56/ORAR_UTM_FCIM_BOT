import json
import os
from functions import send_logs

SUPPORTED_LANGS = {
    "ro": "🇷🇴 Română",
    "ru": "🇷🇺 Русский",
    "en": "🇬🇧 English",
}

DEFAULT_LANG = "ro"

# Global locale storage: { "ro": { "key": "value", ... }, ... }
_locales: dict[str, dict[str, str]] = {}

# Weekday names per language
_week_days = {
    "ro": {0: "Luni", 1: "Marţi", 2: "Miercuri", 3: "Joi", 4: "Vineri", 5: "Sâmbătă", 6: "Duminica"},
    "ru": {0: "Понедельник", 1: "Вторник", 2: "Среда", 3: "Четверг", 4: "Пятница", 5: "Суббота", 6: "Воскресенье"},
    "en": {0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday"},
}


def load_locales():
    global _locales
    locales_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locales")

    for lang_code in SUPPORTED_LANGS:
        filepath = os.path.join(locales_dir, f"{lang_code}.json")
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                _locales[lang_code] = json.load(f)
            send_logs(f"Locale loaded: {lang_code} ({len(_locales[lang_code])} keys)", "info")
        except FileNotFoundError:
            send_logs(f"Locale file not found: {filepath}", "error")
            _locales[lang_code] = {}
        except json.JSONDecodeError as e:
            send_logs(f"Invalid JSON in locale file {filepath}: {e}", "error")
            _locales[lang_code] = {}


def get_text(lang: str, key: str, **kwargs) -> str:
    if lang not in _locales:
        lang = DEFAULT_LANG

    text = _locales.get(lang, {}).get(key) or _locales.get(DEFAULT_LANG, {}).get(key)

    if text is None:
        send_logs(f"Missing locale key '{key}' for lang '{lang}'", "warning")
        return "Error: No text to display."

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError) as e:
            send_logs(f"Format error for key '{key}' lang '{lang}': {e}", "warning")
            return "Error: No text to display."

    return text


def get_week_days(lang: str) -> dict:
    return _week_days.get(lang, _week_days[DEFAULT_LANG])


def get_user_lang(sender_id: str) -> str:
    from handlers.db import locate_field
    lang = locate_field(sender_id, "lang")
    if lang and lang in SUPPORTED_LANGS:
        return lang
    return DEFAULT_LANG

