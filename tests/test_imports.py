def test_import_telegram_main():
    """Verify telegram entrypoint imports without side effects."""
    import bot.telegram_main  # noqa: F401
