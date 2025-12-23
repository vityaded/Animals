from __future__ import annotations

from aiogram import types


# Kid-friendly UI labels (Ukrainian)
BTN_CARE = "Піклуватися"
BTN_PET = "Моя тваринка"


def main_menu_kb() -> types.ReplyKeyboardMarkup:
    # Minimal keyboard: start/continue care session or show pet.
    keyboard = [[types.KeyboardButton(text=BTN_CARE), types.KeyboardButton(text=BTN_PET)]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=False)


PET_LABELS = {
    "panda": "Панда 🐼",
    "dog": "Песик 🐶",
    "dinosaur": "Динозавр 🦖",
    "fox": "Лисичка 🦊",
    "cat": "Котик 🐱",
}


def choose_pet_inline_kb(pet_types: list[str]) -> types.InlineKeyboardMarkup:
    buttons = [
        types.InlineKeyboardButton(text=PET_LABELS.get(p, p.capitalize()), callback_data=f"pick_pet:{p}") for p in pet_types
    ]
    rows: list[list[types.InlineKeyboardButton]] = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i : i + 2])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)


def session_inline_kb() -> types.InlineKeyboardMarkup:
    # Deprecated: keep for compatibility, but do not use in kid UI.
    keyboard = [[types.InlineKeyboardButton(text="Stop", callback_data="session_stop")]]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def repeat_inline_kb() -> types.InlineKeyboardMarkup:
    keyboard = [[types.InlineKeyboardButton(text="🔁 Повторити", callback_data="repeat:current")]]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


CARE_LABELS = {
    "feed": "🍎 Нагодувати",
    "water": "💧 Напоїти",
    "wash": "🫧 Помити",
    "sleep": "😴 Вкласти спати",
    "play": "🎾 Пограти",
    "heal": "🩹 Полікувати",
}


def care_inline_kb(options: list[str]) -> types.InlineKeyboardMarkup:
    buttons = [
        types.InlineKeyboardButton(text=CARE_LABELS.get(opt, opt), callback_data=f"care:{opt}") for opt in options
    ]
    # Arrange in two rows if needed
    rows: list[list[types.InlineKeyboardButton]] = []
    for i in range(0, len(buttons), 2):
        rows.append(buttons[i : i + 2])
    return types.InlineKeyboardMarkup(inline_keyboard=rows)
