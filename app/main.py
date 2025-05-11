from fastapi import FastAPI
from apscheduler.schedulers.background import BackgroundScheduler
import time
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException
import requests,os,json
from contextlib import asynccontextmanager

cache = {}
DATA_DIR = "data"
DEALS_FILE = os.path.join(DATA_DIR, "deals.json")
STORES_FILE = os.path.join(DATA_DIR, "stores.json")

def save_json(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)

def load_json(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None



def fetch_and_cache_deals():
    print("Fetching all deals and stores...")
    get_all_deals()

def fetch_and_cache_stores():
    print("Fetching all stores...")
    get_stores()

def get_stores():
    url = "https://www.cheapshark.com/api/1.0/stores"
    response = requests.get(url)
    if response.status_code == 200:
        stores = response.json()
        cache["stores"] = stores
        save_json(STORES_FILE, stores)
        return response.json()
    return []

def get_store_ids():
    stores = get_stores()
    return [{"id": store["storeID"], "name": store["storeName"]} for store in stores]

def get_deals(store_id):
    deals = []
    page = 0
    while True:
        print(f"Fetching page {page} for store {store_id}...")
        response = requests.get("https://www.cheapshark.com/api/1.0/deals", params={
            "onSale": 1,
            "pageSize": 60,
            "pageNumber": page,
            "storeID": store_id
        })
        if response.status_code == 200:
            try:
                response_data = response.json()
                if not response_data:
                    break
                deals.extend(response_data)
                page += 1
                time.sleep(3)
            except ValueError:
                print("Error decoding JSON response")
                break
        else:
            print(f"Request failed: {response.status_code}")
            break
    return deals

def get_all_deals():
    all_deals = {}
    store_ids = get_store_ids()
    for st in store_ids[:1]:
        name = st["name"]
        id = st["id"]
        print(f"Getting deals for {name}...")
        all_deals[name] = get_deals(id)
        time.sleep(30)
    cache["deals"] = all_deals
    save_json(DEALS_FILE, all_deals)
    return all_deals


@asynccontextmanager
async def lifespan(app: FastAPI):

    print("App started, now scheduling background jobs...")
    scheduler.add_job(fetch_and_cache_deals, 'interval', hours=12)
    scheduler.add_job(fetch_and_cache_stores, 'interval', hours=12)
    scheduler.start()
    fetch_and_cache_deals()
    fetch_and_cache_stores()
    cached_deals = load_json(DEALS_FILE)
    cached_stores = load_json(STORES_FILE)

    if cached_deals:
        cache["deals"] = cached_deals
    if cached_stores:
        cache["stores"] = cached_stores

    yield

    scheduler.shutdown()
    print("Scheduler shut down")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


scheduler = BackgroundScheduler()
@app.get("/deals/")
def get_cached_deals(store_name: str = None):
    deals = cache.get("deals")
    if not deals:
        return {"error": "No cached deals available."}, 503

    if store_name:
        store_deals = deals.get(store_name)
        if store_deals is None:
            raise HTTPException(status_code=404, detail=f"No deals found for store '{store_name}'")
        return {"source": "disk", "deals": store_deals}

    return {"source": "disk", "deals": deals}

@app.get("/deals/top")
def get_top_3_deals():
    deals = cache.get("deals")
    if not deals:
        return {"error": "No cached deals available."}, 503

    all_deals = [deal for store in deals.values() for deal in store]
    top3 = sorted(all_deals, key=lambda d: float(d.get("price", 9999)))[:3]
    return {"source": "disk", "deals": top3}

@app.get("/stores")
def get_store_details():
    stores = cache.get("stores")
    if stores:
        return {"source": "disk", "stores": stores}
    return {"error": "No cached stores available."}, 503

