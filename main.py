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
    
    try:
        item_id = int(data.get("item_id"))
        price = int(data.get("price"))
    except:
        return {"error": "invalid_data", "msg": "Неверный формат данных"}
    
    item = next((i for i in CATALOG if i["item_id"] == item_id), None)
    if not item: return {"error": "not_found", "msg": "Аккаунт уже продан"}
    
    # 1. ПРОВЕРКА БАЛАНСА LOLZ ПЕРЕД СЧЕТОМ
    balance = await get_lolz_balance()
    if balance < item["price_rub"]:
        return {"error": "no_lolz_funds", "msg": "На балансе магазина недостаточно средств. Выберите аккаунт дешевле."}

    # 2. ВЫСТАВЛЕНИЕ СЧЕТА
    try:
        await bot.send_invoice(
            chat_id=user_id, title=f"Аккаунт {item['country']}",
            description=f"Покупка Telegram-аккаунта за {price} Stars",
            payload=f"buy_item_{item_id}_{int(item['price_rub'])}",
            provider_token="", currency="XTR", prices=[LabeledPrice(label="Аккаунт", amount=price)]
        )
        return {"success": True, "status": "invoice_sent"}
    except Exception as e:
        print(f"ОШИБКА ОТПРАВКИ СЧЕТА: {e}")
        return {"error": "tg_error", "msg": str(e)}

async def balance_checker():
    while True:
        balance = await get_lolz_balance()
        if balance < 250:
            try:
                await bot.send_message(ADMIN_ID, f"⚠️ <b>ВНИМАНИЕ!</b>\nБаланс Lolzteam упал ниже 250₽.\nТекущий баланс: <b>{balance}₽</b>\nСрочно пополните счет!")
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
    text = "👋 <b>Добро пожаловать в магазин аккаунтов от Калашовского!</b>\n\nЗдесь ты можешь купить качественные Telegram-аккаунты. Все аккаунты проходят строгую проверку.\n\nВыбери нужный раздел в меню ниже 👇"
    photo_url = "https://raw.githubusercontent.com/fafd4826-ship-it/kalashop-web/main/IMG_20261125_234930_839.jpg"
    await m.answer_photo(photo=photo_url, caption=text, reply_markup=get_main_kb(m.from_user.id), parse_mode="HTML")

@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery): 
    await bot.answer_pre_checkout_query(query.id, ok=True)

@dp.message(F.successful_payment)
async def success_pay(m: types.Message):
    payload = m.successful_payment.invoice_payload
    
    if payload.startswith("buy_item_"):
        parts = payload.split("_")
        item_id = int(parts[2])
        price_rub = float(parts[3])
        price_stars = m.successful_payment.total_amount
        
        await m.answer("✅ Оплата получена! Покупаем аккаунт на Lolzteam, подождите...")
        
        try:
            await fast_buy(item_id, price_rub)
            code = await get_telegram_code(item_id)
            item = next((i for i in CATALOG if i["item_id"] == item_id), None)
            phone = item['phone_prefix'] if item else "+"
            
            await m.answer(f"✅ <b>Успешно куплено!</b>\n\nНомер: <code>{phone}</code>\nКод: <code>{code}</code>\n\nНе забудьте использовать прокси!", reply_markup=get_main_kb(m.from_user.id), parse_mode="HTML")
            
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Оставить отзыв", callback_data="leave_review")]])
            await m.answer("Пожалуйста, оставьте отзыв о нашем магазине!", reply_markup=kb)
            
            add_purchase(m.from_user.id, m.from_user.username or "unknown", item_id, price_stars)
            try: await bot.send_message(ADMIN_ID, f"💰 <b>НОВАЯ ПОКУПКА!</b>\n\nПокупатель: @{m.from_user.username} ({m.from_user.id})\nАккаунт: {item['country']} (ID: {item_id})\nЦена: {price_stars} ⭐")
            except: pass
            
        except Exception as e:
            # Если аккаунт уже кто-то купил (ошибка 400)
            error_msg = str(e)
            await m.answer(f"❌ <b>Ошибка покупки:</b>\n{error_msg}\n\nСкорее всего, этот аккаунт уже купил кто-то другой, пока вы оплачивали. Напишите @aoswat для возврата звезд.", reply_markup=get_main_kb(m.from_user.id), parse_mode="HTML")
            try: await bot.send_message(ADMIN_ID, f"⚠️ ОШИБКА ПОКУПКИ:\nПользователь @{m.from_user.username} оплатил ID {item_id}, но Lolz выдал ошибку: {error_msg}\nЗвезды нужно вернуть вручную.")
            except: pass

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
    else:
        await m.answer("Пожалуйста, отправьте текстовый отзыв.", reply_markup=get_main_kb(m.from_user.id))

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
