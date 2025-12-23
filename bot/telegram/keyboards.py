from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Піклуватися"), KeyboardButton(text="Моя тваринка")],
            [KeyboardButton(text="Рівень")],
        ],
        resize_keyboard=True,
    )


def difficulty_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1️⃣ Слова")],
            [KeyboardButton(text="2️⃣ Фрази")],
            [KeyboardButton(text="3️⃣ Речення")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def pet_picker_keyboard(pet_types: list[str]) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=pet.capitalize(), callback_data=f"pet:{pet}")
        for pet in pet_types
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def care_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    labels = {
        "feed": "🍽️ Годувати",
        "water": "🚰 Напоїти",
        "wash": "🧼 Помити",
        "sleep": "😴 Спати",
        "play": "🎾 Грати",
        "heal": "🩹 Лікувати",
    }
    buttons = [
        InlineKeyboardButton(text=labels[option], callback_data=f"care:{option}")
        for option in options
        if option in labels
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
