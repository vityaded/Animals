"""
Backward-compatible entrypoint.

Old command used in production:
  python -m bot.telegram_main

New canonical entrypoint:
  python -m bot.main
"""

from bot.main import main

if __name__ == "__main__":
    raise SystemExit(main())
