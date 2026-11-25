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
            r = await client.get(f"{BASE_URL}/telegram", headers=HEADERS, params=params, timeout=10.0)
            return r.json().get("items", []) if r.status_code == 200 else []
        except: return []

async def get_seller_feedback(seller_id: int): return {"positive": 100}
async def fast_buy(item_id: int, price: float): return {}
async def get_telegram_code(item_id: int): return "КОД_ЗДЕСЬ"
