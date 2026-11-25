import httpx
from config import LOLZTEAM_TOKEN

BASE_URL = "https://api.lzt.market"
HEADERS = {"Authorization": f"Bearer {LOLZTEAM_TOKEN}", "Accept": "application/json"}

async def search_telegram(country: str = None, query: str = None):
    params = {"pmax": 10000, "pmin": 0}
    if country: params["country"] = country
    if query: params["keyword"] = query
    
    all_items = []
    async with httpx.AsyncClient() as client:
        # Скачиваем первые 10 страниц
        for page in range(1, 11):
            try:
                params["page"] = page
                r = await client.get(f"{BASE_URL}/telegram", headers=HEADERS, params=params, timeout=15.0)
                
                if r.status_code != 200:
                    print(f"❌ ОШИБКА LOLZTEAM: {r.status_code}")
                    break
                
                data = r.json()
                items = data.get("items", [])
                if not items:
                    break # Если аккаунты закончились
                    
                all_items.extend(items)
                
            except Exception as e:
                print(f"❌ ОШИБКА СЕТИ: {e}")
                break
                
    print(f"✅ LOLZTEAM ВЕРНУЛ: {len(all_items)} аккаунтов (с 10 страниц)")
    return all_items
