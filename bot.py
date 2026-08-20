import os
import json
import logging
import hashlib
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineQuery, InlineQueryResultCachedVoice
from aiogram.filters import CommandStart

# Бот автоматически возьмет токен из панели управления Bothost (вкладка Env/Переменные)
BOT_TOKEN = os.getenv("BOT_TOKEN")
# ID вашего аккаунта Telegram (чтобы только вы могли добавлять голосовые)
ADMIN_ID = 333377745  # Замените на свой числовой ID

if not BOT_TOKEN:
    raise ValueError("ОШИБКА: Переменная окружения BOT_TOKEN не настроена в панели хостинга!")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# Файл для хранения базы данных голосовых
DB_FILE = "voice_db.json"

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

voice_db = load_db()

# Команда /start (работает только в ЛС)
@dp.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я инлайн-бот с голосовыми цитатами.\n\n"
        "Вы можете использовать меня в **любом чате**! "
        "Просто введите в поле ввода: `@имя_бота ключевое слово`"
    )

# Обработка добавления голосовых администратором
@dp.message(F.from_user.id == ADMIN_ID)
async def handle_admin_voice_upload(message: Message):
    file_id = None
    keywords_text = ""

    # ВАРИАНТ 1: Вы сделали ОТВЕТ (REPLY) текстом на аудио/голосовое/документ
    if message.reply_to_message:
        reply = message.reply_to_message
        
        # Проверяем, что в исходном сообщении есть аудиофайл
        if reply.voice:
            file_id = reply.voice.file_id
        elif reply.audio:
            file_id = reply.audio.file_id
        elif reply.document and reply.document.mime_type and reply.document.mime_type.startswith("audio/"):
            file_id = reply.document.file_id
            
        keywords_text = message.text

    # ВАРИАНТ 2: Вы ПЕРЕСЛАЛИ/ОТПРАВИЛИ файл и успели написать подпись в том же сообщении
    elif message.caption:
        if message.voice:
            file_id = message.voice.file_id
        elif message.audio:
            file_id = message.audio.file_id
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("audio/"):
            file_id = message.document.file_id
            
        keywords_text = message.caption

    # Подсказка для админа: строго если файл прислан БЕЗ подписи и ТОЛЬКО в ЛС бота
    elif message.chat.type == "private" and (
        message.voice or message.audio or 
        (message.document and message.document.mime_type and message.document.mime_type.startswith("audio/"))
    ):
        await message.answer(
            "Файл получен! Чтобы привязать к нему ключевые слова:\n"
            "**Сделайте ОТВЕТ (reply)** на это сообщение и напишите ключевые слова через запятую."
        )
        return
    else:
        # В группах или если это обычный текст админа — просто пропускаем код в текстовый поиск
        pass

    # Если файл и ключевые слова успешно определены, сохраняем в базу
    if file_id and keywords_text:
        keywords = [kw.strip().lower() for kw in keywords_text.split(",") if kw.strip()]
        
        if not keywords:
            if message.chat.type == "private":
                await message.answer("Ошибка: Не найдено ни одного валидного ключевого слова.")
            return

        # Записываем в базу
        for kw in keywords:
            voice_db[kw] = file_id
        
        save_db(voice_db)
        await message.answer(f"✅ Успешно добавлено! Привязано к словам: {', '.join(keywords)}")

# --- ИНЛАЙН РЕЖИМ (Работает в любых чатах) ---
@dp.inline_query()
async def inline_voice_handler(inline_query: InlineQuery):
    query_text = inline_query.query.strip().lower()
    results = []

    # Если пользователь ничего не ввел, показываем первые 50 доступных цитат
    if not query_text:
        unique_voices = {}
        for kw, f_id in voice_db.items():
            if f_id not in unique_voices:
                unique_voices[f_id] = kw

        for f_id, kw in list(unique_voices.items())[:50]:
            result_id = hashlib.md5(f_id.encode()).hexdigest()
            results.append(
                InlineQueryResultCachedVoice(
                    id=result_id,
                    voice_file_id=f_id,
                    title=f"Цитата: {kw}"
                )
            )
    else:
        # Если есть запрос, фильтруем по ключевым словам
        for keyword, file_id in voice_db.items():
            if query_text in keyword:
                result_id = hashlib.md5(f"{keyword}_{file_id}".encode()).hexdigest()
                results.append(
                    InlineQueryResultCachedVoice(
                        id=result_id,
                        voice_file_id=file_id,
                        title=f"Триггер: {keyword}"
                    )
                )
                if len(results) >= 50:
                    break

    await inline_query.answer(results, is_personal=False, cache_time=1)

# Обычные текстовые сообщения (поиск по ключевым словам внутри ЛС бота)
@dp.message(F.text)
async def reply_with_voice(message: Message):
    user_text = message.text.strip().lower()
    for keyword, file_id in voice_db.items():
        if keyword in user_text:
            await bot.send_voice(chat_id=message.chat.id, voice=file_id)
            return

# Запуск бота
if __name__ == "__main__":
    import asyncio
    asyncio.run(dp.start_polling(bot))