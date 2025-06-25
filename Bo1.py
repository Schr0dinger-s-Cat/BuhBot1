import logging
import sys
import os
import telegram.constants
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode

# Настройка логгера
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Создаем папку для файлов, если её нет
if not os.path.exists('dwfiles'):
    os.makedirs('dwfiles')


async def handle_document(update: Update, context):
    try:
        document = update.message.document
        file = await document.get_file()
        file_bytes = await file.download_as_bytearray()

        file_name = document.file_name
        save_path = f'dwfiles/{file_name}'
        with open(save_path, 'wb') as f:
            f.write(file_bytes)

        await update.message.reply_text("Документ успешно сохранен")
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")
        logger.error(f"Error in handle_document: {e}")


async def handle_photo(update: Update, context):
    try:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_bytes = await file.download_as_bytearray()

        file_name = f'photo_{photo.file_id}.jpg'
        save_path = f'dwfiles/{file_name}'
        with open(save_path, 'wb') as f:
            f.write(file_bytes)

        await update.message.reply_text("Фотография успешно сохранена")
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")
        logger.error(f"Error in handle_photo: {e}")


async def handle_media(update: Update, context):
    try:
        if update.message.audio:
            media = update.message.audio
            file_type = "аудио"
        elif update.message.video:
            media = update.message.video
            file_type = "видео"
        elif update.message.voice:
            media = update.message.voice
            file_type = "голосовое сообщение"
        else:
            await update.message.reply_text("Неподдерживаемый тип файла")
            return

        file = await media.get_file()
        file_bytes = await file.download_as_bytearray()

        if hasattr(media, 'file_name') and media.file_name:
            file_name = media.file_name
        else:
            extension = media.mime_type.split('/')[-1] if hasattr(media, 'mime_type') else 'bin'
            file_name = f'{media.file_id}.{extension}'

        save_path = f'dwfiles/{file_name}'
        with open(save_path, 'wb') as f:
            f.write(file_bytes)

        await update.message.reply_text(f"{file_type.capitalize()} успешно сохранено")
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")
        logger.error(f"Error in handle_media: {e}")



def read_token_from_file():
    try:
        with open('TOKEN.txt', 'r') as file:
            return file.read().strip()
    except Exception as e:
        logger.error(f"Ошибка при чтении токена: {e}")
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Отправляем приветствие и кнопку "Начать"
    welcome_text = "Привет! Нажми кнопку ниже, чтобы начать."
    reply_markup = ReplyKeyboardMarkup([["/start"]], resize_keyboard=True, one_time_keyboard=True)

    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup
    )

    # Убираем клавиатуру после нажатия (если нужно)
    await update.message.reply_text(
        "Теперь ты можешь общаться с ботом!",
        reply_markup=ReplyKeyboardRemove()
    )

async def getme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        bot_info = await context.bot.get_me()

        user = update.effective_user
        chat = update.effective_chat

        response = (
            "<b>Информация о пользователе:</b>\n"
            f"    <b>ID</b>: {user.id}\n"
            f"    <b>Имя:</b> {user.first_name or ''}\n"
            f"    <b>Фамилия:</b> {user.last_name or 'Не указано'}\n"
            f"    <b>Username:</b> @{user.username or 'Не указано'}\n"
            f"    <b>Is Bot:</b> {user.is_bot}\n\n"
            "<b>Информация о сообщении:</b>\n"
            f"    <b>Chat ID:</b> {chat.id}\n"
            f"    <b>Тип чата:</b> {chat.type}\n"
            f"    <b>Сообщение ID:</b> {update.message.message_id}\n"
            f"    <b>Дата отправки:</b> {update.message.date}\n\n"
            "<b>Информация о боте:</b>\n"
            f"    <b>Bot ID:</b> {bot_info.id}\n"
            f"    <b>Bot Username:</b> @{bot_info.username or ''}\n"
            f"    <b>Bot First Name:</b> {bot_info.first_name or ''}\n"
            f"    <b>Can Join Groups:</b> {bot_info.can_join_groups}\n"
            f"    <b>Can Read All Group Messages:</b> {bot_info.can_read_all_group_messages}\n"
            f"    <b>Is Premium:</b> {bot_info.is_premium}\n"
        )

        await update.message.reply_text(response, parse_mode=ParseMode.HTML)
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")
        logger.error(f"Error in getme: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    logger.error(f'Update {update} caused error {error}')

    if update and update.message:
        await update.message.reply_text("Произошла ошибка при обработке сообщения")


def main():
    token = read_token_from_file()
    if not token:
        logger.critical("Не удалось получить токен")
        return

    try:
        application = Application.builder().token(token).build()

        # Обработчики команд
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('getme', getme))

        # Обработчики медиафайлов
        application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.AUDIO | filters.VIDEO | filters.VOICE, handle_media))

        # Обработчик ошибок
        application.add_error_handler(error_handler)

        # Запуск бота
        logger.info("Бот запускается...")
        application.run_polling()

    except Exception as e:
        logger.error(f'Ошибка при запуске бота: {e}')


if __name__ == '__main__':
    main()