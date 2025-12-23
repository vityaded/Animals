from __future__ import annotations

from aiogram import types


# Kid-friendly UI labels (Ukrainian)
BTN_READ = "Прочитай"
BTN_PET = "Моя тваринка"


def main_menu_kb() -> types.ReplyKeyboardMarkup:
    # Minimal keyboard for primary school.
    keyboard = [[types.KeyboardButton(text=BTN_READ), types.KeyboardButton(text=BTN_PET)]]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True, one_time_keyboard=False)


def choose_pet_inline_kb() -> types.InlineKeyboardMarkup:
    keyboard = [
        [
            types.InlineKeyboardButton(text="Panda 🐼", callback_data="pet_choose:panda"),
            types.InlineKeyboardButton(text="Dog 🐶", callback_data="pet_choose:dog"),
        ],
        [
            types.InlineKeyboardButton(text="Dinosaur 🦖", callback_data="pet_choose:dinosaur"),
            types.InlineKeyboardButton(text="Fox 🦊", callback_data="pet_choose:fox"),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def session_inline_kb() -> types.InlineKeyboardMarkup:
    # Deprecated: keep for compatibility, but do not use in kid UI.
    keyboard = [[types.InlineKeyboardButton(text="Stop", callback_data="session_stop")]]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)


def care_actions_inline_kb() -> types.InlineKeyboardMarkup:
    # Care actions unlocked after reading 5 units (then again after 10).
    keyboard = [
        [
            types.InlineKeyboardButton(text="🍎 Нагодуй", callback_data="care:feed"),
            types.InlineKeyboardButton(text="💧 Напоїй", callback_data="care:water"),
            types.InlineKeyboardButton(text="🫧 Помий", callback_data="care:wash"),
        ],
        [
            types.InlineKeyboardButton(text="🎾 Пограй", callback_data="care:play"),
            types.InlineKeyboardButton(text="😴 Спати", callback_data="care:sleep"),
            types.InlineKeyboardButton(text="🩹 Полікуй", callback_data="care:heal"),
        ],
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)
