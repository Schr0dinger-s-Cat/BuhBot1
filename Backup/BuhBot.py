import os
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Optional

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
    PicklePersistence,
)
from config import PROJECTS, CHAT_IDS, APPROVERS

# Logging setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Constants
BB_FILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BBFiles")
TASK_COUNTER_FILE = os.path.join(BB_FILES_PATH, "task_counter.txt")
STATE_TIMEOUT = 8 * 60 * 60  # 8 hours in seconds

# Conversation states
SELECT_OBJECT, SELECT_PROJECT, ENTER_DESCRIPTION = range(3)


class DatabaseManager:
    def __init__(self, db_path: str = "users.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            # Проверяем существование таблицы users
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in cursor.fetchall()]

            # Создаем таблицу users, если ее нет
            if not columns:
                cursor.execute(
                    """
                    CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY,
                        first_name TEXT,
                        last_name TEXT,
                        username TEXT,
                        registration_date TEXT,
                        last_activity TEXT,
                        is_active INTEGER DEFAULT 1
                    );
                    """
                )
            elif "is_active" not in columns:
                # Добавляем отсутствующий столбец
                cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")

            # Проверяем таблицу files
            cursor.execute("PRAGMA table_info(files)")
            columns = [column[1] for column in cursor.fetchall()]

            if not columns:
                cursor.execute(
                    """
                    CREATE TABLE files (
                        file_id TEXT PRIMARY KEY,
                        original_name TEXT,
                        saved_path TEXT,
                        user_id INTEGER,
                        task_id TEXT,
                        upload_date TEXT,
                        media_type TEXT,
                        FOREIGN KEY(user_id) REFERENCES users(user_id)
                    );
                    """
                )
            elif "media_type" not in columns:
                cursor.execute("ALTER TABLE files ADD COLUMN media_type TEXT")

            conn.commit()

    def save_user(self, user):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO users 
                (user_id, first_name, last_name, username, registration_date, last_activity, is_active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    user.id,
                    user.first_name,
                    user.last_name,
                    user.username,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                ),
            )

    def mark_user_inactive(self, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET is_active = 0 WHERE user_id = ?", (user_id,)
            )

    def save_file(
            self,
            file_id: str,
            original_name: str,
            saved_path: str,
            user_id: int,
            task_id: str,
            media_type: str,
    ):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO files 
                (file_id, original_name, saved_path, user_id, task_id, upload_date, media_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    file_id,
                    original_name,
                    saved_path,
                    user_id,
                    task_id,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    media_type,
                ),
            )

    def get_all_active_users(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE is_active = 1")
            return [row[0] for row in cursor.fetchall()]

    def update_last_activity(self, user_id: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE users SET last_activity = ? WHERE user_id = ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id),
            )


class TaskManager:
    def __init__(self, files_path: str = BB_FILES_PATH):
        self.files_path = files_path
        self._ensure_directory_exists()

    def _ensure_directory_exists(self):
        os.makedirs(self.files_path, exist_ok=True)

    def get_next_task_id(self) -> str:
        try:
            with open(TASK_COUNTER_FILE, "r") as f:
                counter = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            counter = 0

        counter += 1
        with open(TASK_COUNTER_FILE, "w") as f:
            f.write(str(counter))

        return f"{counter:08d}"

    def save_task_to_file(self, task_id: str, task_data: Dict):
        task_date = datetime.now().strftime("%Y-%m-%d")
        task_dir = os.path.join(self.files_path, task_date)
        os.makedirs(task_dir, exist_ok=True)

        filename = f"T{task_id}.txt"
        filepath = os.path.join(task_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"ID: T{task_id}\n")
            f.write(f"Дата создания: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Объект: {task_data.get('object', 'Не указан')}\n")
            f.write(f"Проект: {task_data.get('project', 'Не указан')}\n")
            f.write(f"Описание: {task_data.get('description', '')}\n")
            if "attached_media" in task_data:
                f.write(
                    f"Вложение: {task_data['attached_media']['original_name']}\n"
                )

    def save_failed_task(self, task_id: str, task_data: Dict, error: str):
        fail_dir = os.path.join(self.files_path, "failed_tasks")
        os.makedirs(fail_dir, exist_ok=True)

        filename = f"FAILED_{task_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        filepath = os.path.join(fail_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"Ошибка: {error}\n\n")
            f.write(f"ID задачи: T{task_id}\n")
            f.write(f"Объект: {task_data.get('object', 'Не указан')}\n")
            f.write(f"Проект: {task_data.get('project', 'Не указан')}\n")
            f.write(f"Описание: {task_data.get('description', '')}\n")
            if "attached_media" in task_data:
                f.write(f"Вложение: {task_data['attached_media']['original_name']}\n")


class TelegramBot:
    def __init__(self):
        self.db = DatabaseManager()
        self.task_manager = TaskManager()

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.db.save_user(user)
        self.db.update_last_activity(user.id)

        keyboard = [["Создать новую задачу"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            f"Привет, {user.first_name}! Я бот для создания задач.",
            reply_markup=reply_markup,
        )
        return SELECT_OBJECT

    async def create_task(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.message.text != "Создать новую задачу":
            return SELECT_OBJECT

        text = "Выберите объект учета:"
        objects = list(PROJECTS.keys())
        keyboard = [[obj] for obj in objects if obj != "Test"]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(text, reply_markup=reply_markup)
        return SELECT_PROJECT

    async def select_project(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        selected_object = update.message.text
        context.user_data["object"] = selected_object
        self.db.update_last_activity(update.effective_user.id)

        projects = PROJECTS.get(selected_object, [])

        if not projects:
            context.user_data["project"] = selected_object
            await update.message.reply_text(
                "Напишите описание проблемы (можно с вложениями):",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ENTER_DESCRIPTION

        text = "Выберите проект:"
        keyboard = [[project] for project in projects]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(text, reply_markup=reply_markup)
        return SELECT_PROJECT

    async def enter_description(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.db.update_last_activity(user.id)

        # If this is a project selection message
        if "project" not in context.user_data and update.message.text in PROJECTS.get(
                context.user_data.get("object", ""), []
        ):
            context.user_data["project"] = update.message.text
            await update.message.reply_text(
                "Напишите описание проблемы (можно с вложениями):",
                reply_markup=ReplyKeyboardRemove(),
            )
            return ENTER_DESCRIPTION

        # Process task description and attachments
        task_id = self.task_manager.get_next_task_id()
        context.user_data["description"] = update.message.text if update.message.text else ""

        attached_media = await self._process_attachments(update, context, task_id, user.id)
        if attached_media:
            context.user_data["attached_media"] = attached_media

        # Ensure project is set
        if "project" not in context.user_data:
            context.user_data["project"] = context.user_data["object"]

        # Save task to file
        self.task_manager.save_task_to_file(task_id, context.user_data)

        # Send task to appropriate chat
        await self._send_task_to_chat(update, context, task_id, attached_media)

        # Confirm to user
        await self._send_confirmation(update, task_id, context.user_data["project"], attached_media)

        # Reset conversation
        return await self._init_user_state(update)

    async def _process_attachments(
            self, update: Update, context: ContextTypes.DEFAULT_TYPE, task_id: str, user_id: int
    ) -> Optional[Dict]:
        if not (update.message.document or update.message.photo):
            return None

        try:
            if update.message.document:
                file = update.message.document
                media_type = "document"
                original_name = file.file_name
            elif update.message.photo:
                file = update.message.photo[-1]
                media_type = "photo"
                original_name = f"photo_{file.file_unique_id}.jpg"

            # Create attachment directory
            task_date = datetime.now().strftime("%Y-%m-%d")
            task_dir = os.path.join(BB_FILES_PATH, task_date, f"AF_{task_id}")
            os.makedirs(task_dir, exist_ok=True)

            # Download file
            file_path = os.path.join(task_dir, original_name)
            tg_file = await context.bot.get_file(file.file_id)
            await tg_file.download_to_drive(file_path)

            # Save to database
            self.db.save_file(
                file.file_id,
                original_name,
                file_path,
                user_id,
                task_id,
                media_type,
            )

            return {
                "type": media_type,
                "original_name": original_name,
                "saved_path": file_path,
                "telegram_file_id": file.file_id,
            }

        except Exception as e:
            logger.error(f"Error saving attachment: {e}")
            await update.message.reply_text(
                "⚠️ Вложение не было сохранено. Задача будет создана без него.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return None

    async def _send_task_to_chat(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
            task_id: str,  # Добавляем task_id в параметры
            attached_media: Optional[Dict],
    ):
        user = update.effective_user
        task_message = (
            f"🆔 <b>ID задачи:</b> T{task_id}\n"
            f"👤 <b>Автор:</b> {user.mention_html()}\n"
            f"🏢 <b>Объект:</b> {context.user_data.get('object', 'Не указан')}\n"
            f"📂 <b>Проект:</b> {context.user_data.get('project', 'Не указан')}\n"
            f"📝 <b>Описание:</b> {context.user_data.get('description', '')}"
        )

        if attached_media:
            task_message += f"\n📎 <b>Вложение:</b> {attached_media['original_name']} ({attached_media['type']})"

        keyboard = [
            [
                InlineKeyboardButton("✅ Принять", callback_data=f"accept_{task_id}"),
                InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{task_id}"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        project = context.user_data.get("project")
        chat_id = CHAT_IDS.get(project)

        try:
            if chat_id:
                if attached_media:
                    # Правильно обрабатываем фото и документы
                    if attached_media["type"] == "photo":
                        await context.bot.send_photo(
                            chat_id=chat_id,
                            photo=attached_media["telegram_file_id"],
                            caption=task_message,
                            reply_markup=reply_markup,
                            parse_mode="HTML"
                        )
                    else:
                        await context.bot.send_document(
                            chat_id=chat_id,
                            document=attached_media["telegram_file_id"],
                            caption=task_message,
                            reply_markup=reply_markup,
                            parse_mode="HTML"
                        )
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=task_message,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
            else:
                raise Exception(f"No chat ID configured for project {project}")
        except Exception as e:
            logger.error(f"Error sending task to chat: {e}")
            await self._send_to_test_chat(
                context,
                task_message,
                attached_media,
                reply_markup,
                project,
                task_id  # Передаем task_id
            )

    async def _send_to_test_chat(
            self,
            context: ContextTypes.DEFAULT_TYPE,
            task_message: str,
            attached_media: Optional[Dict],
            reply_markup: InlineKeyboardMarkup,
            project: str,
            task_id: str  # Добавляем task_id в параметры
    ):
        test_chat_id = CHAT_IDS.get("Test")
        if not test_chat_id:
            logger.critical("Test chat not configured!")
            return

        try:
            error_msg = f"⚠️ Не удалось отправить в чат проекта {project}\n\n{task_message}"

            if attached_media:
                # Правильно обрабатываем фото и документы
                if attached_media["type"] == "photo":
                    await context.bot.send_photo(
                        chat_id=test_chat_id,
                        photo=attached_media["telegram_file_id"],
                        caption=error_msg,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
                else:
                    await context.bot.send_document(
                        chat_id=test_chat_id,
                        document=attached_media["telegram_file_id"],
                        caption=error_msg,
                        reply_markup=reply_markup,
                        parse_mode="HTML"
                    )
            else:
                await context.bot.send_message(
                    chat_id=test_chat_id,
                    text=error_msg,
                    reply_markup=reply_markup,
                    parse_mode="HTML"
                )
        except Exception as e:
            logger.critical(f"Failed to send to test chat: {e}")
            self.task_manager.save_failed_task(
                task_id,  # Теперь task_id доступен
                context.user_data,
                str(e)
            )

    async def _send_confirmation(
            self,
            update: Update,
            task_id: str,
            project: str,
            attached_media: Optional[Dict],
    ):
        success_msg = (
            f"✅ <b>Задача успешно создана!</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🆔 <b>ID:</b> T{task_id}\n"
            f"📂 <b>Проект:</b> {project}\n"
        )

        if attached_media:
            success_msg += f"📎 <b>Вложение:</b> {attached_media['original_name']}\n"

        await update.message.reply_text(
            success_msg,
            parse_mode="HTML",
            reply_markup=ReplyKeyboardRemove(),
        )

    async def _init_user_state(self, update: Update):
        keyboard = [["Создать новую задачу"]]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(
            "Выберите действие:", reply_markup=reply_markup
        )
        return SELECT_OBJECT

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if not query.message:
            logger.error("Message not available")
            return

        user_link = (
            f'<a href="tg://user?id={query.from_user.id}">'
            f"{query.from_user.first_name} {query.from_user.last_name or ''}"
            f"</a>"
        )

        if query.data.startswith("accept_"):
            new_text = query.message.text + f"\n\n✅ <b>Принял:</b> {user_link}"
            keyboard = [
                [InlineKeyboardButton("✔️ Выполнено", callback_data=f"complete_{query.data.split('_')[1]}")]
            ]
            await query.edit_message_text(
                text=new_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )

        elif query.data.startswith("delete_"):
            await query.delete_message()

        elif query.data.startswith("complete_"):
            new_text = query.message.text + f"\n\n✔️ <b>Выполнил:</b> {user_link}"

            if query.from_user.id in APPROVERS:
                keyboard = [
                    [InlineKeyboardButton("🔒 Подтвердить", callback_data=f"approve_{query.data.split('_')[1]}")]
                ]
                await query.edit_message_text(
                    text=new_text,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="HTML",
                )
            else:
                await query.edit_message_text(
                    text=new_text, parse_mode="HTML"
                )

        elif query.data.startswith("approve_"):
            new_text = query.message.text + f"\n\n🔒 <b>Подтвердил:</b> {user_link}"
            await query.edit_message_text(
                text=new_text, parse_mode="HTML"
            )

    async def check_inactive_chats(self, context: ContextTypes.DEFAULT_TYPE):
        inactive_threshold = datetime.now() - timedelta(hours=8)
        inactive_users = self.db.get_all_active_users()

        for user_id in inactive_users:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Ваш сеанс неактивен более 8 часов. Начните снова.",
                    reply_markup=ReplyKeyboardRemove(),
                )

                keyboard = [["Создать новую задачу"]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                await context.bot.send_message(
                    chat_id=user_id,
                    text="Выберите действие:",
                    reply_markup=reply_markup,
                )

                self.db.update_last_activity(user_id)
            except Forbidden:
                logger.info(f"User {user_id} blocked the bot")
                self.db.mark_user_inactive(user_id)
            except Exception as e:
                logger.error(f"Error notifying user {user_id}: {e}")

    async def init_all_chats(self, application: Application):
        try:
            user_ids = self.db.get_all_active_users()
            for user_id in user_ids:
                try:
                    keyboard = [["Создать новую задачу"]]
                    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                    await application.bot.send_message(
                        chat_id=user_id,
                        text="Бот был перезапущен. Выберите действие:",
                        reply_markup=reply_markup,
                    )
                    self.db.update_last_activity(user_id)
                except Exception as e:
                    logger.error(f"Error initializing chat {user_id}: {e}")
        except Exception as e:
            logger.error(f"Critical error in init_all_chats: {e}")

    async def handle_invalid_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        current_state = await context.state.get_state()

        if current_state in [SELECT_OBJECT, SELECT_PROJECT, ENTER_DESCRIPTION]:
            await update.message.reply_text(
                "Пожалуйста, используйте кнопки для выбора действия.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return current_state

        return ConversationHandler.END

    def get_handlers(self):
        invalid_input_handler = MessageHandler(
            filters.TEXT & ~filters.COMMAND, self.handle_invalid_input
        )

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler("start", self.start)],
            states={
                SELECT_OBJECT: [
                    MessageHandler(
                        filters.Regex("^Создать новую задачу$"), self.create_task
                    ),
                    invalid_input_handler,
                ],
                SELECT_PROJECT: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, self.select_project
                    ),
                    invalid_input_handler,
                ],
                ENTER_DESCRIPTION: [
                    MessageHandler(
                        filters.TEXT | filters.PHOTO | filters.Document.ALL,
                        self.enter_description,
                    ),
                ],
            },
            fallbacks=[CommandHandler("start", self.start)],
            name="conversation_handler",
            persistent=True,
        )

        return [
            conv_handler,
            CallbackQueryHandler(self.button_callback),
        ]


def read_token_from_file():
    try:
        with open("../TOKEN.txt", "r") as file:
            return file.read().strip()
    except Exception as e:
        logger.error(f"Error reading token: {e}")
        return None


def main():
    token = read_token_from_file()
    if not token:
        logger.critical("Failed to get token")
        return

    bot = TelegramBot()
    persistence = PicklePersistence(filepath="conversationbot")
    application = Application.builder().token(token).persistence(persistence).build()

    for handler in bot.get_handlers():
        application.add_handler(handler)

    application.job_queue.run_repeating(
        bot.check_inactive_chats, interval=3600
    )  # Check every hour

    async def post_init(application: Application):
        await bot.init_all_chats(application)

    application.post_init = post_init
    application.run_polling()


if __name__ == "__main__":
    main()