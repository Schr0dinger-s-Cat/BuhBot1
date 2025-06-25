import asyncio
import logging
from tkinter.constants import INSERT

from itit_func import init_logger, read_token_from_file, on_startup
from telegram.ext import (Application, CommandHandler, \
                          MessageHandler, filters, \
                          CallbackQueryHandler, ConversationHandler)
from Handlers import (start, instr, echo, init_dialog, first_state, \
                      message, cancel, insert_file, confirm_task, \
                      fileornot
                      )

from telegram.error import TimedOut, Forbidden
# Инициализация логгера
logger = init_logger(
    name="my_app",
    log_level=logging.DEBUG,
    log_to_console=True,
    log_to_file=True,
    log_file="logs/app.log"
)

FIRST_BUTTON, TASKNAME, DESCRIPTION,  FILEORNOT, INSERTFILE, CONFIRMATION, SEND = range(7)
# Код для кнопки отмены
CANCEL = "cancel"


class TelegramBot:
    def __init__(self):
        self.main()

    async def run(self, token: str):
        try:
            application = (
                Application.builder()
                .token(token)
                .read_timeout(30)  # Таймаут чтения (сек)
                .write_timeout(30)  # Таймаут записи (сек)
                .get_updates_read_timeout(30)  # Таймаут getUpdates.build()
                .build()
            )

            conv_handler = ConversationHandler(
                entry_points=[CommandHandler("new_task", init_dialog)],
                states={
                    FIRST_BUTTON: [
                        CallbackQueryHandler(first_state),
                        CallbackQueryHandler(cancel, pattern=f"^{CANCEL}$")
                    ],
                    TASKNAME: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, message),
                        CallbackQueryHandler(cancel, pattern=f"^{CANCEL}$")
                    ],
                    FILEORNOT: [
                        CallbackQueryHandler(fileornot)
                    ],
                    INSERTFILE: [
                        CallbackQueryHandler(insert_file)
                    ],
                    CONFIRM: [
                        CallbackQueryHandler(confirm_task)
                    ]
                },
                fallbacks=[CommandHandler("cancel", cancel)],
            )
            # Здесь должны быть перечислены все обработчики
            application.add_handler(conv_handler)
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))
            application.add_error_handler(self.error_handler)
            # Для "Поимки" необработанных запросов
            application.add_handler(MessageHandler(filters.ALL, instr))
            # Запуск бота
            try:
                await application.initialize()
                await application.start()
                await application.updater.start_polling()
                self.send_massage_about_start(application)
                print("Бот запущен. Нажмите Ctrl+C для остановки")
                while True:
                    await asyncio.sleep(1)
            except Exception as e:
                print(f"Ошибка: {e}")
            finally:
                await application.stop()
        except Exception as e:
            logger.error(f'Ошибка при запуске бота: {e}')

    async def help_command(self, update, context):
        commands = [
            ("/start", "Начать работу"),
            ("/instr", "Помощь"),
            ("/new_task", "Новая задача"),
        ]

        help_text = "Доступные команды:\n" + "\n".join(
            f"{cmd} - {desc}" for cmd, desc in commands
        )
        await update.message.reply_text(help_text)

    def send_massage_about_start(self, application):
        """Функция для выполнения после инициализации бота"""
        async def startup():
            try:
                await on_startup(application)
            except Exception as e:
                logger.error(f"Ошибка при сохранении списка команд: {e}")
        async def send():
            chat_id = -1002874666761 # !!! Сюда нужно будет сделать получение list из базы данных
            try:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text="Бот был перезапущен! Для начала работы введите /start"
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления о запуске: {e}")

        # Schedule the coroutine to run
        asyncio.create_task(send())

    async def error_handler(update, context, error):
        if isinstance(error, TimedOut):
            logging.warning("Проблемы с интернет-соединением")
        elif isinstance(error, Forbidden):
            logging.warning("Бот заблокирован пользователем")
        else:
            logging.error(f"Неизвестная ошибка: {error}", exc_info=True)

    def main(self):
        # Примеры сообщений
        logger.debug("Это сообщение уровня DEBUG")
        logger.info("Это сообщение уровня INFO")
        logger.warning("Это сообщение уровня WARNING")
        logger.error("Это сообщение уровня ERROR")
        logger.critical("Это сообщение уровня CRITICAL")



if __name__ == "__main__":
    Bot = TelegramBot()
    # Получение токена из файла
    token = read_token_from_file()
    if not token:
        logger.critical("Не удалось получить токен")
    try:
        asyncio.run(Bot.run(token))
    except KeyboardInterrupt:
        print("\nБот остановлен")
