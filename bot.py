import asyncio
import logging
import os
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

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

active_takes = {}

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


@dp.message(Form.waiting_for_take)
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
    }

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
            "Этот тейк устарел, отправь заново.", show_alert=True
        )
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
        else f"Новый тейк ({hashtag}) [Фото]"
    )

    for admin_id in ADMIN_IDS:
        try:
            if take_item["photo_id"]:
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=take_item["photo_id"],
                    caption=preview_text,
                    reply_markup=mod_kb,
                )
            else:
                await bot.send_message(
                    chat_id=admin_id,
                    text=preview_text,
                    reply_markup=mod_kb,
                )
        except Exception as e:
            logging.error(f"Не удалось отправить админу {admin_id}: {e}")

    await callback.message.edit_text(
        f"Тейк с хэштегом {hashtag} отправлен на модерацию!"
    )
    await callback.answer()
    await state.set_state(Form.waiting_for_take)


@dp.callback_query(F.data.startswith(("appr_", "decl_")))
async def process_moderation(callback: CallbackQuery):
    action, unique_key = callback.data.split("_", 1)
    take_item = active_takes.pop(unique_key, None)

    if not take_item:
        await callback.answer(
            "Этот тейк уже обработан или устарел!", show_alert=True
        )
        return

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
            status_line = "\n\n✅ Опубликовано"
            if callback.message.photo:
                await callback.message.edit_caption(
                    caption=f"{callback.message.caption or ''}{status_line}"
                )
            else:
                await callback.message.edit_text(
                    text=f"{callback.message.text or ''}{status_line}"
                )
        except Exception as e:
            await callback.answer(f"Ошибка публикации: {e}", show_alert=True)
            logging.error(f"Ошибка отправки в канал: {e}")
    else:
        await callback.answer("Тейк отклонен.")
        status_line = "\n\n❌ Отклонено"
        if callback.message.photo:
            await callback.message.edit_caption(
                caption=f"{callback.message.caption or ''}{status_line}"
            )
        else:
            await callback.message.edit_text(
                text=f"{callback.message.text or ''}{status_line}"
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
