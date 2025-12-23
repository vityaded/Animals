# Animals Reading Bot

Telegram bot for practicing English reading with a virtual pet (Ukrainian UI).

## Requirements

- Python 3.11+
- ffmpeg (system dependency)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install ffmpeg (example for Ubuntu):

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

Create the environment file:

```bash
cp .env.example .env
```

Initialize the database:

```bash
python -m bot.main --init-db
```

Run the bot:

```bash
python -m bot.main
```

Legacy entrypoint still works:

```bash
python -m bot.telegram_main
```

Optional self-check:

```bash
python tests/self_check.py
```

## Deployment

After updating the systemd unit:

```bash
sudo systemctl daemon-reload
sudo systemctl restart animals_reading
sudo systemctl status animals_reading --no-pager
```
