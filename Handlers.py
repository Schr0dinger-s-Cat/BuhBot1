from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, ContextTypes
import os
from datetime import datetime
import sqlite3

from Backup.BuhBut import logger

# Инициализация базы данных
conn = sqlite3.connect('TasksDataBase.db')
cursor = conn.cursor()
cursor.execute('''
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_chat_id TEXT NOT NULL UNIQUE,
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    object TEXT,
    task_name TEXT,
    task_description TEXT,
    file_ids TEXT,
    claimed TEXT,
    desk TEXT,
    answ_id TEXT
)
''')
conn.commit()
conn.close()
# Создание глобальной переменной ID задачи
t_id = -1
# Состояния
FIRST_BUTTON, TASKNAME, DESCRIPTION,  FILEORNOT, INSERTFILE, CONFIRMATION, SEND = range(7)
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
    keyboard = generate_buttons('projects.txt')
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data=CANCEL)])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите первую кнопку:", reply_markup=reply_markup)
    return FIRST_BUTTON

async def first_state(update, context):
    query = update.callback_query
    await query.answer()

    if query.data == CANCEL:
        await cancel(update, context)
        return ConversationHandler.END

    context.user_data['first_choice'] = query.data
    keyboard = [[InlineKeyboardButton("❌ Отмена", callback_data=CANCEL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        text = "Отправьте название задачи или нажмите 'Отмена':",
        reply_markup=reply_markup
    )
    return TASKNAME


async def taskname(update, context):
    if update.callback_query and update.callback_query.data == CANCEL:
        await cancel(update, context)
        return ConversationHandler.END
    task_name = str(update.message.text)
    cur_chat_id = str(update.effective_chat.id)
    first_name = str(update.effective_user.first_name)
    last_name = str(update.effective_user.last_name)
    obj = get_list('projects.txt')[int(context.user_data['first_choice'])]
    date = update.message.date
    context.user_data['task_name'] = task_name
    context.user_data['date'] = date
    context.user_data['obj'] = obj
    context.user_data['cur_chat_id'] = cur_chat_id
    context.user_data['first_name'] = first_name
    context.user_data['last_name'] = last_name
    text= (
        f"Задача: {task_name}\n"
        f"Постановщик: {first_name} {last_name}\n"
        f"Объект: {obj}\n"
        f"Дата обращения: {date}\n"
        f"\n\nВы хотите прикрепить файлы?"
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    keyboard = [
        [InlineKeyboardButton("✅ Да, хочу", callback_data='Y')],
        [InlineKeyboardButton("❌ Нет, не хочу", callback_data='N')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup)
    return DESCRIPTION

async def fileornot(update, context):
    if update.callback_query == 'Y':
        return INSERTFILE
    elif update.callback_query == 'N':
        return CONFIRMATION
    else:
        logger.error(f'Ошибка при получении ответа на вопрос о прикреплении файла')
        await cancel(update, context)


async def cancel(update, context):
    """Обработка отмены"""
    # Обрабатываем как нажатие кнопки, так и текстовую команду
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(text="Действие отменено")
    else:
        await update.message.reply_text("Действие отменено")

    context.user_data.clear()
    return ConversationHandler.END



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


async def insert_file(update, context, path: str):
    # Проверка: сообщение должно содержать только файлы (без текста)

    if update.message.text or not (update.message.document or update.message.photo):
        await update.message.reply_text("❌ Отправьте сообщение **без текста**, но с прикрепленными файлами.")
        return

    # Получаем tid (один для всех файлов в сообщении)
    tid = get_t_id() #Переделать на
    date_folder = datetime.now().strftime("%Y-%m-%d")
    save_dir = os.path.join(path, date_folder, str(tid))
    os.makedirs(save_dir, exist_ok=True)

    # Файл для логов (сохраняем оригинальные и новые имена)
    log_path = os.path.join(path, f"{tid}.txt")

    with open(log_path, 'w', encoding='utf-8') as log_file:
        # Обрабатываем документы
        if update.message.document:
            original_name = update.message.document.file_name
            did = get_d_id()
            new_name = f"{did}{os.path.splitext(original_name)[1]}"  # Сохраняем расширение
            file = await update.message.document.get_file()
            await file.download_to_drive(os.path.join(save_dir, new_name))
            log_file.write(f"{original_name} -> {new_name}\n")
            increase_d_id()  # Увеличиваем did для следующего файла

        # Обрабатываем фото (берем фото наивысшего качества)
        if update.message.photo:
            photo = update.message.photo[-1]
            original_name = f"photo_{photo.file_unique_id}.jpg"
            did = get_d_id()
            new_name = f"{did}.jpg"
            file = await photo.get_file()
            await file.download_to_drive(os.path.join(save_dir, new_name))
            log_file.write(f"{original_name} -> {new_name}\n")
            increase_d_id()

    await update.message.reply_text(f"✅ Файлы сохранены в папку `{save_dir}`.\nЛог: `{log_path}`")
    return CONFIRMATION


def get_d_id():
    if not os.path.exists('DID.txt'):
        # Создаем файл с default-значением
        with open('DID.txt', 'w', encoding='utf-8') as file:
            file.write("0")  # Например, ID по умолчанию = 0
    # Теперь читаем (гарантировано, что файл существует)
    with open('DID.txt', 'r', encoding='utf-8') as file:
        id = int(file.read())
    return id

def increase_d_id():
    if not os.path.exists('DID.txt'):
        # Создаем файл с default-значением
        with open('DID.txt', 'w', encoding='utf-8') as file:
            file.write("0")  # Например, ID по умолчанию = 0
    # Теперь читаем (гарантировано, что файл существует)
    with open('DID.txt', 'r', encoding='utf-8') as file:
        id = int(file.read())
    with open('DID.txt', 'w', encoding='utf-8') as file:
        file.write(str(id+1))