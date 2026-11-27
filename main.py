import asyncio
import socket
import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, LabeledPrice, PreCheckoutQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from catalog import CATALOG, start_scheduler, refresh
from config import BOT_TOKEN, WEBAPP_URL, ADMIN_ID
from db import add_purchase, get_all_users, save_username
from lolz import fast_buy, get_telegram_code, get_lolz_balance
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
    return JSONResponse(status_code=500, content={"error": "server_error", "msg": str(exc)})

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

# --- ТЕСТОВЫЙ РЕЖИМ ПОКУПКИ (БЕЗ ЗВЕЗД) ---
@app.post("/api/buy")
async def api_buy(request: Request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        item_id = int(data.get("item_id"))
        price = int(data.get("price"))
    except:
        return {"error": "invalid_data", "msg": "Неверный формат данных"}
    
    item = next((i for i in CATALOG if i["item_id"] == item_id), None)
    if not item: return {"error": "not_found", "msg": "Аккаунт уже продан"}
    
    # Делаем покупку напрямую (для теста)
    try:
        await bot.send_message(user_id, f"🧪 <b>ТЕСТОВЫЙ РЕЖИМ</b>\nПробуем купить аккаунт ID {item_id} за {price}⭐ (руб: {item['price_rub']})...", parse_mode="HTML")
        
        # 1. Покупка
        await fast_buy(item_id, item["price_rub"])
        
        # 2. Получение кода
        code = await get_telegram_code(item_id)
        
        await bot.send_message(user_id, f"✅ <b>УСПЕХ!</b>\nАккаунт куплен.\nВаш код: <code>{code}</code>", parse_mode="HTML")
        return {"success": True, "status": "test_buy_success"}
    except Exception as e:
        error_msg = str(e)
        await bot.send_message(user_id, f"❌ <b>ОШИБКА Lolzteam:</b>\n<code>{error_msg}</code>", parse_mode="HTML")
        return {"error": "lolz_error", "msg": error_msg}

async def balance_checker():
    while True:
        balance = await get_lolz_balance()
        if 0 < balance < 250:
            try:
                await bot.send_message(ADMIN_ID, f"⚠️ <b>ВНИМАНИЕ!</b>\nБаланс Lolzteam упал ниже 250₽.\nТекущий баланс: <b>{balance}₽</b>")
            except: pass
        await asyncio.sleep(3600)

@app.on_event("startup")
async def on_start():
    await refresh()
    start_scheduler()
    asyncio.create_task(dp.start_polling(bot))
    asyncio.create_task(balance_checker())

class UserState(StatesGroup):
    waiting_promo = State()
    waiting_review = State()
    admin_waiting_promo_amount = State()
    admin_broadcast = State()

def get_main_kb(user_id):
    kb = [
        [KeyboardButton(text="🛒 Каталог", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="🎟 Промокоды"), KeyboardButton(text="📜 Правила")],
        [KeyboardButton(text="🆘 Поддержка")]
    ]
    if user_id == ADMIN_ID: kb.append([KeyboardButton(text="👑 Админка")])
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=kb)

@dp.message(Command("start"))
async def start(m: types.Message):
    save_username(m.from_user.id, m.from_user.username)
    text = "👋 <b>Добро пожаловать в магазин аккаунтов от Калашовского!</b>\n\nЗдесь ты можешь купить качественные Telegram-аккаунты.\n\nВыбери нужный раздел в меню ниже 👇"
    photo_url = "https://raw.githubusercontent.com/fafd4826-ship-it/kalashop-web/main/IMG_20261125_234930_839.jpg"
    await m.answer_photo(photo=photo_url, caption=text, reply_markup=get_main_kb(m.from_user.id), parse_mode="HTML")

@dp.message(Command("check"))
async def check_balance_cmd(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    await m.answer("⏳ Запрашиваю баланс у Lolzteam...")
    balance = await get_lolz_balance()
    await m.answer(f"Текущий баланс по API: <b>{balance}₽</b>", parse_mode="HTML")

# Заглушка для оплаты, чтобы не было ошибок при старых счетах
@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): 
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: types.Message):
    await m.answer("Оплата получена, но магазин временно в тестовом режиме. Напишите @aoswat для выдачи аккаунта.")

# ... (Остальные функции: Отзывы, Админка, Промокоды, Правила - без изменений) ...
@dp.callback_query(F.data == "leave_review")
async def ask_review(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserState.waiting_review)
    await call.message.answer("Напишите ваш отзыв одним сообщением:")
    await call.answer()

@dp.message(UserState.waiting_review)
async def process_review(m: types.Message, state: FSMContext):
    await state.clear()
    if m.text:
        review_text = f"⭐ <b>Новый отзыв!</b>\n\nОт: @{m.from_user.username or m.from_user.first_name}\n\n{m.text}"
        try:
            await bot.send_message("@otzivikalasovshkogo", review_text, parse_mode="HTML")
            await m.answer("✅ Спасибо! Ваш отзыв отправлен в наш канал.", reply_markup=get_main_kb(m.from_user.id))
        except Exception as e:
            await m.answer("✅ Спасибо за отзыв! (Ошибка отправки в канал)", reply_markup=get_main_kb(m.from_user.id))

@dp.message(F.text == "👑 Админка")
async def admin_panel(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🎟 Создать промокод", callback_data="admin_create_promo")],
        [InlineKeyboardButton(text="📊 История покупок", callback_data="admin_history")]
    ])
    await m.answer("👑 <b>Панель владельца</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.set_state(UserState.admin_broadcast)
    await call.message.answer("Отправьте сообщение для рассылки всем пользователям:")
    await call.answer()

@dp.message(UserState.admin_broadcast)
async def process_broadcast(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    await state.clear()
    users = get_all_users()
    await m.answer(f"⏳ Начинаю рассылку для {len(users)} пользователей...")
    success = 0
    for uid in users:
        try:
            await m.copy_to(chat_id=int(uid))
            success += 1
            await asyncio.sleep(0.05)
        except: pass
    await m.answer(f"✅ Рассылка завершена!\nДоставлено: {success} из {len(users)}", reply_markup=get_main_kb(m.from_user.id))

@dp.callback_query(F.data == "admin_create_promo")
async def admin_promo(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.set_state(UserState.admin_waiting_promo_amount)
    await call.message.answer("Введите количество звезд для промокода:")
    await call.answer()

@dp.message(UserState.admin_waiting_promo_amount)
async def admin_process_promo(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    from db import add_promo
    try:
        amount = int(m.text)
        code = f"KALA{amount}_{m.from_user.id % 1000}"
        add_promo(code, amount)
        await state.clear()
        await m.answer(f"✅ Промокод создан: <code>{code}</code>\nДает: {amount} ⭐", parse_mode="HTML")
    except: await m.answer("Ошибка. Введите число.")

@dp.callback_query(F.data == "admin_history")
async def admin_history(call: types.CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    from db import load_json, PURCHASES_FILE
    history = load_json(PURCHASES_FILE)
    if not history or not isinstance(history, list): return await call.message.answer("История пуста.")
    text = "📊 <b>Последние 10 покупок:</b>\n\n"
    for item in history[-10:]: text += f"👤 @{item['buyer_username']} купил ID {item['item_id']} за {item['price']} ⭐ ({item['date']})\n"
    await call.message.answer(text, parse_mode="HTML")
    await call.answer()

@dp.message(F.text == "🎟 Промокоды")
async def promocodes(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚙️ Ввести промокод", callback_data="enter_promo")]])
    await m.answer("Введите промокод, чтобы получить звезды:", reply_markup=kb)

@dp.callback_query(F.data == "enter_promo")
async def enter_promo(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserState.waiting_promo)
    await call.message.answer("Отправьте промокод в чат:")
    await call.answer()

@dp.message(UserState.waiting_promo)
async def process_promo(m: types.Message, state: FSMContext):
    from db import use_promo, update_balance
    amount = use_promo(m.text)
    await state.clear()
    if amount:
        update_balance(m.from_user.id, amount)
        await m.answer(f"✅ Промокод активирован! Вы получили {amount} ⭐", reply_markup=get_main_kb(m.from_user.id))
    else:
        await m.answer("❌ Неверный или уже использованный промокод.", reply_markup=get_main_kb(m.from_user.id))

@dp.message(F.text == "📜 Правила")
async def rules(m: types.Message):
    await m.answer("⚠️ <b>Правила:</b>\n1. Оплата в Stars.\n2. Гарантия 24 часа.\n3. Используйте прокси.", parse_mode="HTML")

@dp.message(F.text == "🆘 Поддержка")
async def support(m: types.Message): await m.answer("Поддержка: @aoswat")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
