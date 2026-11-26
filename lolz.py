import httpx
from config import LOLZTEAM_TOKEN

BASE_URL = "https://api.lzt.market"
HEADERS = {"Authorization": f"Bearer {LOLZTEAM_TOKEN}"}

async def search_telegram(country: str = None, query: str = None):
    params = {}
    if country: params["country"] = country
    if query: params["keyword"] = query

    all_items = []
    async with httpx.AsyncClient() as client:
        for page in range(1, 3):
            try:
                params["page"] = page
                r = await client.get(f"{BASE_URL}/telegram", headers=HEADERS, params=params)
                
                if r.status_code != 200:
                    print(f"❌ LOLZ API ERROR: {r.status_code} - {r.text}")
                    break
                    
                data = r.json()
                items = data.get("items", [])
                if not items: 
                    print("⚠️ Lolz вернул пустой список items")
                    break
                all_items.extend(items)
            except Exception as e: 
                print(f"❌ ОШИБКА ПРИ ЗАПРОСЕ: {e}")
                break
    return all_items

async def fast_buy(item_id: int, price: float):
    async with httpx.AsyncClient() as client:
        # Перебираем возможные эндпоинты для покупки
        urls = [
            f"{BASE_URL}/market/item/buy",
            f"{BASE_URL}/item/fast-buy",
            f"{BASE_URL}/item/buy"
        ]
        
        last_error = ""
        
        for url in urls:
            try:
                r = await client.post(url, headers=HEADERS, json={"item_id": item_id})
                
                # Если страница не найдена (404), пробуем следующий URL
                if r.status_code == 404:
                    continue
                    
                if r.status_code != 200:
                    error_text = r.text.lower()
                    if r.status_code == 403 or "нет прав" in error_text:
                        raise Exception("already_sold_or_no_rights")
                    if r.status_code == 400:
                        raise Exception("no_lolz_funds")
                    raise Exception(f"Ошибка API: {r.text}")
                    
                # Если 200 ОК - значит купили!
                return r.json()
            except Exception as e:
                last_error = str(e)
                continue
                
        # Если ни один URL не сработал
        raise Exception(f"Не удалось найти рабочий метод. Последняя ошибка: {last_error}")

async def get_telegram_code(item_id: int):
    async with httpx.AsyncClient() as client:
        # Перебираем возможные эндпоинты для получения кода
        urls = [
            f"{BASE_URL}/market/item/check-account",
            f"{BASE_URL}/item/check-account"
        ]
        
        for url in urls:
            r = await client.post(url, headers=HEADERS, json={"item_id": item_id})
            
            if r.status_code == 404:
                continue
                
            if r.status_code == 403 or "нет прав" in r.text.lower():
                raise Exception("wait_please")
                
            if r.status_code != 200:
                return "Код не найден или ошибка API"
                
            data = r.json()
            phone = data.get("phone", "Номер не найден")
            code = data.get("code", "Код не найден")
            
            return f"📱 Номер: {phone}\n🔑 Код: {code}"
            
        return "Не удалось найти эндпоинт для получения кода"
