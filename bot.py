import asyncio
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
    await state.set_state(Form.waiting_for_take)
    await message.answer(
        "Привет! Нажми «💬 Отправить тейк» или просто напиши свой текст (можно"
        " с фото) ниже:",
        reply_markup=main_kb,
    )


@dp.message(F.text == "💬 Отправить тейк")
async def btn_send_take(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_take)
    await message.answer(
        "Отправь свой тейк (текст или фото с подписью):",
        reply_markup=main_kb,
    )


@dp.message()
async def process_take(message: Message, state: FSMContext):
    text = message.text or message.caption
    photo_id = message.photo[-1].file_id if message.photo else None

    if not text and not photo_id:
        await message.answer(
            "Отправь текстовое сообщение или фото с подписью."
        )
        return

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


@dp.callback_query(F.data.startswith("tag_"))
async def process_hashtag(callback: CallbackQuery, state: FSMContext):
    _, unique_key, tag_code = callback.data.split("_", 2)
    take_item = active_takes.get(unique_key)

    if not take_item:
        await callback.answer(
            "Сервер перезагружался, отправь тейк ещё раз.", show_alert=True
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
                    photo=take_item["photo_id"],
                    caption=preview_text,
                    reply_markup=mod_kb,
                )
            else:
                sent = await bot.send_message(
                    chat_id=admin_id,
                    text=preview_text,
                    reply_markup=mod_kb,
                )
            admin_messages.append([admin_id, sent.message_id])
        except Exception as e:
            logging.error(f"Не удалось отправить админу {admin_id}: {e}")

    take_item["admin_messages"] = admin_messages
    save_db()

    await callback.message.edit_text(
        f"Тейк с хэштегом {hashtag} отправлен на модерацию!"
    )
    await callback.answer()
    await state.set_state(Form.waiting_for_take)


def extract_from_message(msg: Message) -> dict:
    raw = msg.caption or msg.text or ""
    photo_id = msg.photo[-1].file_id if msg.photo else None
    match = re.match(r"^Новый тейк \((#[^\)]+)\):(?:\n\n(.*))?$", raw, re.S)
    if match:
        hashtag = match.group(1)
        text = (match.group(2) or "").strip()
    else:
        hashtag = "#хейт"
        text = raw.strip()
    return {
        "text": text,
        "photo_id": photo_id,
        "hashtag": hashtag,
        "admin_messages": [],
    }


@dp.callback_query(F.data.startswith(("appr_", "decl_")))
async def process_moderation(callback: CallbackQuery):
    action, unique_key = callback.data.split("_", 1)

    if unique_key in processed_takes:
        await callback.answer(
            "Этот тейк уже обработан другим администратором!", show_alert=True
        )
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        return

    # Сразу блокируем повторные нажатия от второго админа
    processed_takes.add(unique_key)
    take_item = active_takes.pop(unique_key, None)

    if not take_item:
        take_item = extract_from_message(callback.message)

    save_db()

    admin_name = (
        f"@{callback.from_user.username}"
        if callback.from_user.username
        else callback.from_user.full_name
    )

    if action == "appr":
        try:
            body = f"{take_item['text']}\n\n" if take_item["text"] else ""
            post_text = f"{body}Предложка | Переходник\n{take_item['hashtag']}"

            if take_item["photo_id"]:
                await bot.send_photo(
                    chat_id=CHANNEL_ID,
                    photo=take_item["photo_id"],
                    caption=post_text,
                )
            else:
                await bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=post_text,
                )

            await callback.answer("Опубликовано в канале!")
            status_line = f"\n\n✅ Одобрено ({admin_name})"
        except Exception as e:
            processed_takes.discard(unique_key)
            save_db()
            await callback.answer(f"Ошибка публикации: {e}", show_alert=True)
            logging.error(f"Ошибка отправки в канал: {e}")
            return
    else:
        await callback.answer("Тейк отклонен.")
        status_line = f"\n\n❌ Отклонено ({admin_name})"

    base_text = callback.message.caption or callback.message.text or ""
    updated_text = f"{base_text}{status_line}"

    targets = take_item.get("admin_messages") or [
        [callback.message.chat.id, callback.message.message_id]
    ]

    for chat_id, msg_id in targets:
        try:
            if take_item["photo_id"] or callback.message.photo:
                await bot.edit_message_caption(
                    chat_id=chat_id,
                    message_id=msg_id,
                    caption=updated_text,
                    reply_markup=None,
                )
            else:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=updated_text,
                    reply_markup=None,
                )
        except Exception as e:
            logging.error(
                f"Не удалось обновить сообщение у админа {chat_id}: {e}"
            )


async def handle(request):
    return web.Response(text="Bot is alive!")


async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")


async def main():
    asyncio.create_task(web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
