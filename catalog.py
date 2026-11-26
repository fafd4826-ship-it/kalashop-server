import math
import time
import re
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from lolz import search_telegram
from config import MIN_SELLER_REVIEWS, STAR_RATE_RUB, MIN_QUALITY_SCORE

CATALOG = []

# Словарь кодов стран (если API не отдает префикс)
PHONE_CODES = {
    "RU": "+7", "KZ": "+7", "US": "+1", "CA": "+1", "GB": "+44", "UA": "+380",
    "BY": "+375", "UZ": "+998", "KG": "+996", "TJ": "+992", "AM": "+374",
    "AZ": "+994", "GE": "+995", "MD": "+373", "IN": "+91", "ID": "+62",
    "BD": "+880", "PH": "+63", "VN": "+84", "TH": "+66", "MY": "+60",
    "TR": "+90", "BR": "+55", "MX": "+52", "AR": "+54", "CL": "+56",
    "CO": "+57", "PE": "+51", "DE": "+49", "FR": "+33", "IT": "+39",
    "ES": "+34", "PL": "+48", "NL": "+31", "BE": "+32", "SE": "+46",
    "CH": "+41", "AT": "+43", "PT": "+351", "GR": "+30", "CZ": "+420",
    "RO": "+40", "HU": "+36", "BG": "+359", "HR": "+385", "RS": "+381",
    "SK": "+421", "SI": "+386", "LT": "+370", "LV": "+371", "EE": "+372",
    "FI": "+358", "NO": "+47", "DK": "+45", "IE": "+353"
}

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
                
            # Безопасный парсинг даты
            reg_date = item.get("telegram_registration_date")
            if not reg_date:
                age_days = 0
            else:
                try: age_days = (now - float(reg_date)) / 86400
                except: age_days = 0
            
            # Безопасный парсинг премиума
            is_premium = bool(item.get("telegram_premium", False))
            premium_expires = item.get("telegram_premium_expires")
            if is_premium and premium_expires:
                try: premium_days = (float(premium_expires) - now) / 86400
                except: premium_days = 0
            else:
                premium_days = 0
            
            # Чистим описание
            raw_desc = item.get("description") or ""
            clean_desc = re.sub(r'\[tooltip=\d+\]', '', raw_desc).replace('[/tooltip]', '')
            clean_desc = clean_desc[:120] + "..." if len(clean_desc) > 120 else clean_desc
            
            country = item.get("telegram_country") or item.get("origin") or "UNKNOWN"
            country_upper = str(country).upper()
            
            # Определяем код страны (если префикс пустой, берем из словаря)
            prefix = item.get("phone_prefix")
            if not prefix or prefix == "+":
                prefix = PHONE_CODES.get(country_upper, "+")
            
            price_rub = item.get("price", 0)
            cost_in_stars = price_rub / STAR_RATE_RUB
            dynamic_profit = max(10, math.ceil(cost_in_stars * 0.08))
            price_stars = math.ceil(cost_in_stars + dynamic_profit)
            
            good.append({
                "item_id": item.get("item_id", 0), 
                "price_rub": price_rub, 
                "price_stars": price_stars,
                "country": country_upper, 
                "phone_prefix": prefix,
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
