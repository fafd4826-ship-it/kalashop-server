import asyncio
import socket
import os
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from catalog import CATALOG, start_scheduler, refresh
from config import BOT_TOKEN, WEBAPP_URL, ADMIN_ID
from db import add_purchase
from lolz import fast_buy, get_telegram_code
import uvicorn
from fastapi.middleware.cors import CORSMiddleware

# Фикс для IPv6
orig_getaddrinfo = socket.getaddrinfo
def getaddrinfo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    return orig_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
socket.getaddrinfo = getaddrinfo_ipv4

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.get("/api/ping")
async def api_ping(): return {"status": "ok"}

@app.get("/api/catalog")
async def api_catalog(category: str = "all", country: str = None, q: str = None):
    items = CATALOG
    if category == "new": items = [i for i in items if i["age_days"] < 30]
    elif category == "aged": items = [i for i in items if i["age_days"] >= 180]
    elif category == "premium": items = [i for i in items if i["is_premium"] and i["premium_days"] >= 30]
    if country: items = [i for i in items if country.lower() in (i["country"] or "").lower() or country in (i["phone_prefix"] or "")]
    if q: items = [i for i in items if q.lower() in (i["description"] or "").lower()]
    return {"items": items}

@app.post("/api/buy")
async def api_buy(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    item_id = data.get("item_id")
    price = data.get("price")
    
    item = next((i for i in CATALOG if i["item_id"] == item_id), None)
    if not item: return {"error": "not_found"}
    
    # Отправляем счет на оплату в Stars прямо в чат
    try:
        await bot.send_invoice(
            chat_id=user_id,
            title=f"Аккаунт {item['country']}",
            description=f"Покупка Telegram-аккаунта за {price} Stars",
            payload=f"buy_item_{item_id}_{item['price_rub']}",
            provider_token="",  # Для Stars пусто
            currency="XTR",
            prices=[LabeledPrice(label="Аккаунт", amount=price)]
        )
        return {"success": True, "status": "invoice_sent"}
    except Exception as e:
        return {"error": "tg_error", "msg": str(e)}

@app.on_event("startup")
async def on_start():
    await refresh()
    start_scheduler()
    asyncio.create_task(dp.start_polling(bot))

# --- Клавиатура (БЕЗ ПРОФИЛЯ) ---
def get_main_kb(user_id):
    kb = [
        [KeyboardButton(text="🛒 Каталог", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="🎟 Промокоды"), KeyboardButton(text="📜 Правила")],
        [KeyboardButton(text="🆘 Поддержка")]
    ]
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="👑 Админка")])
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=kb)

@dp.message(Command("start"))
async def start(m: types.Message):
    text = (
        "👋 <b>Добро пожаловать в магазин аккаунтов от Калашовского!</b>\n\n"
        "Здесь ты можешь купить качественные Telegram-аккаунты. "
        "Все аккаунты проходят строгую проверку.\n\n"
        "Выбери нужный раздел в меню ниже 👇"
    )
    photo_url = "https://raw.githubusercontent.com/fafd4826-ship-it/kalashop-web/main/IMG_20261125_234930_839.jpg"
    await m.answer_photo(photo=photo_url, caption=text, reply_markup=get_main_kb(m.from_user.id), parse_mode="HTML")

# ================= ОПЛАТА И ПОКУПКА =================
@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): 
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: types.Message):
    payload = m.successful_payment.invoice_payload
    
    # Если это оплата конкретного аккаунта
    if payload.startswith("buy_item_"):
        parts = payload.split("_")
        item_id = int(parts[2])
        price_rub = float(parts[3])
        price_stars = m.successful_payment.total_amount
        
        await m.answer("✅ Оплата получена! Покупаем аккаунт на Lolzteam, подождите...")
        
        try:
            # Покупаем на Lolzteam
            await fast_buy(item_id, price_rub)
            # Получаем код
            code = await get_telegram_code(item_id)
            
            item = next((i for i in CATALOG if i["item_id"] == item_id), None)
            phone = item['phone_prefix'] if item else "+"
            
            # Отправляем номер и код
            await m.answer(
                f"✅ <b>Успешно куплено!</b>\n\n"
                f"Номер: <code>{phone}</code>\n"
                f"Код: <code>{code}</code>\n\n"
                f"Не забудьте использовать прокси!", 
                reply_markup=get_main_kb(m.from_user.id),
                parse_mode="HTML"
            )
            
            # Запись в историю и уведомление админу
            add_purchase(m.from_user.id, m.from_user.username or "unknown", item_id, price_stars)
            try:
                await bot.send_message(ADMIN_ID, f"💰 <b>НОВАЯ ПОКУПКА!</b>\n\nПокупатель: @{m.from_user.username} ({m.from_user.id})\nАккаунт: {item['country']} (ID: {item_id})\nЦена: {price_stars} ⭐")
            except: pass
            
        except Exception as e:
            await m.answer(f"❌ Ошибка при покупке на Lolzteam. Напишите в поддержку @aoswat для возврата средств.\nОшибка: {e}")

# ================= АДМИНКА =================
@dp.message(F.text == "👑 Админка")
async def admin_panel(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 История покупок", callback_data="admin_history")]
    ])
    await m.answer("👑 <b>Панель владельца</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "admin_history")
async def admin_history(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    from db import load_json, PURCHASES_FILE
    history = load_json(PURCHASES_FILE)
    if not history or not isinstance(history, list):
        return await call.message.answer("История пуста.")
    
    text = "📊 <b>Последние 10 покупок:</b>\n\n"
    for item in history[-10:]:
        text += f"👤 @{item['buyer_username']} купил ID {item['item_id']} за {item['price']} ⭐ ({item['date']})\n"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()

# ================= СТАНДАРТНЫЕ КНОПКИ =================
@dp.message(F.text == "🎟 Промокоды")
async def promocodes(m: types.Message):
    await m.answer("Промокоды временно недоступны.")

@dp.message(F.text == "📜 Правила")
async def rules(m: types.Message):
    text = (
        "⚠️ <b>ВАЖНО! Прочитайте перед покупкой</b>\n\n"
        "🔒 <b>Безопасность:</b>\n"
        "• Обязательно используйте качественный прокси той страны, которую выбрали\n"
        "• Записывайте видео при входе в аккаунт\n"
        "• Не используйте публичные прокси — гарантия аннулируется!\n\n"
        "💼 <b>Рекомендации по использованию:</b>\n"
        "• Первые 3 дня не пишите в чаты и группы\n"
        "• Пароль можно установить сразу\n"
        "• Имя и фамилию лучше не менять первые дни\n"
        "• После 24 часов на аккаунте обязательно привяжите passkey!\n\n"
        "🛡 <b>Гарантия:</b>\n"
        "После авторизации вся ответственность за аккаунт на вас. Проблемы с доступом возникают только при нарушении правил Telegram или неправильном использовании прокси."
    )
    await m.answer(text, parse_mode="HTML")

@dp.message(F.text == "🆘 Поддержка")
async def support(m: types.Message): 
    await m.answer("По всем вопросам пишите: @aoswat")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
