import requests
import time
from fastapi import FastAPI
from starlette.responses import JSONResponse
from apscheduler.schedulers.background import BackgroundScheduler
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi import HTTPException

cache = {}

def get_stores():
    url = "https://www.cheapshark.com/api/1.0/stores"
    response = requests.get(url)
    cache["stores"] = response.json()
    return response.json() if response.status_code == 200 else []

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
    return all_deals

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler()
    scheduler.add_job(get_all_deals, 'interval', hours=1)
    scheduler.add_job(get_stores, 'interval', hours=12)
    scheduler.start()


    print("Starting background jobs for data fetching...")
    get_all_deals()
    get_stores()

    yield
    scheduler.shutdown()
    print("Scheduler shut down")

app = FastAPI(lifespan=lifespan)

# Allow CORS from all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/deals/")
def get_cached_deals(store_name: str = None):
    deals = cache.get("deals")
    if not deals:
        return JSONResponse(content={"error": "No cached deals available."}, status_code=503)

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
        return JSONResponse(content={"error": "No cached deals available."}, status_code=503)

    all_deals = [deal for store in deals.values() for deal in store]
    top3 = sorted(all_deals, key=lambda d: float(d.get("price", 9999)))[:3]
    return {"source": "disk", "deals": top3}

@app.get("/stores")
def get_store_details():
    stores = cache.get("stores")
    if stores:
        return JSONResponse(content={"source": "disk", "stores": stores})
    return JSONResponse(content={"error": "No cached stores available."}, status_code=503)
