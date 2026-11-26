import json
import os
import datetime

USERS_FILE = "users.json"
PROMOS_FILE = "promos.json"
PURCHASES_FILE = "purchases.json"
NAMES_FILE = "usernames.json"

def load_json(filename):
    if not os.path.exists(filename): return {}
    with open(filename, "r") as f:
        try: return json.load(f)
        except: return {}

def save_json(filename, data):
    with open(filename, "w") as f:
        json.dump(data, f, indent=4)

# --- Баланс ---
def get_balance(user_id):
    db = load_json(USERS_FILE)
    return db.get(str(user_id), 0)

def update_balance(user_id, amount):
    db = load_json(USERS_FILE)
    uid = str(user_id)
    db[uid] = db.get(uid, 0) + amount
    save_json(USERS_FILE, db)

# --- Юзернеймы (чтобы переводы работали) ---
def save_username(user_id, username):
    if not username: return
    db = load_json(NAMES_FILE)
    db[username.lower()] = user_id
    save_json(NAMES_FILE, db)

def get_id_by_username(username):
    db = load_json(NAMES_FILE)
    return db.get(username.lower().replace("@", ""))

# --- Промокоды ---
def add_promo(code, amount):
    db = load_json(PROMOS_FILE)
    db[code.upper()] = {"amount": amount, "uses_left": 1}
    save_json(PROMOS_FILE, db)

def use_promo(code):
    db = load_json(PROMOS_FILE)
    code = code.upper()
    if code in db and db[code]["uses_left"] > 0:
        amount = db[code]["amount"]
        del db[code]
        save_json(PROMOS_FILE, db)
        return amount
    return None

# --- История покупок ---
def add_purchase(buyer_id, buyer_username, item_id, price):
    db = load_json(PURCHASES_FILE)
    if not isinstance(db, list): db = []
    db.append({
        "buyer_id": buyer_id,
        "buyer_username": buyer_username,
        "item_id": item_id,
        "price": price,
        "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    save_json(PURCHASES_FILE, db)
