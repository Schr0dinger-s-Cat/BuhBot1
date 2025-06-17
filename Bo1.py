import logging
import sys
import telegram.constants
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode


# Настройка логгера
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Функция обработки прикрепленных документов

async def handle_document(update: Update, context):
    try:
        # Получаем информацию о файле
        document = update.message.document
        file = await document.get_file()

        # Скачиваем файл
        file_bytes = await file.download_as_bytes()

        # Сохраняем файл
        file_name = document.file_name
        save_path = f'путь/к/папке/{file_name}'
        with open(save_path, 'wb') as f:
            f.write(file_bytes)

        await update.message.reply_text("Документ успешно сохранен")

    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")

# Функция обработки прикрепленных фото

async def handle_photo(update: Update, context):
    try:
        # Получаем файл с максимальным разрешением
        photo = update.message.photo[-1]
        file = await photo.get_file()

        # Скачиваем файл
        file_bytes = await file.download_as_bytes()

        # Сохраняем файл
        file_name = f'photo_{photo.file_id}.jpg'
        save_path = f'путь/к/папке/{file_name}'
        with open(save_path, 'wb') as f:
            f.write(file_bytes)

        await update.message.reply_text("Фотография успешно сохранена")

    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")

# Обработка прикрепленных аудио, видео, голосовых сообщений

async def handle_media(update: Update, context):
    try:
        # Определяем тип файла
        if update.message.audio:
            media = update.message.audio
        elif update.message.video:
            media = update.message.video
        elif update.message.voice:
            media = update.message.voice
        else:
            await update.message.reply_text("Неподдерживаемый тип файла")
        return

        # Получаем файл
        file = await media.get_file()
        file_bytes = await file.download_as_bytes()

        # Сохраняем файл
        file_name = media.file_name or f'{media.file_id}.{media.mime_type.split("/")[-1]}'
        save_path = f'путь/к/папке/{file_name}'
        with open(save_path, 'wb') as f:
            f.write(file_bytes)

        await update.message.reply_text("Медиафайл успешно сохранен")

    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")

def read_token_from_file():
    try:
        with open('TOKEN.txt', 'r') as file:
            return file.read().strip()
    except Exception as e:
        logger.error(f"Ошибка при чтении токена: {e}")
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Привет! Я твой бот.')
# Функция для получения информации о боте
async def getme(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем информацию о боте
        bot_info = await context.bot.get_me()


        # Экранируем все данные
        user_id = str(update.effective_user.id)
        first_name = str(update.effective_user.first_name) or ''
        last_name = str(update.effective_user.last_name) or 'Не указано'
        username = str(update.effective_user.username) or 'Не указано'
        chat_id = str(update.effective_chat.id)
        bot_username = str(bot_info.username) or ''
        bot_first_name = str(bot_info.first_name) or ''

        # Формируем ответ с правильным форматированием
        response = f"<b>Информация о пользователе:</b>\n" \
                   f"    <b>ID</b>: {user_id}\n" \
                   f"    <b>Имя:</b> {first_name}\n" \
                   f"    <b>Фамилия:</b> {last_name}\n" \
                   f"    <b>Username:</b> {username}\n" \
                   f"    <b>Is Bot:</b> {update.effective_user.is_bot}\n\n" \
                   f"<b>Информация о сообщении:</b>\n" \
                   f"    <b>Chat ID:</b> {chat_id}\n" \
                   f"    <b>Тип чата:</b> {update.effective_chat.type}\n" \
                   f"    <b>Сообщение ID:</b> {update.message.message_id}\n" \
                   f"    <b>Дата отправки:</b> {update.message.date}\n\n" \
                   f"<b>Информация о боте:</b>\n" \
                   f"    <b>Bot ID:</b> {bot_info.id}\n" \
                   f"    <b>Bot Username:</b> {bot_username}\n" \
                   f"    <b>Bot First Name:</b> {bot_first_name}\n" \
                   f"    <b>Can Join Groups:</b> {bot_info.can_join_groups}\n" \
                   f"    <b>Can Read All Group Messages:</b> {bot_info.can_read_all_group_messages}\n" \
                   f"    <b>Is Premium:</b> {bot_info.is_premium}\n"

        # Проверяем длину сообщения
        if len(response) > 4096:
            await update.message.reply_text("Сообщение слишком длинное для отправки")
            return

        # Проверяем, что сообщение не пустое
        if not response.strip():
            await update.message.reply_text("Произошла ошибка: ответ пуст")
            return

        # Отправляем ответ с правильным экранированием
        await update.message.reply_text(response, parse_mode=telegram.constants.ParseMode.HTML)

    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {str(e)}")


def main():
    token = read_token_from_file()
    if not token:
        logger.critical("Не удалось получить токен")
        return

    try:
        application = Application.builder().token(token).build()

        # Добавляем обработчики
        application.add_handler(CommandHandler('start', start))
        application.add_handler(CommandHandler('getme', getme))
        application.add_handler(MessageHandler(filters.Document, handle_document))
        application.add_handler(MessageHandler(filters.Photo, handle_photo))
        application.add_handler(MessageHandler(filters.Audio, handle_media))
        application.add_handler(MessageHandler(filters.Video, handle_media))
        application.add_handler(MessageHandler(filters.Voice, handle_media))

        # Запускаем бота
        application.run_polling()

    except Exception as e:
        logger.error(f'Ошибка при запуске бота: {e}')


if __name__ == '__main__':
    main()
