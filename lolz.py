import httpx
from config import LOLZTEAM_TOKEN

BASE_URL = "https://api.lzt.market"
HEADERS = {"Authorization": f"Bearer {LOLZTEAM_TOKEN}", "Accept": "application/json"}

async def search_telegram(country: str = None, query: str = None):
    params = {}
    if country: params["country"] = country
    if query: params["keyword"] = query
    
    all_items = []
    async with httpx.AsyncClient() as client:
        for page in range(1, 11):
            try:
                params["page"] = page
                r = await client.get(f"{BASE_URL}/telegram", headers=HEADERS, params=params, timeout=15.0)
                if r.status_code != 200: break
                data = r.json()
                items = data.get("items", [])
                if not items: break
                all_items.extend(items)
            except: break
    return all_items

async def fast_buy(item_id: int, price: float):
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{BASE_URL}/{item_id}/fast-buy", headers=HEADERS, json={"price": price}, timeout=10.0)
            if r.status_code != 200:
                if r.status_code == 400: raise Exception("Аккаунт уже продан или изменилась цена.")
                elif r.status_code == 403: raise Exception("НЕТ ПРАВ (403). Токен не имеет доступа к покупкам.")
                elif r.status_code == 402: raise Exception("НЕДОСТАТОЧНО СРЕДСТВ на балансе Lolzteam.")
                raise Exception(f"Ошибка API ({r.status_code}): {r.text}")
            return r.json()
        except httpx.TimeoutException:
            raise Exception("Сервер Lolzteam не ответил вовремя (таймаут).")

async def get_item_info(item_id: int):
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{BASE_URL}/{item_id}", headers=HEADERS, timeout=5.0)
            if r.status_code == 200:
                return r.json().get("item", {})
            return {}
        except:
            return {}

async def get_telegram_code(item_id: int):
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{BASE_URL}/{item_id}/telegram-code", headers=HEADERS, timeout=10.0)
            if r.status_code != 200: return f"Ошибка API: {r.text}"
            data = r.json()
            return data.get("code", "Код не найден")
        except:
            return "Ошибка сети при получении кода"

async def get_lolz_balance():
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{BASE_URL}/me", headers=HEADERS, timeout=10.0)
            if r.status_code == 200:
                data = r.json()
                if "user" in data and "balance" in data["user"]:
                    return float(data["user"]["balance"])
                elif "balance" in data:
                    return float(data["balance"])
            return 0.0
        except:
            return 0.0
