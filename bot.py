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
    Message,
)
from aiohttp import web

# Логирование
logging.basicConfig(level=logging.INFO)

# Конфигурация
TOKEN = "9041678651:AAH1cHSxew0eHjB_QGRAoP10bggMMKSq4HY"
CHANNEL_ID = -1004260251593
ADMIN_IDS = [7450045362, 1240436673]

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Надежное хранилище активных тейков
if "active_takes" not in dp:
    dp["active_takes"] = {}


class Form(StatesGroup):
    waiting_for_take = State()


# Команда /start запускает диалог
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.set_state(Form.waiting_for_take)
    await message.answer(
        "Привет! Отправь мне свой тейк (признание/мысль), и я отправлю его на модерацию админам."
    )


# Прием тейка от пользователя (состояние не сбрасывается, чтобы можно было писать подряд)
@dp.message(Form.waiting_for_take)
async def process_take(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправь текстовое сообщение.")
        return

    take_text = message.text
    unique_key = f"take_{message.chat.id}_{message.message_id}"
    dp["active_takes"][unique_key] = take_text

    kb = InlineKeyboardMarkup(
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

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=f"Новый анонимный тейк на модерацию:\n\n{take_text}",
                reply_markup=kb,
            )
        except Exception as e:
            logging.error(f"Не удалось отправить админу {admin_id}: {e}")

    await message.answer(
        "Твой тейк отправлен на модерацию! Ожидай публикации."
    )


# Модерация администраторами
@dp.callback_query(F.data.startswith(("appr_", "decl_")))
async def process_moderation(callback: CallbackQuery):
    action, unique_key = callback.data.split("_", 1)
    action_type = "approve" if action == "appr" else "decline"

    take_text = dp["active_takes"].pop(unique_key, None)

    if not take_text:
        await callback.answer(
            "Этот тейк уже обработан или устарел!", show_alert=True
        )
        return

    if action_type == "approve":
        try:
            # Точный формат поста: текст + подпись
            post_text = f"{take_text}\n\nПредложка | Переходник\n#хейт"

            # Инлайн-кнопки под постом в канале (ссылки чистые, без пробелов)
            channel_kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="💬 Предложка", url="https://t.me/"
                        ),
                        InlineKeyboardButton(
                            text="#хейт", url="https://t.me/"
                        ),
                    ]
                ]
            )

            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=post_text,
                reply_markup=channel_kb,
            )
            await callback.answer("Тейк успешно опубликован в канале!")
            await callback.message.edit_text(
                f"{callback.message.text}\n\n✅ *Опубликовано*",
                parse_mode="Markdown",
            )
        except Exception as e:
            await callback.answer(f"Ошибка публикации: {e}", show_alert=True)
            logging.error(f"Ошибка отправки в канал: {e}")
    else:
        await callback.answer("Тейк отклонен.")
        await callback.message.edit_text(
            f"{callback.message.text}\n\n❌ *Отклонено*", parse_mode="Markdown"
        )


# Веб-сервер для Render (удерживает Web Service в статусе Live)
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
