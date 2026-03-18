from fastapi import APIRouter
from backend.models.product_model import ProductInput
from backend.tasks.scrape_tasks import scrape_product
from database.db import products_collection

router = APIRouter()

@router.post("/analyze-product")
def analyze_product(product: ProductInput):

    # حفظ المنتج في database
    product_data = {
        "product_name": product.product_name,
        "country": product.country,
        "status": "queued"
    }

    products_collection.insert_one(product_data)

    # إرسال task إلى Celery
    task = scrape_product.delay(
        product.product_name,
        product.country
    )

    return {
        "message": "Analysis started",
        "task_id": task.id
    }