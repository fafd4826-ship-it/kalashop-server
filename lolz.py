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
        for page in range(1, 3): # Уменьшили до 2 страниц для теста
            try:
                params["page"] = page
                # ВАЖНО: Убедись, что эндпоинт /telegram правильный. 
                # В API Lolz это может быть /market/telegram или /telegram/accounts
                r = await client.get(f"{BASE_URL}/telegram", headers=HEADERS, params=params)
                
                # Если ошибка — печатаем её в логи и прерываем
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

# ... (функции fast_buy и get_telegram_code оставляем без изменений) ...
