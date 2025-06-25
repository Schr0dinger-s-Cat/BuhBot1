import os
import asyncio
import sqlite3
from datetime import datetime, timedelta
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.error import Forbidden
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters, \
    ConversationHandler, PicklePersistence
from config import PROJECTS, CHAT_IDS, APPROVERS

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Глобальные переменные
BB_FILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BBFiles")
TASK_COUNTER_FILE = os.path.join(BB_FILES_PATH, "task_counter.txt")
DOC_COUNTER_FILE = os.path.join(BB_FILES_PATH, "doc_counter.txt")
STATE_TIMEOUT = 8 * 60 * 60  # 8 часов в секундах

# Состояния для ConversationHandler
(
    SELECT_OBJECT,
    SELECT_PROJECT,
    ENTER_DESCRIPTION,
    CONFIRM_TASK
) = range(4)

# Инициализация БД
def init_db():
    conn = sqlite3.connect('../users.db')
    cursor = conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            username TEXT,
            registration_date TEXT,
            last_activity TEXT,
            is_active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS files (
            file_id TEXT PRIMARY KEY,
            original_name TEXT,
            saved_path TEXT,
            user_id INTEGER,
            task_id TEXT,
            upload_date TEXT,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        );
    ''')
    conn.commit()
    conn.close()


# Функция для получения всех пользователей:
def get_all_users():
    conn = sqlite3.connect('../users.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

# Функция сохранения пользователя
async def save_user(user):
    conn = sqlite3.connect('../users.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR REPLACE INTO users 
            (user_id, first_name, last_name, username, registration_date, last_activity, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        ''', (
            user.id,
            user.first_name,
            user.last_name,
            user.username,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        conn.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения пользователя: {e}")
    finally:
        conn.close()

async def mark_user_inactive(user_id):
    conn = sqlite3.connect('../users.db')
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE users 
            SET is_active = 0
            WHERE user_id = ?
        ''', (user_id,))
        conn.commit()
        logger.info(f"Пользователь {user_id} помечен как неактивный")
    except Exception as e:
        logger.error(f"Ошибка пометки пользователя как неактивного: {e}")
    finally:
        conn.close()

def ensure_directory_exists(path):
    os.makedirs(path, exist_ok=True)


def get_next_id(counter_file):
    ensure_directory_exists(BB_FILES_PATH)
    try:
        with open(counter_file, "r") as f:
            counter = int(f.read().strip())
    except (FileNotFoundError, ValueError):
        counter = 0
    counter += 1
    with open(counter_file, "w") as f:
        f.write(str(counter))
    return f"{counter:08d}"


def get_next_task_id():
    return get_next_id(TASK_COUNTER_FILE)


def get_next_doc_id():
    return get_next_id(DOC_COUNTER_FILE)


def save_task_to_file(task_id, task_data):
    task_date = datetime.now().strftime("%Y-%m-%d")
    task_dir = os.path.join(BB_FILES_PATH, task_date)
    ensure_directory_exists(task_dir)

    filename = f"T{task_id}.txt"
    filepath = os.path.join(task_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"ID: T{task_id}\n")
        f.write(f"Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Объект: {task_data.get('object', 'Не указан')}\n")
        f.write(f"Проект: {task_data.get('project', task_data.get('object', 'Не указан'))}\n")
        f.write(f"Описание: {task_data.get('description', '')}\n")
        f.write(f"Attached Document: {task_data.get('attached_doc', 'None')}\n")


async def download_attachment(context, file_id, original_filename, task_id, user_id):
    """Скачивает вложение с сохранением оригинального имени"""
    try:
        # Создаем папку для файла
        file_dir = os.path.join(BB_FILES_PATH, f"AF_{task_id}")
        os.makedirs(file_dir, exist_ok=True)

        # Сохраняем файл с оригинальным именем
        file_path = os.path.join(file_dir, original_filename)

        file = await context.bot.get_file(file_id)
        await file.download_to_drive(file_path)

        # Сохраняем информацию о файле в БД
        conn = sqlite3.connect('../users.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO files 
            (file_id, original_name, saved_path, user_id, task_id, upload_date)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            file_id,
            original_filename,
            file_path,
            user_id,
            task_id,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ))
        conn.commit()
        conn.close()

        return file_path
    except Exception as e:
        logger.error(f"Ошибка сохранения файла: {e}")
        raise


def read_token_from_file():
    try:
        with open('../TOKEN.txt', 'r') as file:
            return file.read().strip()
    except Exception as e:
        logger.error(f"Ошибка при чтении токена: {e}")
        return None


async def init_user_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Инициализация состояния пользователя"""
    keyboard = [["Создать новую задачу"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(
        "Выберите действие:",
        reply_markup=reply_markup
    )
    return SELECT_OBJECT


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await save_user(user)  # Сохраняем пользователя

    keyboard = [["Создать новую задачу"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"Привет, {user.first_name}! Я бот для создания задач.",
        reply_markup=reply_markup
    )
    return SELECT_OBJECT


async def create_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начало создания задачи"""
    if update.message.text != "Создать новую задачу":
        return SELECT_OBJECT

    text = "Выберите объект учета:"
    objects = list(PROJECTS.keys())
    keyboard = [[obj] for obj in objects if obj != "Test"]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)
    return SELECT_PROJECT


async def select_project(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор проекта для объекта"""
    selected_object = update.message.text
    context.user_data['object'] = selected_object
    context.user_data['last_activity'] = datetime.now().timestamp()

    projects = PROJECTS.get(selected_object, [])

    if not projects:
        context.user_data['project'] = selected_object
        await update.message.reply_text(
            "Напишите описание проблемы (можно с вложениями):",
            reply_markup=ReplyKeyboardRemove()
        )
        return ENTER_DESCRIPTION

    text = "Выберите проект:"
    keyboard = [[project] for project in projects]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(text, reply_markup=reply_markup)
    return ENTER_DESCRIPTION


async def enter_description(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод описания проблемы"""
    if 'object' in context.user_data and 'project' not in context.user_data:
        context.user_data['project'] = update.message.text

    context.user_data['last_activity'] = datetime.now().timestamp()

    # Сохраняем текст описания, даже если есть вложение
    context.user_data['description'] = update.message.text

    # Проверяем, есть ли вложение в этом сообщении
    if update.message.document or update.message.photo:
        # Если есть вложение, сразу переходим к подтверждению
        return await confirm_task(update, context)

    await update.message.reply_text(
        "Вы можете добавить вложение (файл, фото) или нажмите /skip чтобы продолжить без вложения",
        reply_markup=ReplyKeyboardRemove()
    )
    return CONFIRM_TASK


async def process_attachments(update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str, user_id: int):
    """Обрабатывает вложения в сообщении"""
    attached_media = None

    if update.message.document:
        file = update.message.document
        media_type = "document"
    elif update.message.photo:
        file = update.message.photo[-1]
        media_type = "photo"
    elif update.message.video:
        file = update.message.video
        media_type = "video"
    elif update.message.audio:
        file = update.message.audio
        media_type = "audio"
    else:
        return None

    try:
        task_date = datetime.now().strftime("%Y-%m-%d")
        task_dir = os.path.join(BB_FILES_PATH, task_date, f"AF_{task_id}")
        os.makedirs(task_dir, exist_ok=True)

        original_filename = (
            file.file_name if hasattr(file, 'file_name')
            else f"{media_type}_{file.file_unique_id}.{media_type}"
        )

        file_path = os.path.join(task_dir, original_filename)
        tg_file = await context.bot.get_file(file.file_id)
        await tg_file.download_to_drive(file_path)

        attached_media = {
            'type': media_type,
            'original_name': original_filename,
            'saved_path': file_path,
            'telegram_file_id': file.file_id
        }

        conn = sqlite3.connect('../users.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO files 
            (file_id, original_name, saved_path, user_id, task_id, upload_date, media_type)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            file.file_id,
            original_filename,
            file_path,
            user_id,
            task_id,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            media_type
        ))
        conn.commit()
        conn.close()

    except Exception as e:
        logger.error(f"Ошибка обработки вложения: {e}")
        await update.message.reply_text(
            "⚠️ Не удалось обработать вложение. Задача будет создана без него.",
            reply_markup=ReplyKeyboardRemove()
        )

    return attached_media

async def confirm_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение и отправка задачи"""
    try:
        user = update.effective_user
        task_id = get_next_task_id()
        context.user_data['last_activity'] = datetime.now().timestamp()

        # Если это команда /skip, пропускаем добавление вложения
        if update.message.text and update.message.text.startswith('/skip'):
            context.user_data['description'] = context.user_data.get('description', '')
        else:
            # Обновляем описание, если оно было изменено
            if update.message.text:
                context.user_data['description'] = update.message.text

            # Обработка вложений
            attached_media = await process_attachments(update, context, task_id, user.id)
            if attached_media:
                context.user_data['attached_media'] = attached_media

        # Обработка вложений
        if update.message.document:
            file = update.message.document
            media_type = "document"
        elif update.message.photo:
            file = update.message.photo[-1]
            media_type = "photo"
        elif update.message.video:
            file = update.message.video
            media_type = "video"
        elif update.message.audio:
            file = update.message.audio
            media_type = "audio"
        else:
            file = None
            media_type = None

        if file:
            try:
                # Создаем папку для вложений
                task_date = datetime.now().strftime("%Y-%m-%d")
                task_dir = os.path.join(BB_FILES_PATH, task_date, f"AF_{task_id}")
                os.makedirs(task_dir, exist_ok=True)

                # Генерируем имя файла
                original_filename = (
                    file.file_name if hasattr(file, 'file_name')
                    else f"{media_type}_{file.file_unique_id}.{media_type}"
                )

                # Скачиваем файл
                file_path = os.path.join(task_dir, original_filename)
                tg_file = await context.bot.get_file(file.file_id)
                await tg_file.download_to_drive(file_path)

                attached_media = {
                    'type': media_type,
                    'original_name': original_filename,
                    'saved_path': file_path,
                    'telegram_file_id': file.file_id
                }
                context.user_data['attached_media'] = attached_media

                # Сохраняем в БД
                conn = sqlite3.connect('../users.db')
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO files 
                    (file_id, original_name, saved_path, user_id, task_id, upload_date, media_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    file.file_id,
                    original_filename,
                    file_path,
                    user.id,
                    task_id,
                    datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    media_type
                ))
                conn.commit()
                conn.close()

            except Exception as e:
                logger.error(f"Ошибка сохранения вложения: {e}")
                await update.message.reply_text(
                    "⚠️ Вложение не было сохранено. Задача будет создана без него.",
                    reply_markup=ReplyKeyboardRemove()
                )

        # Если проект не был выбран
        if 'project' not in context.user_data:
            context.user_data['project'] = context.user_data['object']

        # Сохраняем задачу в файл
        save_task_to_file(task_id, context.user_data)

        # Формируем сообщение
        task_message = (
            f"🆔 <b>ID задачи:</b> T{task_id}\n"
            f"👤 <b>Автор:</b> {user.mention_html()}\n"
            f"🏢 <b>Объект:</b> {context.user_data.get('object', 'Не указан')}\n"
            f"📂 <b>Проект:</b> {context.user_data.get('project', 'Не указан')}\n"
            f"📝 <b>Описание:</b> {context.user_data['description']}"
        )

        if attached_media:
            task_message += f"\n📎 <b>Вложение:</b> {attached_media['original_name']} ({attached_media['type']})"

        # Создаем кнопки
        keyboard = [
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"accept_{task_id}"),
                InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{task_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Получаем chat_id для проекта
        project = context.user_data.get('project')
        chat_id = CHAT_IDS.get(project)

        # Пытаемся отправить в чат проекта
        sent_to_project = False
        if chat_id:
            try:
                if attached_media:
                    # Выбираем метод отправки по типу медиа
                    send_method = {
                        'document': context.bot.send_document,
                        'photo': context.bot.send_photo,
                        'video': context.bot.send_video,
                        'audio': context.bot.send_audio
                    }.get(attached_media['type'])

                    await send_method(
                        chat_id=chat_id,
                        caption=task_message,
                        reply_markup=reply_markup,
                        parse_mode='HTML',
                        **{attached_media['type']: attached_media['telegram_file_id']}
                    )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=task_message,
                        reply_markup=reply_markup,
                        parse_mode='HTML'
                    )
                sent_to_project = True
            except Exception as e:
                logger.error(f"Ошибка отправки в чат проекта {project} (ID: {chat_id}): {e}")

        # Если не удалось отправить в чат проекта, пробуем тестовый чат
        if not sent_to_project:
            test_chat_id = CHAT_IDS.get("Test")
            if test_chat_id:
                try:
                    error_msg = f"⚠️ Не удалось отправить в чат проекта {project}\n\n" + task_message

                    if attached_media:
                        await context.bot.send_document(
                            chat_id=test_chat_id,
                            caption=error_msg,
                            reply_markup=reply_markup,
                            parse_mode='HTML',
                            document=attached_media['telegram_file_id']
                        )
                    else:
                        await context.bot.send_message(
                            chat_id=test_chat_id,
                            text=error_msg,
                            reply_markup=reply_markup,
                            parse_mode='HTML'
                        )

                    logger.info(f"Задача {task_id} отправлена в тестовый чат")
                except Exception as e:
                    logger.critical(f"Не удалось отправить даже в тестовый чат: {e}")
                    save_failed_task(task_id, context.user_data, str(e))
            else:
                logger.critical("Не настроен тестовый чат!")
                save_failed_task(task_id, context.user_data, "Не настроен тестовый чат")

        # Отправляем подтверждение пользователю
        success_msg = f"""
✅ <b>Задача успешно создана!</b>
━━━━━━━━━━━━━━
🆔 <b>ID:</b> T{task_id}
📂 <b>Проект:</b> {context.user_data.get('project')}
"""
        if attached_media:
            success_msg += f"📎 <b>Вложение:</b> {attached_media['original_name']}\n"

        if not sent_to_project:
            success_msg += "\n⚠️ <i>Задача не была отправлена в группу проекта. Администратор уведомлен.</i>"

        await update.message.reply_text(
            success_msg,
            parse_mode='HTML',
            reply_markup=ReplyKeyboardRemove()
        )

    except Exception as e:
        logger.error(f"Критическая ошибка при создании задачи: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ Произошла критическая ошибка. Пожалуйста, попробуйте позже.",
            reply_markup=ReplyKeyboardRemove()
        )

    return await init_user_state(update, context)


def save_failed_task(task_id: str, task_data: dict, error: str):
    """Сохраняет задачу, которую не удалось отправить"""
    try:
        fail_dir = os.path.join(BB_FILES_PATH, "failed_tasks")
        os.makedirs(fail_dir, exist_ok=True)

        filename = f"FAILED_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(fail_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(f"Ошибка: {error}\n\n")
            f.write(f"ID задачи: T{task_id}\n")
            f.write(f"Объект: {task_data.get('object', 'Не указан')}\n")
            f.write(f"Проект: {task_data.get('project', 'Не указан')}\n")
            f.write(f"Описание: {task_data.get('description', '')}\n")
            if 'attached_media' in task_data:
                f.write(f"Вложение: {task_data['attached_media']['original_name']}\n")

        logger.info(f"Сохранена неудачная задача {task_id} в {filepath}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении неудачной задачи: {e}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки в групповом чате"""
    query = update.callback_query

    try:
        await query.answer()

        if not query.message:
            logger.error("Сообщение недоступно (maybe inaccessible message)")
            return

        user_link = f'<a href="tg://user?id={query.from_user.id}">{query.from_user.first_name} {query.from_user.last_name}</a>'

        if query.data == "accept_task":
            accepted_text = f"\n\n✅ <b>Принял:</b> {user_link}"
            new_text = query.message.text + accepted_text

            keyboard = [[InlineKeyboardButton("✔️ Выполнено", callback_data="complete_task")]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                text=new_text,
                reply_markup=reply_markup,
                parse_mode='HTML'
            )

        elif query.data == "delete_task":
            await query.delete_message()

        elif query.data == "complete_task":
            completed_text = f"\n\n✔️ <b>Выполнил:</b> {user_link}"
            new_text = query.message.text + completed_text

            if query.from_user.id in APPROVERS:
                keyboard = [[InlineKeyboardButton("🔒 Подтвердить", callback_data="approve_task")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(
                    text=new_text,
                    reply_markup=reply_markup,
                    parse_mode='HTML'
                )
            else:
                await query.edit_message_text(
                    text=new_text,
                    parse_mode='HTML'
                )

        elif query.data == "approve_task":
            approved_text = f"\n\n🔒 <b>Подтвердил:</b> {user_link}"
            new_text = query.message.text + approved_text
            await query.edit_message_text(
                text=new_text,
                parse_mode='HTML'
            )

    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}")


async def check_inactive_chats(context: ContextTypes.DEFAULT_TYPE):
    """Проверка неактивных пользователей с обработкой блокировок"""
    inactive_threshold = datetime.now() - timedelta(hours=8)

    conn = sqlite3.connect('../users.db')
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id FROM users 
        WHERE last_activity < ? AND is_active = 1
    ''', (inactive_threshold.strftime('%Y-%m-%d %H:%M:%S'),))

    inactive_users = [row[0] for row in cursor.fetchall()]
    conn.close()

    for user_id in inactive_users:
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text="Ваш сеанс неактивен более 8 часов. Начните снова.",
                reply_markup=ReplyKeyboardRemove()
            )

            keyboard = [["Создать новую задачу"]]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await context.bot.send_message(
                chat_id=user_id,
                text="Выберите действие:",
                reply_markup=reply_markup
            )

            update_last_activity(user_id)
        except Forbidden:
            logger.info(f"Пользователь {user_id} заблокировал бота")
            await mark_user_inactive(user_id)
        except Exception as e:
            logger.error(f"Ошибка оповещения пользователя {user_id}: {e}")

async def init_all_chats(application: Application):
    """Инициализация состояний для всех сохранённых пользователей"""
    try:
        user_ids = get_all_users()
        for user_id in user_ids:
            try:
                keyboard = [["Создать новую задачу"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await application.bot.send_message(
                    chat_id=user_id,
                    text="Бот был перезапущен. Выберите действие:",
                    reply_markup=reply_markup
                )
                # Обновляем время последней активности
                update_last_activity(user_id)
            except Exception as e:
                logger.error(f"Ошибка инициализации чата {user_id}: {e}")
    except Exception as e:
        logger.error(f"Критическая ошибка в init_all_chats: {e}")

def update_last_activity(user_id):
    conn = sqlite3.connect('../users.db')
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE users 
        SET last_activity = ?
        WHERE user_id = ?
    ''', (datetime.now().strftime('%Y-%m-%d %H:%M:%S'), user_id))
    conn.commit()
    conn.close()

async def handle_invalid_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка неверного ввода на разных этапах"""
    current_state = await context.state.get_state()

    if current_state in [SELECT_OBJECT, SELECT_PROJECT, ENTER_DESCRIPTION]:
        await update.message.reply_text(
            "Пожалуйста, используйте кнопки для выбора действия.",
            reply_markup=ReplyKeyboardRemove()
        )
        return current_state

    return ConversationHandler.END


def main():
    init_db()
    """Запуск бота"""
    token = read_token_from_file()
    if not token:
        logger.critical("Не удалось получить токен")
        return

    ensure_directory_exists(BB_FILES_PATH)

    # Используем PicklePersistence для сохранения состояний между перезапусками
    persistence = PicklePersistence(filepath='conversationbot')
    application = Application.builder().token(token).persistence(persistence).build()

    # Добавляем обработчик неверного ввода
    invalid_input_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_invalid_input)

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SELECT_OBJECT: [
                MessageHandler(filters.Regex("^Создать новую задачу$"), create_task),
                invalid_input_handler
            ],
            SELECT_PROJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, select_project),
                invalid_input_handler
            ],
            ENTER_DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_description),
                MessageHandler(filters.PHOTO | filters.Document.ALL, enter_description)
            ],
            CONFIRM_TASK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_task),
                MessageHandler(filters.PHOTO | filters.Document.ALL, confirm_task),
                CommandHandler('skip', confirm_task)
            ]
        },
        fallbacks=[CommandHandler('start', start)],
        name="conversation_handler",
        persistent=True
    )

    application.add_handler(conv_handler)
    application.add_handler(CallbackQueryHandler(button_callback))

    # Добавляем периодическую проверку неактивных чатов
    application.job_queue.run_repeating(check_inactive_chats, interval=3600)  # Проверка каждый час

    # Запускаем бота и инициализируем чаты после запуска
    async def post_init(application: Application):
        await init_all_chats(application)

    # Создаем Updater вручную для доступа к нему
    application.post_init = post_init
    application.run_polling()


if __name__ == '__main__':
    main()