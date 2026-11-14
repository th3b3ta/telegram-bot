import asyncio
import html
import json
import logging
import os
import re
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)
from aiohttp import web

logging.basicConfig(level=logging.INFO)

TOKEN = "9041678651:AAH1cHSxew0eHjB_QGRAoP10bggMMKSq4HY"
CHANNEL_ID = -1004260251593
ADMIN_IDS = [7450045362, 1240436673]
DB_FILE = "takes_db.json"

BOT_URL = "https://t.me/speltikr_bot"
PEREHODNIK_URL = "https://t.me/spletnikkr"

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

TAG_MAP = {
    "help": "#хелп",
    "question": "#вопрос",
    "hate": "#хейт",
    "gossip": "#сплетни",
    "assist": "#помощь",
    "dating": "#знакомства",
}

main_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="💬 Отправить тейк")]],
    resize_keyboard=True,
)


def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("active", {}), set(data.get("processed", []))
        except Exception:
            pass
    return {}, set()


def save_db():
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "active": active_takes,
                    "processed": list(processed_takes)[-500:],
                },
                f,
                ensure_ascii=False,
            )
    except Exception as e:
        logging.error(f"Ошибка сохранения БД: {e}")


active_takes, processed_takes = load_db()


class Form(StatesGroup):
    waiting_for_take = State()


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Чтобы предложить пост в канал, нажми кнопку «💬 Отправить"
        " тейк» ниже:",
        reply_markup=main_kb,
    )


@dp.message(F.text.in_({"💬 Отправить тейк", "Отправить тейк"}))
async def btn_send_take(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_take)
    await message.answer(
        "✍️ Отправь свой тейк (текст или фото с подписью):",
        reply_markup=main_kb,
    )


@dp.message(Form.waiting_for_take)
async def process_take(message: Message, state: FSMContext):
    text = message.text or message.caption
    photo_id = message.photo[-1].file_id if message.photo else None

    if not text and not photo_id:
        await message.answer(
            "Отправь текстовое сообщение или фото с подписью."
        )
        return

    # Сразу сбрасываем состояние, чтобы следующий тейк снова требовал нажатия кнопки
    await state.clear()

    unique_key = f"{message.chat.id}:{message.message_id}"
    active_takes[unique_key] = {
        "text": text or "",
        "photo_id": photo_id,
        "hashtag": "#хейт",
        "admin_messages": [],
    }
    save_db()

    hashtag_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="#хелп", callback_data=f"tag_{unique_key}_help"
                ),
                InlineKeyboardButton(
                    text="#вопрос", callback_data=f"tag_{unique_key}_question"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="#хейт", callback_data=f"tag_{unique_key}_hate"
                ),
                InlineKeyboardButton(
                    text="#сплетни", callback_data=f"tag_{unique_key}_gossip"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="#помощь", callback_data=f"tag_{unique_key}_assist"
                ),
                InlineKeyboardButton(
                    text="#знакомства", callback_data=f"tag_{unique_key}_dating"
                ),
            ],
        ]
    )

    await message.answer(
        "🏷 Выберите тег для анкеты:",
        reply_markup=hashtag_kb,
    )


# Любые сообщения без нажатия кнопки «💬 Отправить тейк» игнорируются с подсказкой
@dp.message()
async def fallback_message(message: Message):
    await message.answer(
        "Чтобы отправить тейк, сначала нажми кнопку «💬 Отправить тейк»"
        " ниже 👇",
        reply_markup=main_kb,
    )


@dp.callback_query(F.data.startswith("tag_"))
async def process_hashtag(callback: CallbackQuery):
    _, unique_key, tag_code = callback.data.split("_", 2)
    take_item = active_takes.get(unique_key)

    if not take_item:
        await callback.answer(
            "Сервер перезагружался, нажми «💬 Отправить тейк» и отправь"
            " заново.",
            show_alert=True,
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    hashtag = TAG_MAP.get(tag_code, "#хейт")
    take_item["hashtag"] = hashtag

    mod_kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить", callback_data=f"appr_{unique_key}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"decl_{unique_key}"
                ),
            ]
        ]
    )

    preview_text = (
        f"Новый тейк ({hashtag}):\n\n{take_item['text']}"
        if take_item["text"]
        else f"Новый тейк ({hashtag}):"
    )

    admin_messages = []
    for admin_id in ADMIN_IDS:
        try:
            if take_item["photo_id"]:
                sent = await bot.send_photo(
                    chat_id=admin_id,
