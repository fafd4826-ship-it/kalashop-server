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
                if r.status_code != 200: break
                data = r.json()
                items = data.get("items", [])
                if not items: break
                all_items.extend(items)
            except: break
    return all_items

async def fast_buy(item_id: int, price: float):
    async with httpx.AsyncClient() as client:
        payload = {"item_id": item_id, "price": price}
        
        # Оставляем только один самый вероятный эндпоинт для покупки
        # (Если Lolz опять выдаст 404, мы поймем, что дело в токене)
        url = f"{BASE_URL}/item/buy"
        
        r = await client.post(url, headers=HEADERS, json=payload)
        
        # Если Lolz вернул ошибку, мы покажем её пользователю, а не будем молчать
        if r.status_code != 200:
            # Если 401/403 - скорее всего токен без прав
            if r.status_code in [401, 403]:
                raise Exception(f"У токена нет прав на покупку! Код: {r.status_code}. Ответ: {r.text}")
            
            # Если 404 - возможно, эндпоинт неверный
            if r.status_code == 404:
                raise Exception(f"Lolz пишет 'Страница не найдена'. Возможно, неверный URL в коде.")
                
            raise Exception(f"Ошибка Lolz ({r.status_code}): {r.text}")
            
        return r.json()

async def get_telegram_code(item_id: int):
    async with httpx.AsyncClient() as client:
        # Аналогично для получения кода
        url = f"{BASE_URL}/item/check-account"
        r = await client.post(url, headers=HEADERS, json={"item_id": item_id})
        
        if r.status_code == 403 or "нет прав" in r.text.lower():
            raise Exception("wait_please")
            
        if r.status_code != 200:
            return f"Ошибка API Lolz ({r.status_code}): {r.text}"
            
        data = r.json()
        phone = data.get("phone", "Номер не найден")
        code = data.get("code", "Код не найден")
        
        return f"📱 Номер: {phone}\n🔑 Код: {code}"
