from fastapi import FastAPI
from backend.api.product_api import router

app = FastAPI()

app.include_router(router)

@app.get("/")
def home():
    
    return {"message": "Dropship Product Analyzer API Running"}