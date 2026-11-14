import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

# === НАСТРОЙКИ ===
BOT_TOKEN = "9041678651:AAH1cHSxew0eHjB_QGRAoP10bggMMKSq4HY"  # Твой токен
CHANNEL_ID = "-1004260251593"  # ID твоего приватного канала

# Список Telegram ID всех админов
ADMINS = [7450045362, 1240436673]
# =================

# Словари для хранения данных
admin_reply_targets = {}
takes_data = {}  # Здесь храним сообщение пользователя и выбранный им тег

dp = Dispatcher()


class Form(StatesGroup):
    waiting_for_content = State()


# Главная клавиатура для пользователей
def get_main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="💬 Отправить тейк")]],
        resize_keyboard=True,
    )


# Клавиатура модератора под пересланным сообщением
def get_moderation_kb(user_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Одобрить и опубликовать",
                    callback_data=f"approve_{user_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отказать", callback_data=f"reject_{user_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✉️ Написать пользователю",
                    callback_data=f"reply_{user_id}",
                )
            ],
        ]
    )


@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Привет! 👋 Это бот для отправки анонимных тейков в наш канал.\nНажми кнопку ниже, чтобы отправить сообщение:",
        reply_markup=get_main_kb(),
    )


# Шаг 1: Пользователь нажал "💬 Отправить тейк" -> показываем выбор тегов
@dp.message(F.text == "💬 Отправить тейк")
async def start_take(message: Message, state: FSMContext):
    await state.clear()
    
    tags_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="#хелп", callback_data="tag_#хелп"),
                InlineKeyboardButton(text="#вопрос", callback_data="tag_#вопрос"),
            ],
            [
                InlineKeyboardButton(text="#хейт", callback_data="tag_#хейт"),
                InlineKeyboardButton(text="#сплетни", callback_data="tag_#сплетни"),
            ],
            [
                InlineKeyboardButton(text="#помощь", callback_data="tag_#помощь"),
                InlineKeyboardButton(text="#знакомства", callback_data="tag_#знакомства"),
            ],
        ]
    )

    await message.answer(
        "🏷 <b>Выберите тег для анкеты:</b>",
        reply_markup=tags_keyboard,
        parse_mode="HTML"
    )


# Шаг 2: Пользователь нажал на конкретный тег
@dp.callback_query(F.data.startswith("tag_"))
async def process_tag_selection(callback: CallbackQuery, state: FSMContext):
    chosen_tag = callback.data.split("_", 1)[1]

    await state.update_data(selected_tag=chosen_tag)
    await state.set_state(Form.waiting_for_content)

    await callback.message.edit_text(
        f"Выбран тег: <b>{chosen_tag}</b>\n\n✍️ Теперь напиши текст, который хочешь опубликовать.\n(Можно прикрепить фото или видео с подписью).",
        parse_mode="HTML"
    )
    await callback.answer()


# Шаг 3: Пользователь отправляет контент
@dp.message(Form.waiting_for_content)
async def process_take(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    tag = data.get("selected_tag", "#тейк") 
    
    await state.clear()

    await message.answer(
        "✅ Твой тейк успешно отправлен на модерацию! Ожидай публикации.",
        reply_markup=get_main_kb(),
    )

    # Список для сохранения ID сообщений, отправленных каждому админу
    admin_messages = []

    for admin_id in ADMINS:
        await bot.copy_message(
            chat_id=admin_id,
            from_chat_id=message.chat.id,
            message_id=message.message_id,
        )
        sent_msg = await bot.send_message(
            chat_id=admin_id,
            text=f"📥 Новый тейк (тег: <b>{tag}</b>) от пользователя (ID: `{message.from_user.id}`):",
            reply_markup=get_moderation_kb(message.from_user.id),
            parse_mode="HTML",
        )
        admin_messages.append({"chat_id": admin_id, "message_id": sent_msg.message_id})

    # Сохраняем информацию о тейке И список сообщений всех админов
    takes_data[str(message.message_id)] = {
        "message": message,
        "tag": tag,
        "admin_messages": admin_messages
    }


# Шаг 4: Админ одобряет публикацию
@dp.callback_query(F.data.startswith("approve_"))
async def approve_take(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[1])
    
    # Ищем, какой именно тейк пытаются одобрить
    # Пробегаемся по всем записям в takes_data, чтобы найти нужное сообщение админа
    target_key = None
    take_info = None
    
    for key, info in takes_data.items():
        for am in info["admin_messages"]:
            if am["chat_id"] == callback.message.chat.id and am["message_id"] == callback.message.message_id:
                target_key = key
                take_info = info
                break
        if target_key:
            break

    # Если тейк уже кто-то одобрил или отклонил (его больше нет в памяти)
    if not take_info:
        await callback.answer("⚠️ Этот тейк уже был обработан другим модератором!", show_alert=True)
        await callback.message.edit_text(f"{callback.message.text}\n\n**Статус: УЖЕ ОБРАБОТАН ⚠️**", parse_mode="Markdown")
        return

    # Удаляем из памяти, чтобы никто другой больше не смог его тронуть
    takes_data.pop(target_key, None)

    user_msg = take_info["message"]
    tag = take_info["tag"]

    footer = f'\n\n<a href="https://t.me/speltikr_bot">Предложка</a> | <a href="https://t.me/spletnikkr">Переходник</a>\n{tag}'

    try:
        if user_msg:
            original_text = user_msg.text or user_msg.caption or ""
            full_content = f"{original_text}{footer}"

            if user_msg.text:
                await bot.send_message(chat_id=CHANNEL_ID, text=full_content, parse_mode="HTML")
            elif user_msg.photo:
                await bot.send_photo(chat_id=CHANNEL_ID, photo=user_msg.photo[-1].file_id, caption=full_content, parse_mode="HTML")
            elif user_msg.video:
                await bot.send_video(chat_id=CHANNEL_ID, video=user_msg.video.file_id, caption=full_content, parse_mode="HTML")
            else:
                await bot.copy_message(chat_id=CHANNEL_ID, from_chat_id=callback.message.chat.id, message_id=callback.message.message_id - 1)
        else:
            await bot.copy_message(chat_id=CHANNEL_ID, from_chat_id=callback.message.chat.id, message_id=callback.message.message_id - 1)

        # Уведомляем пользователя
        await bot.send_message(user_id, "🎉 Твой тейк был одобрен и опубликован в канале!")

        # Очищаем кнопки у ВСЕХ админов, которые получили этот тейк
        for am in take_info["admin_messages"]:
            try:
                status_text = "ОДОБРЕНО И ОПУБЛИКОВАНО ✅" if am["chat_id"] == callback.message.chat.id else "ОБРАБОТАН ДРУГИМ АДМИНИСТРАТОРОМ ✅"
                await bot.edit_message_text(
                    chat_id=am["chat_id"],
                    message_id=am["message_id"],
                    text=f"📥 Тейк от пользователя (ID: `{user_id}`):\n\n**Статус: {status_text}**",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    except Exception as e:
        await callback.answer(f"Ошибка публикации: {e}", show_alert=True)
        return

    await callback.answer("Опубликовано!")


@dp.callback_query(F.data.startswith("reject_"))
async def reject_take(callback: CallbackQuery, bot: Bot):
    user_id = int(callback.data.split("_")[1])
    
    target_key = None
    take_info = None
    
    for key, info in takes_data.items():
        for am in info["admin_messages"]:
            if am["chat_id"] == callback.message.chat.id and am["message_id"] == callback.message.message_id:
                target_key = key
                take_info = info
                break
        if target_key:
            break

    if not take_info:
        await callback.answer("⚠️ Этот тейк уже был обработан другим модератором!", show_alert=True)
        await callback.message.edit_text(f"{callback.message.text}\n\n**Статус: УЖЕ ОБРАБОТАН ⚠️**", parse_mode="Markdown")
        return

    takes_data.pop(target_key, None)

    try:
        await bot.send_message(user_id, "❌ К сожалению, твой тейк был отклонен модератором.")
        
        # Обновляем статус у всех админов
        for am in take_info["admin_messages"]:
            try:
                status_text = "ОТКЛОНЕНО ❌" if am["chat_id"] == callback.message.chat.id else "ОБРАБОТАН ДРУГИМ АДМИНИСТРАТОРОМ ❌"
                await bot.edit_message_text(
                    chat_id=am["chat_id"],
                    message_id=am["message_id"],
                    text=f"📥 Тейк от пользователя (ID: `{user_id}`):\n\n**Статус: {status_text}**",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
                
    except Exception as e:
        await callback.answer(f"Ошибка: {e}", show_alert=True)

    await callback.answer("Тейк отклонен.")


@dp.callback_query(F.data.startswith("reply_"))
async def reply_to_user_start(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[1])
    admin_reply_targets[callback.from_user.id] = user_id
    await callback.message.answer("✉️ Введи текст ответа пользователю (он придет ему от имени бота):")
    await callback.answer()


@dp.message(F.from_user.id.in_(ADMINS))
async def handle_admin_reply(message: Message, bot: Bot):
    if message.from_user.id in admin_reply_targets:
        target_user_id = admin_reply_targets.pop(message.from_user.id)
        try:
            await bot.send_message(target_user_id, f"💬 Сообщение от модератора:\n\n{message.text}")
            await message.answer("✅ Ответ успешно отправлен пользователю!")
        except Exception as e:
            await message.answer(f"❌ Не удалось отправить сообщение: {e}")


async def main():
    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())