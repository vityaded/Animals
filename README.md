# Animals Bot

Прототип голосового тренажера для взаємодії з домашнім улюбленцем через телеграм-бота. Архітектура рознесена на хендлери, сервіси, сховище та планувальник нагадувань.

## Залежності
- Python 3.11+
- SQLite (вбудовано в Python) та ffmpeg для конвертації аудіо
- Системні бібліотеки для faster-whisper (опційно OpenBLAS/FAISS)
- pip-пакети: `faster-whisper`, `rapidfuzz`, `python-dotenv`, `aiogram` (за потреби інтеграції з Telegram)

Встановлення залежностей:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # або встановіть пакети вручну
```

Приклад `requirements.txt`:

```
faster-whisper
rapidfuzz
python-dotenv
aiogram
```

## Налаштування середовища
Створіть файл `.env` у корені з параметрами:

```
TELEGRAM_TOKEN=your-telegram-token
DATABASE_PATH=bot.sqlite
WHISPER_MODEL=base
SESSION_TIMES=09:00,18:00
REMINDER_MINUTES_BEFORE=30
DEADLINE_MINUTES_AFTER=90
```

## Запуск
Схема SQLite (`bot/storage/schema.sql`) створюється автоматично під час старту. Запуск демонстраційної логіки:

```bash
python -m bot.main
```

## Планувальник
`bot/scheduler/scheduler.py` планує дві сесії на день (часи беруться з `SESSION_TIMES`) та генерує нагадування за `REMINDER_MINUTES_BEFORE` хвилин до старту й дедлайни через `DEADLINE_MINUTES_AFTER` хвилин після початку.

## Структура контенту
- Рівні: `content/levels/level1.csv`, `level2.csv`, `level3.csv`
- Графіка улюбленця використовує плейсхолдери `assets/pets/cat/<state>.png.placeholder` (happy, sad, sleep). Реальні PNG не зберігаються в репозиторії.

Щоб замінити плейсхолдери на справжні зображення (наприклад, 512x512):

1. Покладіть файли `happy.png`, `sad.png`, `sleep.png` у `assets/pets/cat/`.
2. Видаліть або перейменуйте відповідні `.png.placeholder` файли, якщо вони більше не потрібні.
3. Уникайте додавання двійкових PNG у pull request; додайте їх локально під час деплою.

## Сервіс systemd (рекомендовано)
Файл `deploy/systemd/bot.service` містить базовий юніт. Розташуйте його у `/etc/systemd/system` та відредагуйте шляхи й користувача.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now bot.service
```
