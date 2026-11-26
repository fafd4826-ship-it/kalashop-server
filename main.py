import asyncio
import socket
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from catalog import CATALOG, start_scheduler, refresh  # <--- ДОБАВИЛИ refresh
from config import BOT_TOKEN, WEBAPP_URL
from db import add_purchase
from lolz import fast_buy, get_telegram_code, search_telegram # <--- ДОБАВИЛИ search_telegram
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

@app.get("/api/catalog")
async def api_catalog(category: str = "all", q: str = ""):
    global CATALOG
    
    # Если каталог пустой, пробуем спарсить прямо сейчас
    if not CATALOG:
        try:
            print("Каталог пуст, пробуем спарсить Lolz вручную...")
            await refresh() # Вызываем функцию обновления из catalog.py
        except Exception as e:
            print(f"Ошибка ручного парсинга: {e}")
            return JSONResponse({"error": f"Ошибка Lolz API: {e}", "items": []})

    items = CATALOG
    if category == "new": items = [i for i in items if i["age_days"] < 30]
    elif category == "aged": items = [i for i in items if i["age_days"] >= 30]
    elif category == "premium": items = [i for i in items if i["is_premium"]]
    
    if q:
        q_lower = q.lower()
        items = [i for i in items if q_lower in str(i.get("description", "")).lower() or q_lower in str(i.get("country", "")).lower()]
        
    return {"items": items}

# ... (функция api_buy и остальной код остаются БЕЗ ИЗМЕНЕНИЙ, как в прошлом сообщении) ...
