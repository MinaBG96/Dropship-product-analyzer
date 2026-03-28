"""
product_api.py — Fixed & Hardened
===================================
Changes from original:
1. All GET endpoints are now implemented (were completely missing)
2. Task status endpoint added — users can poll job progress
3. Input validation added to ProductInput via Pydantic
4. NoSQL injection protection on all query parameters
5. Consistent error responses using FastAPI HTTPException
6. MongoDB _id field excluded from all responses (not JSON serializable)
7. Pagination added to product and ads list endpoints
8. Startup document is no longer inserted into products_collection
   (it was wrong — products are scraped data, not user requests)
"""

import re
import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, field_validator
from backend.tasks.scrape_tasks import scrape_product

from database.db import (
    products_collection,
    reports_collection,
    final_reports_collection,
    ads_collection,
    tasks_collection,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _sanitize_product_name(name: str) -> str:
    """
    FIX: Original passed product_name directly into MongoDB queries.
    A value like {"$gt": ""} would be a NoSQL injection vector.
    This strips everything except letters, numbers, spaces, and hyphens.
    """
    return re.sub(r"[^\w\s\-]", "", name).strip()


def _exclude_id(doc: dict) -> dict:
    """
    FIX: MongoDB _id is a BSON ObjectId — not JSON serializable.
    Original would crash on any endpoint that returned a raw document.
    """
    if doc and "_id" in doc:
        doc.pop("_id")
    return doc


# ------------------------------------------------------------------
# Input Model
# ------------------------------------------------------------------

class ProductInput(BaseModel):
    product_name: str
    country: str

    @field_validator("product_name")
    @classmethod
    def validate_product_name(cls, v: str) -> str:
        """
        FIX: Original accepted any string including empty, injections,
        and 10,000-character inputs.
        """
        v = v.strip()
        if not v:
            raise ValueError("product_name cannot be empty")
        if len(v) < 2:
            raise ValueError("product_name must be at least 2 characters")
        if len(v) > 200:
            raise ValueError("product_name cannot exceed 200 characters")
        # Allow only safe characters
        if re.search(r"[^\w\s\-]", v):
            raise ValueError("product_name contains invalid characters")
        return v

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("country cannot be empty")
        if len(v) > 100:
            raise ValueError("country name too long")
        return v


# ------------------------------------------------------------------
# POST /analyze
# ------------------------------------------------------------------

@router.post("/analyze")
def analyze_product(product: ProductInput):
    """
    Starts a full product analysis pipeline via Celery.

    FIX: Original inserted a document into products_collection here.
    That collection is for scraped products — not user requests.
    User requests are now tracked in tasks_collection instead.

    FIX: Returns task_id so the user can poll /status for progress.
    """
    safe_name = _sanitize_product_name(product.product_name)

    # Check if analysis is already running for this product + country
    existing = tasks_collection.find_one({
        "product_name": safe_name,
        "country":      product.country,
        "status":       "running",
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Analysis for '{safe_name}' in '{product.country}' is already running."
        )

    # Create task tracking document
    tasks_collection.update_one(
        {"product_name": safe_name, "country": product.country},
        {"$set": {
            "product_name": safe_name,
            "country":      product.country,
            "status":       "queued",
        }},
        upsert=True
    )

    # Send to Celery
    task = scrape_product.delay(safe_name, product.country)

    logger.info("Task queued: product='%s', task_id='%s'", safe_name, task.id)

    return {
        "status":  "queued",
        "task_id": task.id,
        "message": f"Analysis started for '{safe_name}'"
    }


# ------------------------------------------------------------------
# GET /status/{product_name}
# ------------------------------------------------------------------

@router.get("/status/{product_name}")
def get_task_status(product_name: str, country: str = Query(...)):
    """
    FIX: This endpoint did not exist in the original.
    Users had no way to know if their analysis finished, failed,
    or was still running after POST /analyze.

    Poll this endpoint after submitting an analysis.
    Requires country as a query param: /status/electric brush?country=Saudi Arabia
    """
    safe_name = _sanitize_product_name(product_name)

    task = tasks_collection.find_one(
        {"product_name": safe_name, "country": country},
        {"_id": 0}  # exclude _id at query level
    )

    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for '{safe_name}' in '{country}'"
        )

    return task


# ------------------------------------------------------------------
# GET /report/{product_name}
# ------------------------------------------------------------------

@router.get("/report/{product_name}")
def get_final_report(product_name: str, country: str = Query(...)):
    """
    FIX: This endpoint was documented but never implemented.
    Returns the final combined report with score and recommendation.

    Requires country as query param: /report/electric brush?country=Saudi Arabia
    """
    safe_name = _sanitize_product_name(product_name)

    report = final_reports_collection.find_one(
        {"product": safe_name, "country": country},
        {"_id": 0}
    )

    if not report:
        # Check if analysis is still running
        task = tasks_collection.find_one(
            {"product_name": safe_name, "country": country},
            {"_id": 0}
        )
        if task and task.get("status") == "running":
            raise HTTPException(
                status_code=202,
                detail="Analysis is still running. Poll /status for updates."
            )
        raise HTTPException(
            status_code=404,
            detail=f"No report found for '{safe_name}'. Run POST /analyze first."
        )

    return report


# ------------------------------------------------------------------
# GET /reports/{product_name}
# ------------------------------------------------------------------

@router.get("/reports/{product_name}")
def get_platform_reports(product_name: str, country: str = Query(...)):
    """
    FIX: This endpoint was documented but never implemented.
    Returns individual analysis report for each platform (AliExpress, Amazon).
    """
    safe_name = _sanitize_product_name(product_name)

    cursor = reports_collection.find(
        {"product": safe_name, "country": country},
        {"_id": 0}
    )

    results = list(cursor)

    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"No platform reports found for '{safe_name}'."
        )

    return results


# ------------------------------------------------------------------
# GET /products/{product_name}
# ------------------------------------------------------------------

@router.get("/products/{product_name}")
def get_products(
    product_name: str,
    country: str  = Query(...),
    source: str   = Query(None, description="Filter by source: aliexpress or amazon"),
    page: int     = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    FIX: This endpoint was documented but never implemented.
    FIX: Pagination added — original would dump all products with no limit.
    FIX: Optional source filter so caller can request only AliExpress or Amazon.
    """
    safe_name = _sanitize_product_name(product_name)

    query: dict = {"product_name": safe_name}

    if source:
        if source not in ("aliexpress", "amazon"):
            raise HTTPException(
                status_code=400,
                detail="source must be 'aliexpress' or 'amazon'"
            )
        query["source"] = source

    skip  = (page - 1) * page_size
    total = products_collection.count_documents(query)

    cursor = products_collection.find(query, {"_id": 0}).skip(skip).limit(page_size)
    items  = list(cursor)

    return {
        "product":   safe_name,
        "source":    source or "all",
        "page":      page,
        "page_size": page_size,
        "total":     total,
        "results":   items,
    }


# ------------------------------------------------------------------
# GET /ads/{product_name}
# ------------------------------------------------------------------

@router.get("/ads/{product_name}")
def get_ads(
    product_name: str,
    page: int      = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """
    FIX: This endpoint was documented but never implemented.
    FIX: Pagination added.
    """
    safe_name = _sanitize_product_name(product_name)

    query = {"product": safe_name}
    skip  = (page - 1) * page_size
    total = ads_collection.count_documents(query)

    cursor = ads_collection.find(query, {"_id": 0}).skip(skip).limit(page_size)
    items  = list(cursor)

    if total == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No ads found for '{safe_name}'."
        )

    return {
        "product":   safe_name,
        "page":      page,
        "page_size": page_size,
        "total":     total,
        "results":   items,
    }