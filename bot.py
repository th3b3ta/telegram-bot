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
from aiohttp import web  # Импортируем веб-сервер для дружбы с Render

# Включаем логирование, чтобы видеть всё в консоли Render
logging.basicConfig(level=logging.INFO)

# Твои данные бота и чатов
TOKEN = "7724128913:AAEM698pU8k4y3iV3wXN2aVzR9c7bL1K68w"
CHANNEL_ID = -1004260251593
ADMIN_IDS = [7450045362, 1240436673]

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Словарь для хранения текстов тейков перед модерацией (чтобы админы не конфликтовали)
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


# Ловим текст тейка от пользователя
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

    # Рассылаем всем админам предложение оценить тейк
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


# Обработка нажатий кнопок админами (с защитой от гонки потоков)
@dp.callback_query(F.data.startswith(("approve_", "decline_")))
async def process_moderation(callback: CallbackQuery):
    action, take_id = callback.data.split("_", 1)

    # Безопасно забираем текст из памяти (если другой админ уже нажал кнопку, здесь будет пусто)
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
        # Публикуем в канал
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


# --- ФИКТИВНЫЙ ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle(request):
    return web.Response(text="Bot is alive!")


async def web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render передает порт через переменные окружения, либо используем 10000 по умолчанию
    port = 10000
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")


# Главная функция запуска всего вместе
async def main():
    # Запускаем веб-сервер в фоновом режиме, чтобы Render видел открытый порт
    asyncio.create_task(web_server())

    # Запускаем телеграм-бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
