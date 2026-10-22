import asyncio
import os
import asyncpg
from aiohttp import web

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

TOKEN = "8971026156:AAFxaZEOWaZeipjOgOMtujmLm19c7NRZ_nE"
DB_URI = "postgresql://postgres:kupevchernomkupeauditt3481555@db.ksuduzilrjxrfblavpqc.supabase.co:5432/postgres"

dp = Dispatcher()

# Главное меню
menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📚 Домашка"), KeyboardButton(text="📒 Конспекты")],
        [KeyboardButton(text="🔒 Мои долги"), KeyboardButton(text="➕ Добавить долг")],
        [KeyboardButton(text="➕ Добавить домашку"), KeyboardButton(text="📎 Загрузить конспект")],
    ],
    resize_keyboard=True,
)

# Меню отмены во время ввода
cancel_menu = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
)

class HomeworkForm(StatesGroup):
    subject = State()
    description = State()
    deadline = State()

class DebtForm(StatesGroup):
    title = State()

class NoteForm(StatesGroup):
    content = State()

# Список всех системных кнопок для фильтрации
MAIN_BUTTONS = [
    "📚 Домашка", "📒 Конспекты", "🔒 Мои долги", 
    "➕ Добавить долг", "➕ Добавить домашку", "📎 Загрузить конспект"
]

async def init_db():
    # Открываем соединение правильно через await, используя ссылку DB_URI
    conn = await asyncpg.connect(DB_URI)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS homework (
            id SERIAL PRIMARY KEY,
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            deadline TEXT NOT NULL,
            author_id BIGINT NOT NULL
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS personal_debts (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            title TEXT NOT NULL,
            done INTEGER NOT NULL DEFAULT 0
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            file_id TEXT,
            file_type TEXT,
            author_id BIGINT NOT NULL
        )
    """)
    # Обязательно закрываем соединение в конце
    await conn.close()


# Секретная команда полной очистки базы данных
@dp.message(Command("очистить_базу"))
async def clear_database(message: Message):
    async with asyncpg.connect(DB_URI) as db:
        await db.execute("DROP TABLE IF EXISTS homework")
        await db.execute("DROP TABLE IF EXISTS personal_debts")
        await db.execute("DROP TABLE IF EXISTS notes")
        await db.commit()
    await init_db()
    await message.answer("💥 База данных бота полностью очищена! Все домашки и долги удалены.")

# Хэндлер отмены (Кнопка Назад/Отмена)
@dp.message(F.text == "❌ Отмена")
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нечего отменять. Вы в главном меню.", reply_markup=menu)
        return
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=menu)

# =========================
# СТАРТ (ПРИВЕТСТВИЕ)
# =========================

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()  # Принудительно сбрасываем любые зависшие шаги ввода
    
    await message.answer(
        "Привет! 👋 Наш бот поможет группе координировать учебу и ничего не забыть.\n\n"
        "📖 **Вот что умеют разделы меню:**\n\n"
        "📚 **Домашка** — Показывает полный список актуальных домашних заданий для всей группы. "
        "Любой студент может нажать «➕ Добавить домашку», пошагово ввести предмет, описание и срок сдачи, "
        "и это задание мгновенно увидят все.\n\n"
        "📒 **Конспекты** — Сюда можно скидывать лекции, фотографии доски, шпаргалки или файлы в формате PDF. "
        "Нажмите «📎 Загрузить конспект», отправьте файл, и он сохранится в общую базу материалов.\n\n"
        "🔒 **Мои долги** — Твой личный приватный список. Никто из группы не увидит твои задолженности. "
        "Через кнопку «➕ Добавить долг» ты можешь записать то, что нужно досдать лично тебе. "
        "Как только сдашь работу — просто нажми кнопку «✅ Сдал(а)» под долгом, и он закроется.\n\n"
        "❌ **Отмена** — Если ты случайно нажал кнопку добавления и передумал вводить текст, эта кнопка "
        "всегда вернет тебя в главное меню без сохранения мусора.\n\n"
        "👇 Используй кнопки на клавиатуре ниже, чтобы переключаться между разделами!",
        reply_markup=menu,
        parse_mode="Markdown"  # Этот параметр нужен, чтобы текст с жирным шрифтом отображался красиво
    )

@dp.message(F.text == "➕ Добавить домашку")
async def add_homework(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(HomeworkForm.subject)
    await message.answer("Напиши название предмета.", reply_markup=cancel_menu)

@dp.message(HomeworkForm.subject)
async def homework_subject(message: Message, state: FSMContext):
    if not message.text or message.text in MAIN_BUTTONS:
        await message.answer("Пожалуйста, введите название предмета текстом или нажмите «❌ Отмена»")
        return
    await state.update_data(subject=message.text.strip())
    await state.set_state(HomeworkForm.description)
    await message.answer("Напиши, что задали.", reply_markup=cancel_menu)

@dp.message(HomeworkForm.description)
async def homework_description(message: Message, state: FSMContext):
    if not message.text or message.text in MAIN_BUTTONS:
        await message.answer("Пожалуйста, опишите задание текстом или нажмите «❌ Отмена»")
        return
    await state.update_data(description=message.text.strip())
    await state.set_state(HomeworkForm.deadline)
    await message.answer("Укажи срок сдачи, например 25.10.2026.", reply_markup=cancel_menu)

@dp.message(HomeworkForm.deadline)
async def homework_deadline(message: Message, state: FSMContext):
    if not message.text or message.text in MAIN_BUTTONS:
        await message.answer("Пожалуйста, укажите срок сдачи текстом или нажмите «❌ Отмена»")
        return
    data = await state.get_data()
    async with asyncpg.connect(DB_URI) as db:
        await db.execute(
            "INSERT INTO homework (subject, description, deadline, author_id) VALUES (?, ?, ?, ?)",
            (data["subject"], data["description"], message.text.strip(), message.from_user.id)
        )
        await db.commit()
    await state.clear()
    await message.answer("✅ Домашнее задание добавлено!", reply_markup=menu)

@dp.message(F.text == "📚 Домашка")
async def show_homework(message: Message):
    async with aiosqlite.connect(DB_URI) as db:
        cursor = await db.execute("SELECT id, subject, description, deadline FROM homework ORDER BY id DESC")
        tasks = await cursor.fetchall()
    if not tasks:
        await message.answer("Пока заданий нет.")
        return
    for task_id, subject, description, deadline in tasks:
        await message.answer(f"📚 Задание №{task_id}\n\nПредмет: {subject}\nЗадание: {description}\nСрок: {deadline}")

@dp.message(F.text == "➕ Добавить долг")
async def add_debt(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(DebtForm.title)
    await message.answer("Напиши свой долг.", reply_markup=cancel_menu)

@dp.message(DebtForm.title)
async def save_debt(message: Message, state: FSMContext):
    if not message.text or message.text in MAIN_BUTTONS:
        await message.answer("Пожалуйста, напишите название долга текстом или нажмите «❌ Отмена»")
        return
    async with asyncpg.connect(DB_URI) as db:
        await db.execute("INSERT INTO personal_debts (user_id, title) VALUES (?, ?)", (message.from_user.id, message.text.strip()))
        await db.commit()
    await state.clear()
    await message.answer("🔒 Долг добавлен в список.", reply_markup=menu)

@dp.message(F.text == "🔒 Мои долги")
async def show_debts(message: Message):
    async with asyncpg.connect(DB_URI) as db:
        cursor = await db.execute("SELECT id, title FROM personal_debts WHERE user_id = ? AND done = 0 ORDER BY id DESC", (message.from_user.id,))
        debts = await cursor.fetchall()
    if not debts:
        await message.answer("🎉 У тебя нет открытых долгов!")
        return
    for debt_id, title in debts:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Сдал(а)", callback_data=f"done:{debt_id}")]])
        await message.answer(f"📌 {title}", reply_markup=keyboard)

@dp.callback_query(F.data.startswith("done:"))
async def complete_debt(callback: CallbackQuery):
    debt_id = int(callback.data.split(":")[1]) # Исправленная строка
    async with asyncpg.connect(DB_URI) as db:
        cursor = await db.execute("UPDATE personal_debts SET done = 1 WHERE id = ? AND user_id = ? AND done = 0", (debt_id, callback.from_user.id))
        await db.commit()
        updated = cursor.rowcount
    if updated:
        if isinstance(callback.message, Message):
            await callback.message.edit_text("✅ Долг закрыт!")
        await callback.answer("Готово!")
    else:
        await callback.answer("Долг не найден.", show_alert=True)
# =========================
# РАЗДЕЛ: КОНСПЕКТЫ
# =========================
@dp.message(F.text == "📎 Загрузить конспект")
async def upload_note(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NoteForm.content)
    await message.answer("Отправь следующим сообщением текст, фото или файл конспекта.", reply_markup=cancel_menu)

# Исправленный хэндлер сохранения конспектов (принимает любые типы файлов)
@dp.message(NoteForm.content)
async def save_note(message: Message, state: FSMContext):
    if message.text in MAIN_BUTTONS:
        await message.answer("Пожалуйста, отправьте материал конспекта или нажмите «❌ Отмена»")
        return

    title = message.caption or message.text or "Конспект без описания"
    content = message.text
    file_id = None
    file_type = None

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
        title = message.caption or message.document.file_name or "Документ"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
    elif message.voice:
        file_id = message.voice.file_id
        file_type = "voice"

    async with asyncpg.connect(DB_URI) as db:
        await db.execute(
            "INSERT INTO notes (title, content, file_id, file_type, author_id) VALUES (?, ?, ?, ?, ?)",
            (title[:200], content, file_id, file_type, message.from_user.id)
        )
        await db.commit()

    await state.clear()
    await message.answer("📒 Конспект успешно сохранён для всей группы!", reply_markup=menu)

@dp.message(F.text == "📒 Конспекты")
async def show_notes(message: Message):
    async with asyncpg.connect(DB_URI) as db:
        cursor = await db.execute("SELECT id, title, content, file_id, file_type FROM notes ORDER BY id DESC LIMIT 20")
        notes = await cursor.fetchall()
    if not notes:
        await message.answer("Пока конспектов нет.")
        return
    for note_id, title, content, file_id, file_type in notes:
        await message.answer(f"📒 Конспект №{note_id}\n\nОписание/Название: {title}")
        if content:
            await message.answer(content[:4000])
        if not file_id:
            continue
        if file_type == "photo":
            await message.answer_photo(file_id)
        elif file_type == "document":
            await message.answer_document(file_id)
        elif file_type == "video":
            await message.answer_video(file_id)
        elif file_type == "audio":
            await message.answer_audio(file_id)
        elif file_type == "voice":
            await message.answer_voice(file_id)


# Заглушка веб-сервера для Render
async def handle(request):
    return web.Response(text="Bot is running")

async def main():
    await init_db()
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

    async with Bot(token=TOKEN) as bot:
        await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
