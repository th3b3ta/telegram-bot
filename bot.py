import asyncio
import logging
import sys
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

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Твои актуальные данные
TOKEN = "9041678651:AAH1cHSxew0eHjB_QGRAoP10bggMMKSq4HY"
CHANNEL_ID = -1004260251593
ADMIN_IDS = [7450045362, 1240436673]

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Хранилище текстов тейков для модерации
takes_data = {}


class Form(StatesGroup):
    waiting_for_take = State()


# Команда /start
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! Отправь мне свой тейк (признание/мысль), и я отправлю его на модерацию админам."
    )
    await state.set_state(Form.waiting_for_take)


# Обработка текста тейка от пользователя
@dp.message(Form.waiting_for_take)
async def process_take(message: Message, state: FSMContext):
    if not message.text:
        await message.answer("Пожалуйста, отправь текстовое сообщение.")
        return

    take_text = message.text
    take_id = str(message.message_id)

    # Сохраняем текст в память
    takes_data[take_id] = take_text

    # Клавиатура для админов
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить", callback_data=f"approve_{take_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить", callback_data=f"decline_{take_id}"
                ),
            ]
        ]
    )

    # Рассылаем админам
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
    await state.clear()


# Обработка нажатий кнопок админами
@dp.callback_query(F.data.startswith(("approve_", "decline_")))
async def process_moderation(callback: CallbackQuery):
    action, take_id = callback.data.split("_", 1)

    take_text = takes_data.pop(take_id, None)

    if not take_text:
        await callback.answer(
            "Этот тейк уже обработан другим администратором!", show_alert=True
        )
        try:
            await callback.message.edit_text(
                f"{callback.message.text}\n\n⚠️ *Уже обработано*",
                parse_mode="Markdown",
            )
        except Exception:
            pass
        return

    if action == "approve":
        try:
            await bot.send_message(
                chat_id=CHANNEL_ID,
                text=f"💬 *Анонимный тейк:*\n\n{take_text}",
                parse_mode="Markdown",
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


# Веб-сервер для удержания бесплатного Web Service на Render
async def handle(request):
    return web.Response(text="Bot is alive!")


async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()
    logging.info("Web server started on port 10000")


# Главная функция запуска
async def main():
    asyncio.create_task(web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
