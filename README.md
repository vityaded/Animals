# Animals Bot

Прототип голосового тренажера для взаємодії з домашнім улюбленцем через телеграм-бота. Архітектура рознесена на хендлери, сервіси, сховище та планувальник нагадувань.

## Залежності
- Python 3.11+
- SQLite (вбудовано в Python) та ffmpeg для конвертації аудіо
- espeak-ng для офлайн TTS (генерація озвучки контенту)
- Системні бібліотеки для faster-whisper (опційно OpenBLAS/FAISS)
- pip-пакети: `faster-whisper`, `rapidfuzz`, `python-dotenv`, `aiogram`, `aiosqlite`, `pytest`

Встановлення залежностей:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # або встановіть пакети вручну
```

Для TTS встановіть espeak-ng:

```bash
sudo apt-get update && sudo apt-get install -y espeak-ng
```

Приклад `requirements.txt`:

```
faster-whisper
rapidfuzz
python-dotenv
aiogram
aiosqlite
pytest
```

## Налаштування середовища
Створіть файл `.env` у корені з параметрами:

```
TELEGRAM_TOKEN=your-telegram-token
DATABASE_PATH=bot.sqlite
PETS_ASSETS_ROOT=assets/pets
WHISPER_MODEL=base
SESSION_TIMES=09:00,18:00
REMINDER_MINUTES_BEFORE=30
DEADLINE_MINUTES_AFTER=90
TIMEZONE=Europe/Helsinki
```

## Запуск
Схема SQLite (`bot/storage/schema.sql`) створюється автоматично під час старту. Запуск демонстраційної логіки:

```bash
python -m bot.main
```

Запуск Telegram-версії з aiogram і реальним polling:

```bash
python -m bot.telegram_main
```

## Планувальник
`bot/scheduler/scheduler.py` планує дві сесії на день (часи беруться з `SESSION_TIMES`) та генерує нагадування за `REMINDER_MINUTES_BEFORE` хвилин до старту й дедлайни через `DEADLINE_MINUTES_AFTER` хвилин після початку.

## Структура контенту
- Рівні: `content/levels/level1.csv`, `level2.csv`, `level3.csv`
- Графіка улюбленця знаходиться у `assets/pets/<pet_type>/`. Для кожного стейту використовуйте реальні зображення (`.jpg`, `.jpeg`, `.png`, `.webp`). Плейсхолдери `*.placeholder` ігноруються та не пропонують таких тварин у виборі.

Щоб замінити плейсхолдери на справжні зображення (наприклад, 512x512):

1. Покладіть файли `happy.png`, `sad.png`, `sleep.png` у `assets/pets/cat/`.
2. Видаліть або перейменуйте відповідні `.png.placeholder` файли, якщо вони більше не потрібні.
3. Уникайте додавання двійкових PNG у pull request; додайте їх локально під час деплою.
4. Якщо зображення лежать в іншій директорії на сервері, вкажіть шлях у `.env` через `PETS_ASSETS_ROOT=/abs/path/to/pets`.

## Сервіс systemd (рекомендовано)
Файл `deploy/systemd/bot.service` містить базовий юніт. Розташуйте його у `/etc/systemd/system` та відредагуйте шляхи й користувача.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bot.service
```

## Діагностика зображень
Команда `/debug_pet_assets` (доступна адміністраторам з `ADMIN_TELEGRAM_IDS`) показує, яку директорію з активами бачить бот, який обраний тип тваринки та який файл використовується для поточного стану.
