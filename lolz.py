import httpx
from config import LOLZTEAM_TOKEN

BASE_URL = "https://api.lzt.market"
HEADERS = {"Authorization": f"Bearer {LOLZTEAM_TOKEN}", "Accept": "application/json"}

async def search_telegram(country: str = None, query: str = None):
    params = {"pmax": 10000, "pmin": 0}
    if country: params["country"] = country
    if query: params["keyword"] = query
    
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{BASE_URL}/telegram", headers=HEADERS, params=params, timeout=15.0)
            if r.status_code != 200:
                print(f"❌ ОШИБКА LOLZTEAM: Код {r.status_code}. Ответ: {r.text}")
                return []
            
            data = r.json()
            items = data.get("items", [])
            print(f"✅ LOLZTEAM ВЕРНУЛ: {len(items)} аккаунтов")
            return items
        except Exception as e:
            print(f"❌ ОШИБКА СЕТИ: {e}")
            return []
