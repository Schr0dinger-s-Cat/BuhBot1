import logging
import os
from logging.handlers import RotatingFileHandler
from telegram.ext import Application
from telegram import BotCommand

# Глобальный логгер для использования в этом модуле
logger = logging.getLogger(__name__)


def init_logger(
        name: str = "my_logger",
        log_level: int = logging.INFO,
        log_to_console: bool = True,
        log_to_file: bool = False,
        log_file: str = "app.log",
        max_file_size: int = 5 * 1024 * 1024,  # 5 MB
        backup_count: int = 3,
        formatter: logging.Formatter = None
) -> logging.Logger:
    """
    Инициализирует и настраивает логгер.
    """
    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Удаляем все существующие обработчики (если есть)
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    if formatter is None:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if log_to_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_file_size,
            backupCount=backup_count,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # ⚡ Включаем логирование для telegram, httpx и apscheduler
    for lib_name in ("telegram", "httpx", "apscheduler"):
        lib_logger = logging.getLogger(lib_name)
        lib_logger.setLevel(log_level)
        if log_to_console:
            lib_logger.addHandler(console_handler)
        if log_to_file:
            lib_logger.addHandler(file_handler)

    return logger


def read_token_from_file(token_file: str = 'TOKEN.txt') -> str:
    """
    Читает токен бота из файла.

    Args:
        token_file (str): Путь к файлу с токеном. По умолчанию 'TOKEN.txt'.

    Returns:
        str: Токен бота или None при ошибке.
    """
    try:
        with open(token_file, 'r') as file:
            return file.read().strip()
    except Exception as e:
        logger.error(f"Ошибка при чтении токена: {e}")
        return None


def on_startup(app, chat_id: int = None):
    app.bot.set_my_commands([
        BotCommand("start", "Запустить бота"),
        BotCommand("help_", "Помощь по командам"),
        BotCommand("new_task", "Создать задачу"),
    ])
