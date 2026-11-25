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
        for page in range(1, 11):
            try:
                params["page"] = page
                r = await client.get(f"{BASE_URL}/telegram", headers=HEADERS, params=params, timeout=15.0)
                if r.status_code != 200:
                    break
                data = r.json()
                items = data.get("items", [])
                if not items:
                    break
                all_items.extend(items)
            except:
                break
    return all_items

async def fast_buy(item_id: int, price: float):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/{item_id}/fast-buy", headers=HEADERS, json={"price": price}, timeout=15.0)
        if r.status_code != 200:
            raise Exception(f"Ошибка покупки: {r.text}")
        return r.json()

async def get_telegram_code(item_id: int):
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{BASE_URL}/{item_id}/telegram-code", headers=HEADERS, timeout=15.0)
        if r.status_code != 200:
            return "Код не получен (ошибка API)"
        data = r.json()
        return data.get("code", "Код не найден в ответе")
