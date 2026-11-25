import math
import time
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from lolz import search_telegram
from config import MIN_SELLER_REVIEWS, STAR_RATE_RUB, MIN_QUALITY_SCORE

CATALOG = []

async def refresh():
    global CATALOG
    try:
        raw = await search_telegram()
    except Exception as e:
        print(f"❌ ОШИБКА ПРИ ЗАПРОСЕ: {e}")
        return
        
    print(f"✅ ПОЛУЧЕНО СЫРЫХ ДАННЫХ: {len(raw)}")
    
    good = []
    now = time.time()
    
    # Выведем названия полей первого аккаунта для проверки
    if len(raw) > 0:
        print(f"🔍 ПОЛЯ АККАУНТА: {list(raw[0].keys())}")
        
    for item in raw:
        try:
            seller = item.get("seller") or {}
            if seller.get("positive_feedback", 0) < MIN_SELLER_REVIEWS: 
                continue
                
            quality = item.get('telegram_quality_score') or item.get('quality_score', 0)
            if quality < MIN_QUALITY_SCORE: 
                continue
                
            reg_date = item.get("telegram_registration_date", 0)
            age_days = (now - reg_date) / 86400 if reg_date else 0
            
            is_premium = item.get("telegram_premium", False)
            premium_expires = item.get("telegram_premium_expires", 0)
            premium_days = (premium_expires - now) / 86400 if is_premium else 0
                
            price_rub = item.get("price", 0)
            cost_in_stars = price_rub / STAR_RATE_RUB
            dynamic_profit = max(10, math.ceil(cost_in_stars * 0.08))
            price_stars = math.ceil(cost_in_stars + dynamic_profit)
            
            good.append({
                "item_id": item.get("item_id", 0), 
                "price_rub": price_rub, 
                "price_stars": price_stars,
                "country": item.get("country") or item.get("origin") or "Неизвестно",
                "phone_prefix": item.get("phone_prefix") or item.get("country_code") or "+",
                "description": (item.get("description") or "")[:120],
                "quality_score": quality, 
                "age_days": age_days,
                "is_premium": is_premium, 
                "premium_days": premium_days
            })
        except Exception as e:
            print(f"⚠️ ОШИБКА ПАРСИНГА АККАУНТА: {e}")
            continue
            
    print(f"📦 В КАТАЛОГЕ ПОСЛЕ ФИЛЬТРОВ: {len(good)} аккаунтов")
    CATALOG = good

def start_scheduler():
    sched = AsyncIOScheduler()
    sched.add_job(refresh, "interval", minutes=5)
    sched.start()
