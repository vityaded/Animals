from aiogram import types

from bot.telegram.keyboards import BTN_CARE, BTN_PET, main_menu_kb


def test_main_menu_kb_structure() -> None:
    keyboard = main_menu_kb()

    assert isinstance(keyboard, types.ReplyKeyboardMarkup)
    assert keyboard.resize_keyboard is True
    assert keyboard.one_time_keyboard is False
    assert keyboard.is_persistent is True

    texts = [button.text for row in keyboard.keyboard for button in row]
    assert texts == [BTN_CARE, BTN_PET]
