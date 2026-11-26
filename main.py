import asyncio
import socket
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from catalog import CATALOG, start_scheduler, refresh
from config import BOT_TOKEN, WEBAPP_URL
from db import add_purchase
from lolz import fast_buy, get_telegram_code, search_telegram
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

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

@app.get("/api/test_lolz")
async def api_test_lolz():
    try:
        raw = await search_telegram()
        return {"status": "ok", "count": len(raw), "first_item": raw[0] if raw else "СПИСОК ПУСТ"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/catalog")
async def api_catalog(category: str = "all", q: str = ""):
    global CATALOG
    if not CATALOG:
        await refresh()
        
    items = CATALOG
    if category == "new": items = [i for i in items if i["age_days"] < 30]
    elif category == "aged": items = [i for i in items if i["age_days"] >= 30]
    elif category == "premium": items = [i for i in items if i["is_premium"]]
    
    if q:
        q_lower = q.lower()
        items = [i for i in items if q_lower in str(i.get("description", "")).lower() or q_lower in str(i.get("country", "")).lower()]
        
    return {"items": items}

@app.post("/api/buy")
async def api_buy(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    item_id = data.get("item_id")
    
    # Получаем цену в рублях из запроса
    price_rub = data.get("price", 0)

    try:
        # Передаем цену в рублях в функцию покупки
        await fast_buy(item_id, price_rub) 
        
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
            return JSONResponse({"error": f"{error_str}"})
