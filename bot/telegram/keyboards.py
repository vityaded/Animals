from __future__ import annotations

from aiogram import types


def main_menu_kb() -> types.ReplyKeyboardMarkup:
    keyboard = [
        [types.KeyboardButton(text="/menu")],
        [types.KeyboardButton(text="/session 1"), types.KeyboardButton(text="/session 2"), types.KeyboardButton(text="/session 3")],
    ]
    return types.ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def session_inline_kb() -> types.InlineKeyboardMarkup:
    keyboard = [
        [
            types.InlineKeyboardButton(text="Hint", callback_data="session_hint"),
            types.InlineKeyboardButton(text="Stop", callback_data="session_stop"),
        ]
    ]
    return types.InlineKeyboardMarkup(inline_keyboard=keyboard)
