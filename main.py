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
from db import get_balance, update_balance, add_promo, use_promo, add_purchase, load_json, PURCHASES_FILE, save_username, get_id_by_username
from lolz import fast_buy, get_telegram_code
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

# Эндпоинт для пробуждения сервера
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
    username = data.get("username", "unknown")
    item_id = data.get("item_id")
    price = data.get("price")
    
    item = next((i for i in CATALOG if i["item_id"] == item_id), None)
    if not item: return {"error": "not_found"}
    
    balance = get_balance(user_id)
    if balance < price: return {"error": "no_money", "balance": balance}
        
    update_balance(user_id, -price)
    try:
        await fast_buy(item_id, item["price_rub"])
        code = await get_telegram_code(item_id)
    except Exception as e:
        update_balance(user_id, price)
        return {"error": "lolz_error", "msg": str(e)}
        
    add_purchase(user_id, username, item_id, price)
    try: await bot.send_message(ADMIN_ID, f"💰 <b>НОВАЯ ПОКУПКА!</b>\n\nПокупатель: @{username} ({user_id})\nАккаунт: {item['country']} (ID: {item_id})\nЦена: {price} ⭐")
    except: pass
    return {"success": True, "code": code, "phone": item["phone_prefix"]}

@app.on_event("startup")
async def on_start():
    await refresh()
    start_scheduler()
    asyncio.create_task(dp.start_polling(bot))

class UserState(StatesGroup):
    waiting_deposit_amount = State()
    waiting_transfer_target = State()
    waiting_transfer_amount = State()
    waiting_promo = State()
    admin_waiting_promo_amount = State()

def get_main_kb(user_id):
    kb = [
        [KeyboardButton(text="🛒 Каталог", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="🎟 Промокоды")],
        [KeyboardButton(text="📜 Правила"), KeyboardButton(text="🆘 Поддержка")]
    ]
    if user_id == ADMIN_ID: kb.append([KeyboardButton(text="👑 Админка")])
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=kb)

@dp.message(Command("start"))
async def start(m: types.Message):
    # Сохраняем юзернейм для переводов
    save_username(m.from_user.id, m.from_user.username)
    
    text = "👋 <b>Добро пожаловать в магазин аккаунтов от Калашовского!</b>\n\nЗдесь ты можешь купить качественные Telegram-аккаунты. Все аккаунты проходят строгую проверку.\n\nВыбери нужный раздел в меню ниже 👇"
    photo_url = "https://raw.githubusercontent.com/fafd4826-ship-it/kalashop-web/main/IMG_20261125_234930_839.jpg"
    await m.answer_photo(photo=photo_url, caption=text, reply_markup=get_main_kb(m.from_user.id), parse_mode="HTML")

@dp.message(F.text == "👤 Профиль")
async def profile(m: types.Message):
    save_username(m.from_user.id, m.from_user.username)
    balance = get_balance(m.from_user.id)
    ref_link = f"https://t.me/{(await bot.get_me()).username}?start=ref{m.from_user.id}"
    text = f"👤 <b>Ваш профиль</b>\n\nИдентификатор: <code>{m.from_user.id}</code>\n\n💳 Баланс: <b>{balance} ⭐</b>\n\n🔗 <b>Реф. ссылка:</b>\n<code>{ref_link}</code>"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пополнить баланс", callback_data="pay")], [InlineKeyboardButton(text="Перевести другу", callback_data="transfer")]])
    await m.answer(text, reply_markup=kb, parse_mode="HTML")

@dp.message(F.text == "👑 Админка")
async def admin_panel(m: types.Message):
    if m.from_user.id != ADMIN_ID: return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟 Создать промокод", callback_data="admin_create_promo")],[InlineKeyboardButton(text="📊 История покупок", callback_data="admin_history")]])
    await m.answer("👑 <b>Панель владельца</b>", reply_markup=kb, parse_mode="HTML")

@dp.callback_query(F.data == "admin_create_promo")
async def admin_promo(call: types.CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.set_state(UserState.admin_waiting_promo_amount)
    await call.message.answer("Введите количество звезд для промокода (например, 50):")
    await call.answer()

@dp.message(UserState.admin_waiting_promo_amount)
async def admin_process_promo(m: types.Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
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
    amount = use_promo(m.text)
    await state.clear()
    if amount:
        update_balance(m.from_user.id, amount)
        await m.answer(f"✅ Промокод активирован! Вы получили {amount} ⭐", reply_markup=get_main_kb(m.from_user.id))
    else:
        await m.answer("❌ Неверный или уже использованный промокод.", reply_markup=get_main_kb(m.from_user.id))

@dp.callback_query(F.data == "pay")
async def start_deposit(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserState.waiting_deposit_amount)
    await call.message.answer("Введите сумму пополнения в звездах:")
    await call.answer()

@dp.message(UserState.waiting_deposit_amount)
async def process_deposit_amount(m: types.Message, state: FSMContext):
    try:
        amount = int(m.text)
        if amount < 1: raise ValueError
    except: return await m.answer("Введите число больше 0.")
    await state.clear()
    await bot.send_invoice(m.chat.id, title="Пополнение", description=f"На {amount} Stars", payload=f"dep_{amount}", provider_token="", currency="XTR", prices=[LabeledPrice(label="Пополнение", amount=amount)])

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: types.Message):
    amount = m.successful_payment.total_amount
    update_balance(m.from_user.id, amount)
    await m.answer(f"✅ Баланс пополнен на {amount} ⭐", reply_markup=get_main_kb(m.from_user.id))

@dp.callback_query(F.data == "transfer")
async def start_transfer(call: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserState.waiting_transfer_target)
    await call.message.answer("Введите @username получателя:")
    await call.answer()

@dp.message(UserState.waiting_transfer_target)
async def process_transfer_target(m: types.Message, state: FSMContext):
    await state.update_data(target=m.text.strip())
    await state.set_state(UserState.waiting_transfer_amount)
    await m.answer("Введите сумму перевода в звездах:")

@dp.message(UserState.waiting_transfer_amount)
async def process_transfer_amount(m: types.Message, state: FSMContext):
    try: amount = int(m.text)
    except: return await m.answer("Введите число.")
    
    data = await state.get_data()
    target = data.get("target").replace("@", "")
    balance = get_balance(m.from_user.id)
    
    if balance < amount: 
        await state.clear()
        return await m.answer("❌ Недостаточно средств.")
        
    # Ищем ID в нашей базе (или через API)
    receiver_id = None
    if target.isdigit():
        receiver_id = target
    else:
        receiver_id = get_id_by_username(target)
        if not receiver_id:
            try:
                chat = await bot.get_chat(f"@{target}")
                receiver_id = chat.id
            except:
                await state.clear()
                return await m.answer("❌ Пользователь не найден. Попросите друга нажать /start в боте.")
        
    if str(receiver_id) == str(m.from_user.id):
        await state.clear()
        return await m.answer("❌ Нельзя перевести самому себе.")

    update_balance(m.from_user.id, -amount)
    update_balance(receiver_id, amount)
    await state.clear()
    await m.answer(f"✅ Переведено {amount} ⭐ пользователю @{target}", reply_markup=get_main_kb(m.from_user.id))
    try: await bot.send_message(receiver_id, f"💰 Вам перевели {amount} ⭐!")
    except: pass

@dp.message(F.text == "📜 Правила")
async def rules(m: types.Message):
    await m.answer("⚠️ <b>Правила:</b>\n1. Оплата в Stars.\n2. Гарантия 24 часа.\n3. Используйте прокси.", parse_mode="HTML")

@dp.message(F.text == "🆘 Поддержка")
async def support(m: types.Message): await m.answer("Поддержка: @aoswat")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
