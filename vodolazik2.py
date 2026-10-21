import asyncio
import os
import aiosqlite
import telebot
import logging
logging.basicConfig(level=logging.INFO)
from aiohttp import web
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

TOKEN = "8971026156:AAFxaZEOWaZeipjOgOMtujmLm19c7NRZ_nE"
DB_NAME = "/data/study.db"

dp = Dispatcher(storage=MemoryStorage())


# -------------------- КНОПКИ --------------------

MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📚 Домашка"),
            KeyboardButton(text="📒 Конспекты"),
        ],
        [
            KeyboardButton(text="🔒 Мои долги"),
            KeyboardButton(text="➕ Добавить долг"),
        ],
        [
            KeyboardButton(text="➕ Добавить домашку"),
            KeyboardButton(text="📎 Добавить конспект"),
        ],
    ],
    resize_keyboard=True,
)

CANCEL_TEXT = "❌ Отмена"
CANCEL_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=CANCEL_TEXT)]
    ],
    resize_keyboard=True,
)


# -------------------- ФОРМЫ ВВОДА --------------------

class HomeworkForm(StatesGroup):
    subject = State()
    description = State()
    deadline = State()


class DebtForm(StatesGroup):
    title = State()


class NoteForm(StatesGroup):
    waiting_for_content = State()


# -------------------- БАЗА ДАННЫХ --------------------

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS homework (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                description TEXT NOT NULL,
                deadline TEXT NOT NULL,
                author_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS personal_debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                done INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                content TEXT,
                file_id TEXT,
                file_type TEXT,
                author_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()


# -------------------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ --------------------

async def is_private_chat(message: Message) -> bool:
    if message.chat.type != "private":
        await message.answer(
            "Пожалуйста, открой мой личный чат и отправь команду /start."
        )
        return False
    return True


async def cancel_current_action(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=MAIN_MENU)


# -------------------- СТАРТ И ОТМЕНА --------------------

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    if not await is_private_chat(message):
        return

    await message.answer(
        "Привет! 👋\n\n"
        "Я бот вашей учебной группы.\n\n"
        "📚 «Домашка» — общий список заданий.\n"
        "📒 «Конспекты» — общие тексты, фото и файлы.\n"
        "🔒 «Мои долги» — только твои личные задолженности.\n\n"
        "Все личные долги привязаны к твоему Telegram-аккаунту.",
        reply_markup=MAIN_MENU,
    )


@dp.message(Command("cancel"))
@dp.message(F.text == CANCEL_TEXT)
async def cancel_action(message: Message, state: FSMContext):
    await cancel_current_action(message, state)


# -------------------- ДОМАШНИЕ ЗАДАНИЯ --------------------

@dp.message(F.text == "➕ Добавить домашку")
async def homework_begin(message: Message, state: FSMContext):
    if not await is_private_chat(message):
        return
    await state.clear()
    await state.set_state(HomeworkForm.subject)
    await message.answer(
        "Напиши название предмета.\nНапример: Компьютерные сети.\n\n"
        "Для отмены отправь /cancel."
    )
    reply_markup=CANCEL_MENU()


@dp.message(HomeworkForm.subject)
async def homework_subject(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Напиши название предмета текстом.")
        return

    await state.update_data(subject=message.text.strip())
    await state.set_state(HomeworkForm.description)
    await message.answer("Напиши, что задали.")


@dp.message(HomeworkForm.description)
async def homework_description(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Опиши задание текстом.")
        return

    await state.update_data(description=message.text.strip())
    await state.set_state(HomeworkForm.deadline)

    await message.answer(
        "Укажи срок сдачи, например 25.10.2026.\n"
        "Если срока нет, напиши «не указан»."
    )


@dp.message(HomeworkForm.deadline)
async def homework_deadline(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Укажи срок сдачи текстом.")
        return

    data = await state.get_data()

    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                """
                INSERT INTO homework (subject, description, deadline, author_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    data.get("subject", "Не указан"),
                    data.get("description", "Не указано"),
                    message.text.strip(),
                    message.from_user.id,
                ),
            )
            await db.commit()
            
        await state.clear()
        await message.answer("✅ Домашнее задание добавлено!", reply_markup=MAIN_MENU)
        
    except Exception as e:
        await message.answer("⚠️ Ошибка сохранения в базу данных. Попробуйте еще раз.")
        logging.error(f"DB Error: {e}")





@dp.message(F.text == "📚 Домашка")
async def homework_list(message: Message):
    if not await is_private_chat(message):
        return

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """
            SELECT id, subject, description, deadline
            FROM homework
            ORDER BY id DESC
            LIMIT 30
            """
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("Пока заданий нет. Нажми «➕ Добавить домашку».")
        return

    for task_id, subject, description, deadline in rows:
        text = (
            f"📚 Задание №{task_id}\n"
            f"Предмет: {subject}\n"
            f"Задание: {description}\n"
            f"Срок сдачи: {deadline}"
        )
        await message.answer(text)


# -------------------- ЛИЧНЫЕ ДОЛГИ --------------------

@dp.message(F.text == "➕ Добавить долг")
async def debt_begin(message: Message, state: FSMContext):
    if not await is_private_chat(message):
        return
    await state.clear()
    await state.set_state(DebtForm.title)
    await message.answer(
        "Напиши, что тебе нужно сдать.\n"
        "Например: «Доделать практическую по математике».\n\n"
        "Этот долг будет виден только в твоём списке."
    )


@dp.message(DebtForm.title)
async def debt_save(message: Message, state: FSMContext):
    if not message.text or not message.text.strip():
        await message.answer("Напиши задолженность текстом.")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT INTO personal_debts (user_id, title) VALUES (?, ?)",
            (message.from_user.id, message.text.strip()),
        )
        await db.commit()

    await state.clear()
    await message.answer(
        "🔒 Личный долг сохранён. Другие участники его не увидят.",
        reply_markup=MAIN_MENU,
    )


@dp.message(F.text == "🔒 Мои долги")
async def debt_list(message: Message):
    if not await is_private_chat(message):
        return

    user_id = message.from_user.id

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """
            SELECT id, title
            FROM personal_debts
            WHERE user_id = ? AND done = 0
            ORDER BY id DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("🎉 У тебя нет открытых долгов!")
        return

    for debt_id, title in rows:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Я сдал(а)",
                        callback_data=f"debt_done:{debt_id}",
                    )
                ]
            ]
        )
        await message.answer(
            f"🔒 Личный долг №{debt_id}\n{title}",
            reply_markup=keyboard,
        )


@dp.callback_query(F.data.startswith("debt_done:"))
async def debt_mark_done(callback: CallbackQuery):
    try:
        debt_id = int(callback.data.split(":", 1)[1])
    except (ValueError, AttributeError):
        await callback.answer("Некорректный запрос.", show_alert=True)
        return

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """
            UPDATE personal_debts
            SET done = 1
            WHERE id = ? AND user_id = ? AND done = 0
            """,
            (debt_id, callback.from_user.id),
        )
        await db.commit()
        updated = cursor.rowcount

    if updated:
        if callback.message:
            await callback.message.edit_text("✅ Долг отмечен как выполненный.")
        await callback.answer("Готово!")
    else:
        await callback.answer(
            "Долг не найден, уже закрыт или принадлежит другому пользователю.",
            show_alert=True,
        )


# -------------------- КОНСПЕКТЫ --------------------

@dp.message(F.text == "📎 Добавить конспект")
async def note_begin(message: Message, state: FSMContext):
    if not await is_private_chat(message):
        return
    await state.clear()
    await state.set_state(NoteForm.waiting_for_content)
    await message.answer(
        "Отправь одним сообщением конспект: текст, фото, PDF или другой файл.\n"
        "Можно добавить подпись к фото или документу.\n\n"
        "Для отмены отправь /cancel."
    )


@dp.message(NoteForm.waiting_for_content)
async def note_save(message: Message, state: FSMContext):
    title = (
        message.caption
        or message.text
        or "Конспект"
    ).strip()[:200]

    content = message.text
    file_id = None
    file_type = None

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
        title = (
            message.caption
            or message.document.file_name
            or "Конспект"
        ).strip()[:200]
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.audio:
        file_id = message.audio.file_id
        file_type = "audio"
    elif message.voice:
        file_id = message.voice.file_id
        file_type = "voice"

    if not content and not file_id:
        await message.answer("Пришли текст, фото, видео, аудио или файл.")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO notes (title, content, file_id, file_type, author_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                title,
                content,
                file_id,
                file_type,
                message.from_user.id,
            ),
        )
        await db.commit()

    await state.clear()
    await message.answer(
        "📒 Конспект сохранён и доступен участникам бота.",
        reply_markup=MAIN_MENU,
    )


@dp.message(F.text == "📒 Конспекты")
async def note_list(message: Message):
    if not await is_private_chat(message):
        return

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """
            SELECT id, title, content, file_id, file_type
            FROM notes
            ORDER BY id DESC
            LIMIT 20
            """
        )
        rows = await cursor.fetchall()

    if not rows:
        await message.answer("Пока конспектов нет. Нажми «📎 Добавить конспект».")
        return

    await message.answer("📒 Последние конспекты группы:")

    for note_id, title, content, file_id, file_type in rows:
        await message.answer(f"Конспект №{note_id}: {title}")

        if content:
            await message.answer(content[:4000])

        if not file_id:
            continue

        try:
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
        except Exception:
            await message.answer(
                "Не получилось отправить вложение. Возможно, файл больше недоступен."
            )


# -------------------- НЕИЗВЕСТНЫЕ СООБЩЕНИЯ --------------------

@dp.message()
async def fallback(message: Message):
    if message.chat.type != "private":
        return
    await message.answer(
        "Выбери действие с помощью кнопок меню.\n"
        "Чтобы отменить ввод, отправь /cancel.",
        reply_markup=MAIN_MENU,
    )


# -------------------- ЗАПУСК --------------------

async def main():
    await init_db()
    
    # Создаем крошечный веб-сервер, чтобы Render не ругался на отсутствие порта
    app = web.Application()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.getenv("PORT", 10000)))
    await site.start()

    async with Bot(token=TOKEN) as bot:
        await dp.start_polling(bot)

