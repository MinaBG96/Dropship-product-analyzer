from backend.celery_worker import celery_app
from backend.scrapers.aliexpress_scraper import scrape_aliexpress
from backend.scrapers.amazon_scraper import scrape_amazon
from backend.analyzer.market_analyzer import analyze_market
from backend.analyzer.product_filter import is_relevant
from backend.scrapers.facebook_ads import search_facebook_ads

from database.db import (
    products_collection,
    reports_collection,
    final_reports_collection,
    ads_collection
)


@celery_app.task
def scrape_product(product_name, country):

    print("TASK STARTED")

    # ========================
    # 1) Scraping
    # ========================

    aliexpress_products = scrape_aliexpress(product_name)
    print("AliExpress raw:", len(aliexpress_products))
    # ========================
    # Facebook Ads
    # ========================

    try:
        facebook_ads = search_facebook_ads(product_name)
    except:
        facebook_ads = []

    print("Facebook Ads:", len(facebook_ads))


    for ad in facebook_ads:
        try:
            ads_collection.insert_one({
                "product": product_name,
                "country": country,
                **ad
            })
        except:
            continue

    try:
        amazon_products = scrape_amazon(product_name)
    except:
        amazon_products = []

    

    # ========================
    # 2) Merge + Filter + Save
    # ========================

    saved_products = []

    all_products = aliexpress_products + amazon_products

    for product in all_products:

        title = product.get("title")

        if not is_relevant(title, product_name):
            continue

        try:
            products_collection.insert_one(product)
            saved_products.append(product)
        except:
            continue

    print("Saved Products:", len(saved_products))

    # ========================
    # 3) Split by source
    # ========================

    ali_products = [p for p in saved_products if p.get("source") == "aliexpress"]
    amazon_products = [p for p in saved_products if p.get("source") == "amazon"]

    # ========================
    # 4) Analyze each market
    # ========================

    ali_analysis = analyze_market(ali_products)
    amazon_analysis = analyze_market(amazon_products)

    # ========================
    # 5) Save platform reports
    # ========================

    ali_report = {
        "product": product_name,
        "country": country,
        "platform": "aliexpress",
        "analysis": ali_analysis,
    }

    amazon_report = {
        "product": product_name,
        "country": country,
        "platform": "amazon",
        "analysis": amazon_analysis,
    }

    reports_collection.insert_one(ali_report)
    reports_collection.insert_one(amazon_report)

    print("Platform Reports Saved")

    # ========================
    # 6) Final Analysis
    # ========================

    final_score = (
        ali_analysis["avg_rating"] * 20 + amazon_analysis["avg_rating"] * 20
    ) / 2

    recommendation = "🔥 Winning Product" if final_score > 70 else "❌ Not Recommended"

    # ========================
    # 7) Final Report
    # ========================

    final_report = {
        "product": product_name,
        "country": country,
        "markets": {"aliexpress": ali_analysis, "amazon": amazon_analysis},
        "final_analysis": {
            "score": round(final_score, 2),
            "recommendation": recommendation,
        },
    }

    final_reports_collection.insert_one(final_report)

    print("Final Report Saved")

    # ========================
    # 8) Return
    # ========================

    return {"status": "completed", "reports_created": 3}
