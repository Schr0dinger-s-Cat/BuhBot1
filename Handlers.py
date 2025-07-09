from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, error
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, ContextTypes
import os
import json
from datetime import datetime
import sqlite3
from typing import Optional, Any
import logging
from itit_func import logger


def init_database():
    # Инициализация базы данных
    conn = sqlite3.connect('TasksDataBase.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_chat_id TEXT NOT NULL,
        first_name TEXT,
        last_name TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        object TEXT,
        task_name TEXT,
        task_description TEXT,
        file_ids TEXT,
        claimed TEXT,
        desk TEXT,
        answ_id TEXT,
        weeek_task_id TEXT,
        week_url TEXT,
        status TEXT
    )
    ''')
    conn.commit()
    conn.close()

# Создание глобальной переменной ID задачи
t_id = -1

# Состояния
OBJECT, TASKNAME, DESCRIPTION, FILEORNOT, INSERTFILE, CONFIRMATION, SEND, WAITID, WHATTODO, SENDFILE, SEARCHFILE, GETURL = range(12)
# OBJECT - выбор объекта (select_object)
# TASKNAME - ввод имени задачи (taskname)
# DESCRIPTION - ввод описания задачи (taskdescription)
# FILEORNOT - выбор прикрепления файла (fileornot)
# INSERTFILE - прикрепление файлов к задаче (insert_file)
# CONFIRMATION - проверка задачи перед отправкой (confirmation)
# SEND - отправка сообщения в чат бухгалтеров (send)
# WAITID - получение ID задачи (!!!!! СДЕЛАТЬ)
# WHATTODO - выбор действия (whattodo)
# SENDFILE - прикрепление файлов (ответ) (!!!!! СДЕЛАТЬ)
# SEARCHFILE - поиск файлов в базе данных (!!!!! СДЕЛАТЬ)

# Код для кнопки отмены
CANCEL = "cancel"


async def echo(update, context):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Вы написали: " + update.message.text
    )

async def start(update, context):
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Начинаем работу. Выберете действие:")

async def init_dialog(update, context):
    init_database()
    context.user_data.clear()
    keyboard = [[
                    InlineKeyboardButton("Создать новую задачу", callback_data='newtask'),
                    InlineKeyboardButton("Получить файлы задачи", callback_data='searchtask')],
                [
                    InlineKeyboardButton("Загрузить ответ на задачу", callback_data='sendfile'),
                    InlineKeyboardButton("Получить ссылку на задачу", callback_data='GetURLtask')
                ]]
    sent_message = await context.bot.send_message(chat_id=update.effective_chat.id, text = f"Выберете действие", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['last_mess_id'] = sent_message.id
    return WHATTODO


async def whattodo(update, context):
    query = update.callback_query
    await query.answer(text = f'Выполняем действие "{query.data}"') #Отладка
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=context.user_data['last_mess_id']
        )
    except Exception as e:
        logger.error(f'Ошибка при попытке удаления сообщения: {e}')
    if query.data == 'newtask':
        try:
            chat_id = str(update.effective_chat.id)
            # Проверяем и редактируем незавершенные задачи
            conn = sqlite3.connect('TasksDataBase.db')
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id FROM tasks WHERE from_chat_id = ? AND status = 'in_progress'",
                (chat_id,)
            )
            existing_task = cursor.fetchone()

            if existing_task:
                cursor.execute(
                    "UPDATE tasks SET status = 'bad_end' WHERE id = ?",
                    (existing_task[0],)
                )
                conn.commit()

            # Создаем новую задачу
            context.user_data['db_task_id'] = create_empty_row(from_chat_id=chat_id)
            update_column(context.user_data['db_task_id'], 'status', 'in_progress')

            # Генерируем кнопки
            keyboard = generate_buttons('projects.txt')
            keyboard.append([InlineKeyboardButton("🛑 Отмена", callback_data=CANCEL)])
            reply_markup = InlineKeyboardMarkup(keyboard)
            # Отправляем новое сообщение с кнопками
            sent_message = await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Выберите объект:",
                reply_markup=reply_markup
            )
            context.user_data['last_mess_id'] = sent_message.id
            return OBJECT

        except Exception as e:
            logger.error(f"Ошибка при создании задачи: {e}")
            await query.edit_message_text("Ошибка при создании задачи. Попробуйте позже.")
            return ConversationHandler.END
    else:
        context.user_data['mode'] = query.data
        return WAITID



async def stub_handler(update, context, sost):
    # Получаем режим работы из user_data
    mode = context.user_data.get('mode', 'не указан')
    # Отправляем первое сообщение с информацией
    await update.message.reply_text(
        f"Это временная заглушка.\n"
        f"mode = {mode}\n"
        f"sost = {str(sost)}"
    )
    # Создаем клавиатуру с действиями
    keyboard = [
        [
            InlineKeyboardButton("Создать новую задачу", callback_data='newtask'),
            InlineKeyboardButton("Получить файлы задачи", callback_data='searchtask')
        ],
        [
            InlineKeyboardButton("Загрузить ответ на задачу", callback_data='sendfile'),
            InlineKeyboardButton("Получить ссылку на задачу", callback_data='GetURLtask')
        ]
    ]

    # Отправляем второе сообщение с клавиатурой
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Выберите действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['last_mess_id']=sent_message.id
    return WHATTODO

async def select_object(update, context):
    query = update.callback_query
    await query.answer(text = f'Выбрано - {query.data}') # Отладка
    message_id = query.message.message_id
    if query.data == CANCEL:
        return await cancel(update, context)
    context.user_data['last_mess_id'] = message_id
    context.user_data['project'] = query.data
    try:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=message_id
        )
    except Exception as e:
        logger.error(f'Ошибка при попытке удаления сообщения: {e}')
    keyboard = [[InlineKeyboardButton("🛑 Отмена", callback_data=CANCEL)]]
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Отправьте название задачи или нажмите 'Отмена':",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['last_mess_id'] = sent_message.id
    return TASKNAME



async def taskname(update, context):
    if update.callback_query and update.callback_query.data == CANCEL:
        await update.callback_query.answer(text = 'Обработка отмены') # Отладка
        return await cancel(update, context)

    task_name = str(update.message.text)
    try:
        await context.bot.delete_message(
            chat_id = update.effective_chat.id,
            message_id = context.user_data['last_mess_id']
        )
    except Exception as e:
        logger.error(f'Ошибка при поптке удаления сообщения: {e}')

    update_column(context.user_data['db_task_id'], 'task_name', task_name)
    keyboard = [[InlineKeyboardButton("🛑 Отмена", callback_data=CANCEL)]]
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Введите описание задачи:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['last_mess_id'] = sent_message.message_id
    return DESCRIPTION


async def taskdescription(update, context):
    if update.callback_query and update.callback_query.data == CANCEL:
        await update.callback_query.answer('Обработка отмены') # Отладка
        return await cancel(update, context)

    task_description = str(update.message.text)
    update_column(context.user_data['db_task_id'], 'task_description', task_description)

    try:
        await context.bot.delete_message(
            chat_id = update.effective_chat.id,
            message_id = context.user_data['last_mess_id']
        )
    except Exception as e:
        logger.error(f'Ошибка при поптке удаления сообщения: {e}')

    # Обновляем остальные данные
    cur_chat_id = str(update.effective_chat.id)
    update_column(context.user_data['db_task_id'], 'from_chat_id', cur_chat_id)

    first_name = str(update.effective_user.first_name)
    update_column(context.user_data['db_task_id'], 'first_name', first_name)

    last_name = str(update.effective_user.last_name)
    update_column(context.user_data['db_task_id'], 'last_name', last_name)

    obj = get_list('projects.txt')[int(context.user_data['project'])]
    update_column(context.user_data['db_task_id'], 'object', obj)

    keyboard = [
        [InlineKeyboardButton("✅ Да, хочу", callback_data='Y')],
        [InlineKeyboardButton("❌ Нет, не хочу", callback_data='N')]
    ]
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Вы хотите прикрепить файлы?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['last_mess_id'] = sent_message.message_id
    return FILEORNOT


async def fileornot(update, context):
    query = update.callback_query
    await query.answer(f'Ваш выбор - {query.data}')
    if query.data == 'Y':
        keyboard = [
            [InlineKeyboardButton("❌ Не хочу прикреплять файлы", callback_data='SKIP')],
            [InlineKeyboardButton("🛑 Отмена", callback_data=CANCEL)]
        ]
        text = (
            "Отправьте сообщение <b>без текста</b>, прикрепив либо <b>ТОЛЬКО</b> файлы, либо <b>ТОЛЬКО</b> фото, одним сообщением.\n"
            "<b>Если нужно прикрепить и файлы, и фото или более 10 файлов/фото — создайте архив и прикрепите его к сообщению.</b>\n"
            "В случае, если вы не понимаете этот шаг, обратитесь к инструкции."
        )
        try:
            await query.edit_message_text(
                text=text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
        except error as e:
            logger.exception("Ошибка в fileornot при отправке сообщения")
            await query.edit_message_text("Ошибка при отображении инструкции. Попробуйте снова.")
            return await cancel(update, context)
        return INSERTFILE

    elif query.data == 'N':
        return await skip_files(update, context)

    else:
        logger.error('Ошибка при получении ответа на вопрос о прикреплении файла')
        return await cancel(update, context)



async def confirmation(update, context):
    query = update.callback_query
    await query.answer('Продолжаем') # Отладка
    db_task_id = context.user_data.get('db_task_id')
    if not db_task_id:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Ошибка: ID задачи не найден"
        )
        return await cancel(update, context)

    # Подключение к БД
    conn = sqlite3.connect('TasksDataBase.db')
    cursor = conn.cursor()

    try:
        # Получение данных из БД
        cursor.execute(
            "SELECT object, task_name, task_description, from_chat_id, created_at, file_ids FROM tasks WHERE id = ?",
            (db_task_id,)
        )
        task_data = cursor.fetchone()

        if not task_data:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Ошибка: задача не найдена в базе данных"
            )
            return await cancel(update, context)

        object_name, task_name, task_description, user_id, created_at, file_ids_json = task_data

        user = update.effective_user
        user_link = f'<a href="tg://user?id={user.id}">{user.full_name}</a>'

        # Файлы
        try:
            file_ids = json.loads(file_ids_json)
            doc_ids = file_ids.get('doc_ids', [])
            photo_ids = file_ids.get('photo_ids', [])
        except json.JSONDecodeError:
            doc_ids = []
            photo_ids = []

        # Список оригинальных имён файлов
        original_files = []
        log_path = context.user_data.get('log_path')
        if log_path and os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as log_file:
                for line in log_file:
                    if '->' in line:
                        original_name = line.split('->')[0].strip()
                        original_files.append(original_name)

        files_list = "\n".join([f"- {f}" for f in original_files]) or "Нет"

        message_text = (
            f"<b>Подтвердите публикацию задачи:</b>\n\n"
            f"<b>Объект:</b> {object_name}\n"
            f"<b>Имя задачи:</b> {task_name}\n"
            f"<b>Описание:</b> {task_description}\n\n"
            f"<b>Прикрепленные файлы:</b>\n{files_list}\n\n"
            f"Добавил: {user_link}\n"
            f"Дата: {created_at}"
        )

        keyboard = [
            [InlineKeyboardButton("✅ Подтвердить", callback_data='PUBLISH')],
            [InlineKeyboardButton("❌ Отменить", callback_data=CANCEL)]
        ]
        await query.message.edit_reply_markup(reply_markup=None)
        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=message_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        context.user_data['last_mess_id']=sent_message.id
        return SEND

    except Exception as e:
        logger.exception("Ошибка в confirmation")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"Ошибка при формировании подтверждения: {e}"
        )
        return await cancel(update, context)

    finally:
        conn.close()




async def cancel(update, context): # !!! Переделать
    """Обработка отмены"""
    # Обрабатываем как нажатие кнопки, так и текстовую команду
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="Диалог завершен")
    else:
        await update.message.reply_text("Диалог завершен")
    text = f"Выберете действие"
    keyboard = [[
                    InlineKeyboardButton("Создать новую задачу", callback_data='newtask'),
                    InlineKeyboardButton("Получить файлы задачи", callback_data='searchtask')],
                [
                    InlineKeyboardButton("Загрузить ответ на задачу", callback_data='sendfile'),
                    InlineKeyboardButton("Получить ссылку на задачу", callback_data='GetURLtask')
                ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text= text,
        reply_markup=reply_markup
    )
    update_column(context.user_data['db_task_id'], 'status', 'deleted_by_user')
    context.user_data.clear()
    context.user_data['last_mess_id'] = sent_message.id
    return WHATTODO




def generate_buttons(filename):
    buttons_text = get_list(filename)
    paired_buttons = [buttons_text[i:i + 2] for i in range(0, len(buttons_text), 2)]

    keyboard = []

    # Обрабатываем полные пары (первые N-1 рядов)
    for pair in paired_buttons[:-1] or []:  # or [] на случай, если paired_buttons пустой
        row = [InlineKeyboardButton(btn, callback_data=f"{buttons_text.index(btn) + 1}")
               for btn in pair]
        keyboard.append(row)

    # Обрабатываем последний ряд
    if paired_buttons:  # если есть хотя бы один ряд
        last_row = paired_buttons[-1]
        if len(last_row) == 1:  # если последняя кнопка одна
            # Добавляем её по центру
            keyboard.append([InlineKeyboardButton(last_row[0],
                                                  callback_data=f"{buttons_text.index(last_row[0]) + 1}")])
        else:  # если две кнопки в последнем ряду
            row = [InlineKeyboardButton(btn, callback_data=f"{buttons_text.index(btn) + 1}")
                   for btn in last_row]
            keyboard.append(row)

    return keyboard


async def instr(update, context):
    with open('instruction.txt', 'r', encoding='utf-8') as file:
        text = file.read()
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)

def get_list(filename):
    with open(filename, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    return lines


async def skip_files(update, context):
    # Проверка на нажатие кнопок
    if update.callback_query:
        query = update.callback_query
        await query.answer(text=f'Вы выбрали: {query.data}')

        if query.data == 'N':
            # Создаем пустой JSON по тому же шаблону
            tid = context.user_data['db_task_id']
            empty_files_data = {
                "tid": tid,
                "file_count": 0,
                "doc_ids": [],
                "photo_ids": [],
                "timestamp": datetime.now().isoformat()
            }
            files_json = json.dumps(empty_files_data, indent=2)

            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['last_mess_id']
                )
            except Exception as e:
                logger.error(f'Ошибка при попытке удаления сообщения: {e}')

            await query.message.reply_text(
                text=(
                    '✅ Вы решили не прикреплять файлы к задаче.\n\n'
                    f'<b>Информация о файлах:</b>\n<pre>{files_json}</pre>'
                ),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("➡️ Продолжить", callback_data='continue')]
                    ]
                ),
                parse_mode="HTML"
            )

            # Сохраняем пустой JSON в базу
            update_column(context.user_data['db_task_id'], 'file_ids', files_json)
            return CONFIRMATION

async def insert_file(update, context, path: str = '/data/bot_uploads'):
    # Проверка на нажатие кнопок
    if update.callback_query:
        query = update.callback_query
        query.answer(text=f'Вы выбрали: {query.data}')
        if query.data == 'SKIP':
            return CONFIRMATION
        elif query.data == 'NEXT':
            log_path = context.user_data.get('log_path', '[путь не найден]')
            folder = context.user_data.get('save_dir', '[путь не найден]')
            files_json = context.user_data.get('files_json', '{}')

            try:
                log_dict = json.loads(files_json)
            except Exception as e:
                log_dict = {"error": str(e), "raw": files_json}
            try:
                await context.bot.delete_message(
                    chat_id=update.effective_chat.id,
                    message_id=context.user_data['last_mess_id']
                )
            except Exception as e:
                logger.error(f'Ошибка при попытке удаления сообщения: {e}')
            await query.message.reply_text(
                text=(
                    f'✅ Файлы сохранены в папку <code>{folder}</code>\n'
                    f'Лог: <code>{log_path}</code>\n\n'
                    f'<b>Информация о файлах:</b>\n<pre>{json.dumps(log_dict, indent=2, ensure_ascii=False)}</pre>'
                ),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("➡️ Продолжить", callback_data='continue')]
                    ]
                ),
                parse_mode="HTML"
            )
              # показать подтверждение
            update_column(context.user_data['db_task_id'], 'file_ids', files_json)
            return CONFIRMATION # Ожидание нажатия кнопки

        elif query.data == 'Repeat':
            keyboard = [
                [InlineKeyboardButton("❌ Не хочу прикреплять файлы", callback_data='SKIP')],
                [InlineKeyboardButton("🛑 Отмена", callback_data=CANCEL)]
            ]
            await query.message.edit_reply_markup(reply_markup = None)
            await query.message.reply_text(
                text="Отправьте сообщение <b>без текста</b>, прикрепив либо <b>ТОЛЬКО</b> файлы, либо <b>ТОЛЬКО</b> фото, одним сообщением.\n"
                    "<b>Если нужно прикрепить и файлы, и фото или более 10 файлов/фото — создайте архив и прикрепите его к сообщению.</b>\n"
                    "В случае, если вы не понимаете этот шаг, обратитесь к инструкции.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML"
            )
            return INSERTFILE
        else:
            return await cancel(update, context)

    # Проверка: сообщение должно содержать только файлы (без текста)
    if update.message.text or not (update.message.document or update.message.photo):
        keyboard = [
            [InlineKeyboardButton("❌ Не хочу прикреплять файлы", callback_data='SKIP')],
            [InlineKeyboardButton("🛑 Отмена", callback_data=CANCEL)]
        ]
        await update.message.edit_reply_markup(reply_markup=None)
        await update.message.reply_text(
            text="❌ Отправьте сообщение <b>без текста</b>, но с прикреплёнными файлами.",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="HTML"
        )
        return INSERTFILE

    # Обработка файлов
    tid = context.user_data['db_task_id']
    date_folder = datetime.now().strftime("%Y-%m-%d")
    save_dir = os.path.join(path, date_folder, str(tid))
    os.makedirs(save_dir, exist_ok=True)

    logs_dir = os.path.join(path, date_folder, "Logs")
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, f"{tid}.txt")

    # Инициализация структуры для JSON
    if 'files_data' not in context.user_data:
        context.user_data['files_data'] = {
            "tid": tid,
            "file_count": 0,
            "doc_ids": [],
            "photo_ids": [],
            "timestamp": datetime.now().isoformat()
        }

    with open(log_path, 'a', encoding='utf-8') as log_file:
        # Обработка документов
        if update.message.document:
            original_name = update.message.document.file_name
            did = get_d_id()
            new_name = f"{did}{os.path.splitext(original_name)[1]}"
            file = await update.message.document.get_file()
            await file.download_to_drive(os.path.join(save_dir, new_name))
            log_file.write(f"{original_name} -> {new_name}\n")

            # Добавляем информацию о документе
            context.user_data['files_data']['doc_ids'].append(did)
            context.user_data['files_data']['file_count'] += 1
            increase_d_id()

        # Обработка фото
        if update.message.photo:
            photo = update.message.photo[-1]
            original_name = f"photo_{photo.file_unique_id}.jpg"
            did = get_d_id()
            new_name = f"{did}.jpg"
            file = await photo.get_file()
            await file.download_to_drive(os.path.join(save_dir, new_name))
            log_file.write(f"{original_name} -> {new_name}\n")

            # Добавляем информацию о фото
            context.user_data['files_data']['photo_ids'].append(did)
            context.user_data['files_data']['file_count'] += 1
            increase_d_id()

    # Сохраняем пути и JSON в user_data
    context.user_data['save_dir'] = save_dir
    context.user_data['log_path'] = log_path
    context.user_data['files_json'] = json.dumps(context.user_data['files_data'], indent=2)

    # Предлагаем добавить ещё файлы или продолжить
    keyboard = [
        [InlineKeyboardButton("✅ Да, хочу добавить ещё файлы", callback_data='Repeat')],
        [InlineKeyboardButton("❌ Нет, больше файлов нет", callback_data='NEXT')],
        [InlineKeyboardButton("🛑 Отмена", callback_data=CANCEL)]
    ]
    sent_message = await update.message.reply_text(
        text=f"Файлы успешно сохранены. Прикреплено файлов: {context.user_data['files_data']['file_count']}\n"
             f"Хотите добавить ещё файлы?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data['last_mess_id'] = sent_message.id
    return INSERTFILE


async def send(update, context, chat_id: int = -1002874666761):
    # Получаем данные задачи из БД
    query = update.callback_query
    if query.data == CANCEL:
        return await cancel(update, context)
    db_task_id = context.user_data.get('db_task_id')
    if not db_task_id:
        await update.message.reply_text("Ошибка: ID задачи не найден")
        return ConversationHandler.END

    conn = sqlite3.connect('TasksDataBase.db')
    cursor = conn.cursor()

    try:
        # Получаем данные задачи
        cursor.execute(
            "SELECT object, task_name, task_description, from_chat_id, created_at, file_ids FROM tasks WHERE id = ?",
            (db_task_id,)
        )
        task_data = cursor.fetchone()

        if not task_data:
            await update.message.reply_text("Ошибка: задача не найдена в базе данных")
            return ConversationHandler.END

        object_name, task_name, task_description, user_id, created_at, file_ids_json = task_data

        # Получаем информацию о пользователе
        user = update.effective_user
        user_link = f'<a href="tg://user?id={user.id}">{user.full_name}</a>'

        # Парсим JSON с файлами
        try:
            file_ids = json.loads(file_ids_json) #E!!!!!
            doc_ids = file_ids.get('doc_ids', [])
            photo_ids = file_ids.get('photo_ids', [])
        except json.JSONDecodeError:
            doc_ids = []
            photo_ids = []

        # Читаем оригинальные имена файлов из лога
        original_files = []
        log_path = context.user_data.get('log_path')
        if log_path and os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8') as log_file:
                for line in log_file:
                    if '->' in line:
                        original_name = line.split('->')[0].strip()
                        original_files.append(original_name)

        # Формируем список файлов для отображения
        files_list = "\n".join([f"- {f}" for f in original_files])

        # Формируем сообщение для админского чата
        admin_message_text = (
            f"<b>Новая задача:</b>\n\n"
            f"<b>Внутренний ID:</b> {db_task_id}\n"
            f"<b>Объект:</b> {object_name}\n"
            f"<b>Имя задачи:</b> {task_name}\n"
            f"<b>Описание:</b> {task_description}\n\n"
            f"<b>Прикрепленные файлы:</b>\n{files_list}\n\n"
            f"Добавил: {user_link}\n"
            f"Дата: {created_at}"
        )

        # Создаем клавиатуру для админского чата
        admin_keyboard = [
            [InlineKeyboardButton("❌ Удалить", callback_data=f'delete_{db_task_id}')],
            [InlineKeyboardButton("✅ Принять", callback_data=f'accept_{db_task_id}')]
        ]

        # Отправляем сообщение в админский чат
        admin_message = await context.bot.send_message(
            chat_id=chat_id,
            text=admin_message_text,
            reply_markup=InlineKeyboardMarkup(admin_keyboard),
            parse_mode="HTML",
            disable_web_page_preview=True
        )

        # Обновляем статус задачи в БД
        cursor.execute(
            "UPDATE tasks SET status = 'published' WHERE id = ?",
            (db_task_id,)
        )
        conn.commit()

        # Обновляем сообщение в чате пользователя
        user_message_text = (
            f"<b>Задача опубликована</b>\n\n"
            f"<b>Объект:</b> {object_name}\n"
            f"<b>Имя задачи:</b> {task_name}\n"
            f"<b>Описание:</b> {task_description}\n\n"
            f"<b>Прикрепленные файлы:</b>\n{files_list}\n\n"
            f"Дата: {created_at}"
        )

        await context.bot.edit_message_text(
            chat_id=user_id,
            message_id=context.user_data.get('last_mess_id'),
            text=user_message_text,
            reply_markup=None,
            parse_mode="HTML"
        )

        # Отправляем меню действий пользователю
        keyboard = [
            [
                InlineKeyboardButton("Создать новую задачу", callback_data='newtask'),
                InlineKeyboardButton("Получить файлы задачи", callback_data='searchtask')
            ],
            [
                InlineKeyboardButton("Загрузить ответ на задачу", callback_data='sendfile'),
                InlineKeyboardButton("Получить ссылку на задачу", callback_data='GetURLtask')
            ]
        ]

        sent_message = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Выберите действие:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data.clear()
        context.user_data['last_mess_id']=sent_message.message_id
        return WHATTODO

    except Exception as e:
        await query.message.reply_text(f"Ошибка при публикации задачи: {str(e)}")
        return ConversationHandler.END
    finally:
        conn.close()

def get_d_id():
    # Получение текущего значения файлов
    if not os.path.exists('DID.txt'):
        # Создаем файл с default-значением
        with open('DID.txt', 'w', encoding='utf-8') as file:
            file.write("0")  # Например, ID по умолчанию = 0
    # Теперь читаем (гарантировано, что файл существует)
    with open('DID.txt', 'r', encoding='utf-8') as file:
        id = int(file.read())
    return id

def increase_d_id():
    # Увеличение счётчика файлов
    if not os.path.exists('DID.txt'):
        # Создаем файл с default-значением
        with open('DID.txt', 'w', encoding='utf-8') as file:
            file.write("0")  # Например, ID по умолчанию = 0
    # Теперь читаем (гарантировано, что файл существует)
    with open('DID.txt', 'r', encoding='utf-8') as file:
        id = int(file.read())
    with open('DID.txt', 'w', encoding='utf-8') as file:
        file.write(str(id+1))




def create_empty_row(
        desired_id: Optional[int] = None,
        db_path: str = 'TasksDataBase.db',
        table_name: str = 'tasks',
        from_chat_id: str = "unknown"  # Добавляем параметр с default значением
) -> int:
    """
    Создает пустую строку в таблице SQLite.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Всегда включаем обязательные поля
        columns = ["status", "from_chat_id"]
        values = ["draft", from_chat_id]
        placeholders = ["?", "?"]

        if desired_id is not None:
            columns.insert(0, "id")
            values.insert(0, desired_id)
            placeholders.insert(0, "?")

        query = f"""
            INSERT INTO {table_name} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
        """

        cursor.execute(query, values)
        row_id = cursor.lastrowid if desired_id is None else desired_id

        conn.commit()
        return row_id

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def update_column(
        row_id: int,
        column_name: str,
        new_value: Any,
        id_column: str = "id",
        db_path: str = 'TasksDataBase.db',
        table_name: str = "tasks"
) -> bool:
    """
    Обновляет значение конкретного столбца в указанной строке.

    Параметры:
        db_path (str): Путь к файлу базы данных
        table_name (str): Имя таблицы
        row_id (int): ID изменяемой строки
        column_name (str): Название изменяемого столбца
        new_value (Any): Новое значение
        id_column (str): Название столбца с ID (по умолчанию 'id')

    Возвращает:
        bool: True если обновление прошло успешно, False если строка не найдена
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Проверяем существование строки
        cursor.execute(
            f"SELECT 1 FROM {table_name} WHERE {id_column} = ?",
            (row_id,)
        )
        if not cursor.fetchone():
            return False

        # Обновляем значение
        cursor.execute(
            f"UPDATE {table_name} SET {column_name} = ? WHERE {id_column} = ?",
            (new_value, row_id)
        )

        conn.commit()
        return cursor.rowcount > 0

    except sqlite3.Error as e:
        conn.rollback()
        raise sqlite3.Error(f"Ошибка при обновлении: {e}")

    finally:
        conn.close()