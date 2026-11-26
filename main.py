import asyncio
import socket
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from catalog import CATALOG, start_scheduler
from config import BOT_TOKEN, WEBAPP_URL
from db import add_purchase
from lolz import fast_buy, get_telegram_code
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

# Фикс для IPv4 (чтобы Render не тупил с подключением к Telegram)
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=500, content={"error": str(exc)})

@app.get("/api/ping")
async def api_ping(): return {"status": "ok"}

@app.get("/api/catalog")
async def api_catalog(category: str = "all", q: str = ""):
    items = CATALOG
    # Фильтрация по категориям
    if category == "new": items = [i for i in items if i["age_days"] < 30]
    elif category == "aged": items = [i for i in items if i["age_days"] >= 30]
    elif category == "premium": items = [i for i in items if i["is_premium"]]
    
    # Фильтрация по поиску (если нужно)
    if q:
        q_lower = q.lower()
        items = [i for i in items if q_lower in str(i.get("description", "")).lower() or q_lower in str(i.get("country", "")).lower()]
        
    return {"items": items}

@app.post("/api/buy")
async def api_buy(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    item_id = data.get("item_id")
    # price_stars = data.get("price") # Цена нам тут больше не нужна

    try:
        # 1. Покупаем на Lolz (звезды НЕ списываются)
        # Передаем цену как строку/число, чтобы Lolz не ругался
        await fast_buy(item_id, 0) 
        
        # 2. Отправляем кнопку в бот при успехе
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Получить номер и код", callback_data=f"getcode_{item_id}")]
        ])
        
        await bot.send_message(
            chat_id=user_id, 
            text=f"✅ Аккаунт успешно куплен!\nID лота: {item_id}\n\nНажми кнопку ниже, чтобы получить данные.",
            reply_markup=keyboard
        )
        
        return {"status": "ok"}
        
    except Exception as e:
        error_str = str(e)
        if error_str == "already_sold_or_no_rights":
            return JSONResponse({"error": "Аккаунт уже куплен или нет прав на покупку."})
        elif error_str == "no_lolz_funds":
            return JSONResponse({"error": "no_lolz_funds"})
        else:
            return JSONResponse({"error": f"Ошибка: {error_str}"})

@dp.callback_query(lambda c: c.data.startswith('getcode_'))
async def process_get_code(callback_query: types.CallbackQuery):
    item_id = int(callback_query.data.split('_')[1])
    
    msg = await callback_query.message.answer("⏳ Запрашиваю данные у Lolz...")
    
    try:
        result_text = await get_telegram_code(item_id)
        await msg.edit_text(f"Данные аккаунта:\n\n{result_text}")
        
    except Exception as e:
        if "wait_please" in str(e):
            await msg.edit_text(
                "⏳ Lolz еще обрабатывает покупку. Подождите 1-2 минуты и нажмите кнопку снова.", 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"getcode_{item_id}")]
                ])
            )
        else:
            await msg.edit_text(f"❌ Ошибка получения: {e}")

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛒 Открыть магазин", web_app=types.WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer("Добро пожаловать в магазин!", reply_markup=kb)

async def main():
    start_scheduler()
    config = uvicorn.Config(app, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await asyncio.gather(
        dp.start_polling(bot),
        server.serve()
    )

if __name__ == "__main__":
    asyncio.run(main())
