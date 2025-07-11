import asyncio
import logging
from bdb import effective
from tkinter.constants import INSERT

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from itit_func import init_logger, read_token_from_file, on_startup
from telegram.ext import (Application, CommandHandler,
                          MessageHandler, filters,
                          CallbackQueryHandler, ConversationHandler)
from Handlers import (instr, echo,
                      taskname, cancel, insert_file, confirmation,
                      fileornot, taskdescription, select_object, whattodo, init_dialog, send
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

OBJECT, TASKNAME, DESCRIPTION, FILEORNOT, INSERTFILE, CONFIRMATION, SEND, WAITID, WHATTODO, SENDFILE, SEARCHFILE, GETURL = range(12)
CANCEL = "cancel"

class TelegramBot:
    def __init__(self):
        self.main()

    async def run(self, token: str):
        try:
            application = (
                Application.builder()
                .token(token)
                .read_timeout(30)
                .write_timeout(30)
                .get_updates_read_timeout(30)
                .build()
            )

            conv_handler = ConversationHandler(
                entry_points=[
                    CommandHandler("new_task", init_dialog),
                    CallbackQueryHandler(init_dialog, pattern='^start$')
                ],
                states={
                    WHATTODO: [
                        CallbackQueryHandler(whattodo)
                    ],
                    OBJECT: [
                        CallbackQueryHandler(select_object),
                        CallbackQueryHandler(cancel, pattern=f"^{CANCEL}$")
                    ],
                    TASKNAME: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, taskname),
                        CallbackQueryHandler(cancel, pattern=f"^{CANCEL}$")
                    ],
                    DESCRIPTION: [
                        MessageHandler(filters.TEXT & ~filters.COMMAND, taskdescription),
                        CallbackQueryHandler(cancel, pattern=f"^{CANCEL}$")
                    ],
                    FILEORNOT: [
                        CallbackQueryHandler(fileornot),
                        CallbackQueryHandler(cancel, pattern=f"^{CANCEL}$")
                    ],
                    INSERTFILE: [
                        CallbackQueryHandler(insert_file, pattern="^(NEXT|SKIP|Repeat)$"),
                        MessageHandler(filters.PHOTO | filters.Document.ALL, insert_file),
                        CallbackQueryHandler(cancel, pattern=f"^{CANCEL}$")
                    ],
                    CONFIRMATION: [
                        CallbackQueryHandler(confirmation, pattern="^continue$"),
                        CallbackQueryHandler(cancel, pattern=f"^{CANCEL}$")
                    ],
                    SEND: [
                        CallbackQueryHandler(send, pattern="^PUBLISH$"),
                        CallbackQueryHandler(cancel, pattern=f"^{CANCEL}$")
                    ]

                },
                fallbacks=[CommandHandler("cancel", cancel)],
                per_message=False
            )

            application.add_handler(conv_handler)
            application.add_handler(CommandHandler("start", init_dialog))
            application.add_handler(CommandHandler("help", self.help_command))
            application.add_handler(CommandHandler("instr", instr))
            application.add_error_handler(self.error_handler)

            print("Бот запущен. Нажмите Ctrl+C для остановки")

            try:
                await application.initialize()
                await application.start()
                await application.updater.start_polling()
                self.send_massage_about_start(application)

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
        async def startup():
            try:
                await on_startup(application)
            except Exception as e:
                logger.error(f"Ошибка при сохранении списка команд: {e}")

        async def send():
            chat_id = -1002874666761
            try:
                keyboard = [[InlineKeyboardButton("Начать работу", callback_data='start')]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await application.bot.send_message(
                    chat_id=chat_id,
                    text="Бот был перезапущен! Для начала работы введите /start",
                    reply_markup=reply_markup
                )
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления о запуске: {e}")

        asyncio.create_task(send())

    async def error_handler(update, context, error):
        if isinstance(error, TimedOut):
            logging.warning("Проблемы с интернет-соединением")
        elif isinstance(error, Forbidden):
            logging.warning("Бот заблокирован пользователем")
        else:
            logging.error(f"Неизвестная ошибка: {error}", exc_info=True)

    def main(self):
        logger.debug("Это сообщение уровня DEBUG")
        logger.info("Это сообщение уровня INFO")
        logger.warning("Это сообщение уровня WARNING")
        logger.error("Это сообщение уровня ERROR")
        logger.critical("Это сообщение уровня CRITICAL")


if __name__ == "__main__":
    Bot = TelegramBot()
    token = read_token_from_file()
    if not token:
        logger.critical("Не удалось получить токен")
    try:
        asyncio.run(Bot.run(token))
    except KeyboardInterrupt:
        print("\nБот остановлен")