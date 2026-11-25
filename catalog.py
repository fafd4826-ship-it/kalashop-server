import math
import time
import re
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
        
    good = []
    now = time.time()
    
    for item in raw:
        try:
            seller = item.get("seller") or {}
            if seller.get("positive_feedback", 0) < MIN_SELLER_REVIEWS: 
                continue
                
            quality = item.get('telegram_quality_score') or 0
            if quality < MIN_QUALITY_SCORE: 
                continue
                
            # Вычисляем отлегу (берем дату регистрации, если нет — дату публикации)
            reg_date = item.get("telegram_registration_date") or item.get("published_date", 0)
            age_days = (now - reg_date) / 86400 if reg_date else 0
            
            # Проверяем премиум
            is_premium = bool(item.get("telegram_premium", False))
            premium_expires = item.get("telegram_premium_expires", 0)
            premium_days = (premium_expires - now) / 86400 if is_premium and premium_expires else 0
            
            # Убираем теги tooltip из описания
            raw_desc = item.get("description") or ""
            clean_desc = re.sub(r'\[tooltip=\d+\]', '', raw_desc).replace('[/tooltip]', '')
            clean_desc = clean_desc[:120] + "..." if len(clean_desc) > 120 else clean_desc
            
            price_rub = item.get("price", 0)
            cost_in_stars = price_rub / STAR_RATE_RUB
            dynamic_profit = max(10, math.ceil(cost_in_stars * 0.08))
            price_stars = math.ceil(cost_in_stars + dynamic_profit)
            
            good.append({
                "item_id": item.get("item_id", 0), 
                "price_rub": price_rub, 
                "price_stars": price_stars,
                "country": item.get("telegram_country") or "UNKNOWN", 
                "phone_prefix": item.get("phone_prefix") or "+",
                "description": clean_desc,
                "quality_score": quality, 
                "age_days": age_days,
                "is_premium": is_premium, 
                "premium_days": premium_days
            })
        except Exception as e:
            continue
            
    print(f"📦 В КАТАЛОГЕ ПОСЛЕ ФИЛЬТРОВ: {len(good)} аккаунтов")
    CATALOG.clear()
    CATALOG.extend(good)

def start_scheduler():
    sched = AsyncIOScheduler()
    sched.add_job(refresh, "interval", minutes=5)
    sched.start()
