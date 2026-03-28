"""
scrape_tasks.py — Fixed & Hardened
====================================
Changes from original:
1. Scoring formula completely rewritten — uses weighted multi-factor model
2. Variable name collision fixed (amazon_products was overwritten)
3. Bare except clauses replaced with proper exception handling + logging
4. Duplicate prevention using MongoDB upsert
5. Task status tracking — DB document updated at each pipeline stage
6. Partial failure handling — report generates even if one scraper fails
7. Data quality from market_analyzer now feeds into score confidence
8. report_generator.py is now actually used
9. All score sub-components are stored in final report for transparency
"""

import logging
from backend.celery_worker import celery_app
from backend.scrapers.aliexpress_scraper import scrape_aliexpress
from backend.scrapers.amazon_scraper import scrape_amazon
from backend.analyzer.market_analyzer import analyze_market
from backend.analyzer.product_filter import is_relevant
from backend.analysis.report_generator import generate_final_report
from backend.scrapers.facebook_ads import search_facebook_ads

from database.db import (
    products_collection,
    reports_collection,
    final_reports_collection,
    ads_collection,
    tasks_collection,        # NEW: track task status per job
)

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Scoring weights — must sum to 1.0
# Demand is weighted highest because it is the strongest
# signal of a sellable product.
# ------------------------------------------------------------------
SCORE_WEIGHTS = {
    "demand":      0.40,
    "profit":      0.30,
    "competition": 0.20,
    "data_quality": 0.10,
}


def _update_task_status(product_name: str, country: str, status: str, extra: dict = None):
    """
    FIX: Original never updated task status after starting.
    Users had no way to know if analysis finished, failed, or was still running.
    Now every pipeline stage updates the task document.
    """
    update = {"status": status}
    if extra:
        update.update(extra)

    tasks_collection.update_one(
        {"product_name": product_name, "country": country},
        {"$set": update},
        upsert=True
    )


def _calculate_demand_score(ali: dict, amazon: dict) -> float:
    """
    Demand score (0-100) based on orders across both platforms.

    FIX: Original used avg_rating * 20 — rating is NOT demand.
    A product with 5-star rating and 0 orders is not in demand.

    Logic:
    - AliExpress orders = actual purchases (stronger signal)
    - Amazon reviews = ~2-5% of buyers, so we multiply by 30 as proxy
    - Score is normalized against thresholds for dropshipping context
    """
    ali_orders    = ali.get("avg_orders", 0) or 0
    amazon_reviews = amazon.get("avg_orders", 0) or 0

    # Amazon reviews are ~2-5% of actual buyers — scale up as proxy
    amazon_orders_proxy = amazon_reviews * 30

    # Combine: AliExpress is primary demand signal
    combined_orders = (ali_orders * 0.6) + (amazon_orders_proxy * 0.4)

    # Normalize to 0-100
    # Thresholds based on dropshipping context:
    # < 100 orders = weak demand
    # 500+ orders = strong demand
    # 2000+ orders = very strong demand
    if combined_orders >= 2000:
        return 100.0
    elif combined_orders >= 500:
        return 70.0 + ((combined_orders - 500) / 1500) * 30
    elif combined_orders >= 100:
        return 40.0 + ((combined_orders - 100) / 400) * 30
    else:
        return max(0.0, (combined_orders / 100) * 40)


def _calculate_profit_score(ali: dict, amazon: dict) -> float:
    """
    Profit score (0-100) based on price gap between AliExpress (supplier)
    and Amazon (market price).

    FIX: Original never calculated profit at all.
    FIX: Both prices are now in USD (from market_analyzer), so comparison is valid.

    Logic:
    - Profit margin = (amazon_price - ali_price) / amazon_price
    - 50%+ margin = excellent for dropshipping
    - 20-50% margin = acceptable
    - < 20% margin = too thin (fees eat it)
    """
    ali_price    = ali.get("avg_price_usd", 0) or 0
    amazon_price = amazon.get("avg_price_usd", 0) or 0

    # Cannot calculate without both prices
    if ali_price <= 0 or amazon_price <= 0:
        logger.warning("Missing prices for profit calculation — returning neutral score 50")
        return 50.0

    # If AliExpress is more expensive than Amazon, margin is negative
    if ali_price >= amazon_price:
        return 0.0

    margin = (amazon_price - ali_price) / amazon_price

    if margin >= 0.60:
        return 100.0
    elif margin >= 0.50:
        return 85.0
    elif margin >= 0.35:
        return 65.0
    elif margin >= 0.20:
        return 40.0
    else:
        return max(0.0, margin * 200)  # linear below 20%


def _calculate_competition_score(ali: dict, amazon: dict) -> float:
    """
    Competition score (0-100) — HIGHER score means LOWER competition (better).

    FIX: Original did not calculate competition score at all.

    Logic:
    - Use competition level from both platforms
    - Low competition = high score (good for new dropshippers)
    - High competition = low score
    """
    level_scores = {"low": 90.0, "medium": 55.0, "high": 20.0, "unknown": 50.0}

    ali_score    = level_scores.get(ali.get("competition", "unknown"), 50.0)
    amazon_score = level_scores.get(amazon.get("competition", "unknown"), 50.0)

    return round((ali_score * 0.5) + (amazon_score * 0.5), 2)


def _calculate_data_quality_score(ali: dict, amazon: dict) -> float:
    """
    Data quality score (0-100) — how much can we trust this analysis?

    FIX: Original had no concept of data quality.
    A report built on 2 products with all fabricated ratings should
    score lower than one built on 20 products with real data.

    This score penalizes:
    - Low product count
    - High ratio of defaulted/fabricated ratings
    - Many unknown currencies (prices that couldn't be converted)
    """
    score = 100.0

    # Penalize low product count
    ali_count    = ali.get("products_found", 0)
    amazon_count = amazon.get("products_found", 0)
    total        = ali_count + amazon_count

    if total < 5:
        score -= 40
    elif total < 10:
        score -= 20
    elif total < 15:
        score -= 10

    # Penalize fabricated ratings
    for market in [ali, amazon]:
        dq = market.get("data_quality", {})
        real      = dq.get("ratings_real", 0)
        defaulted = dq.get("ratings_defaulted", 0)
        total_ratings = real + defaulted

        if total_ratings > 0:
            fabrication_ratio = defaulted / total_ratings
            score -= fabrication_ratio * 20  # max -20 per market

        # Penalize unknown currencies
        unknown = dq.get("unknown_currencies", 0)
        if unknown > 0:
            score -= min(unknown * 5, 20)  # max -20 for unknown currencies

    return max(0.0, round(score, 2))


def _build_final_score(ali: dict, amazon: dict) -> dict:
    """
    Builds the weighted final score from all sub-components.

    FIX: Original had one line: avg_rating * 20. That was not a scoring engine.
    This implements the weighted formula from the README properly.

    Returns full breakdown so the report is transparent and explainable.
    """
    demand_score      = _calculate_demand_score(ali, amazon)
    profit_score      = _calculate_profit_score(ali, amazon)
    competition_score = _calculate_competition_score(ali, amazon)
    quality_score     = _calculate_data_quality_score(ali, amazon)

    final_score = (
        demand_score      * SCORE_WEIGHTS["demand"]      +
        profit_score      * SCORE_WEIGHTS["profit"]      +
        competition_score * SCORE_WEIGHTS["competition"] +
        quality_score     * SCORE_WEIGHTS["data_quality"]
    )
    final_score = round(final_score, 2)

    # Recommendation tiers
    if final_score >= 75:
        recommendation = "Winning product"
        confidence     = "high"
    elif final_score >= 55:
        recommendation = "Potential product — needs more research"
        confidence     = "medium"
    elif final_score >= 35:
        recommendation = "Weak product — significant risks"
        confidence     = "low"
    else:
        recommendation = "Not recommended"
        confidence     = "low"

    return {
        "score":          final_score,
        "recommendation": recommendation,
        "confidence":     confidence,
        "breakdown": {
            "demand_score":      round(demand_score, 2),
            "profit_score":      round(profit_score, 2),
            "competition_score": round(competition_score, 2),
            "data_quality_score": round(quality_score, 2),
        },
        "weights_used": SCORE_WEIGHTS,
    }


@celery_app.task(bind=True, max_retries=2)
def scrape_product(self, product_name: str, country: str):
    """
    Main Celery task — orchestrates the full scraping and analysis pipeline.

    bind=True gives access to self for retry logic.
    max_retries=2 means the task will retry twice on unexpected failure.
    """
    logger.info("Task started: product='%s', country='%s'", product_name, country)

    # ---------------------------------------------------------------
    # 0) Mark task as running
    # ---------------------------------------------------------------
    _update_task_status(product_name, country, "running")

    try:
        # -----------------------------------------------------------
        # 1) Scraping — each scraper is independent
        #    FIX: Original crashed entirely if Amazon scraper failed.
        #    Now each scraper failure is logged and pipeline continues.
        # -----------------------------------------------------------
        aliexpress_raw = []
        amazon_raw     = []
        facebook_ads   = []

        try:
            aliexpress_raw = scrape_aliexpress(product_name)
            logger.info("AliExpress: %d raw results", len(aliexpress_raw))
        except Exception as e:
            logger.error("AliExpress scraper failed: %s", e)
            _update_task_status(product_name, country, "running",
                                {"aliexpress_error": str(e)})

        try:
            amazon_raw = scrape_amazon(product_name)
            logger.info("Amazon: %d raw results", len(amazon_raw))
        except Exception as e:
            logger.error("Amazon scraper failed: %s", e)
            _update_task_status(product_name, country, "running",
                                {"amazon_error": str(e)})

        try:
            facebook_ads = search_facebook_ads(product_name)
            logger.info("Facebook Ads: %d results", len(facebook_ads))
        except Exception as e:
            logger.error("Facebook scraper failed: %s", e)

        # -----------------------------------------------------------
        # 2) Save Facebook ads
        # -----------------------------------------------------------
        for ad in facebook_ads:
            try:
                ads_collection.update_one(
                    {"product": product_name, "link": ad.get("link")},
                    {"$setOnInsert": {"product": product_name, "country": country, **ad}},
                    upsert=True  # FIX: no duplicate ads on re-run
                )
            except Exception as e:
                logger.warning("Failed to save ad: %s", e)

        # -----------------------------------------------------------
        # 3) Filter + save products
        #    FIX: variable name collision — amazon_raw never overwritten
        #    FIX: upsert prevents duplicate products on re-run
        # -----------------------------------------------------------
        ali_saved    = []
        amazon_saved = []

        for product in aliexpress_raw:
            title = product.get("title", "")
            if not is_relevant(title, product_name):
                continue
            try:
                products_collection.update_one(
                    {"title": title, "source": "aliexpress"},
                    {"$setOnInsert": product},
                    upsert=True
                )
                ali_saved.append(product)
            except Exception as e:
                logger.warning("Failed to save AliExpress product: %s", e)

        for product in amazon_raw:
            title = product.get("title", "")
            if not is_relevant(title, product_name):
                continue
            try:
                products_collection.update_one(
                    {"title": title, "source": "amazon"},
                    {"$setOnInsert": product},
                    upsert=True
                )
                amazon_saved.append(product)
            except Exception as e:
                logger.warning("Failed to save Amazon product: %s", e)

        logger.info("Saved: %d AliExpress, %d Amazon", len(ali_saved), len(amazon_saved))

        # Abort only if BOTH scrapers returned nothing
        if not ali_saved and not amazon_saved:
            _update_task_status(product_name, country, "failed",
                                {"error": "No relevant products found from any source"})
            return {"status": "failed", "reason": "no_products_found"}

        # -----------------------------------------------------------
        # 4) Analyze each market separately
        #    FIX: platform name passed explicitly — no more source detection inside loop
        # -----------------------------------------------------------
        ali_analysis    = analyze_market(ali_saved,    platform="aliexpress")
        amazon_analysis = analyze_market(amazon_saved, platform="amazon")

        # -----------------------------------------------------------
        # 5) Save platform reports (upsert — no duplicates on re-run)
        # -----------------------------------------------------------
        for platform, analysis in [("aliexpress", ali_analysis), ("amazon", amazon_analysis)]:
            reports_collection.update_one(
                {"product": product_name, "country": country, "platform": platform},
                {"$set": {
                    "product":  product_name,
                    "country":  country,
                    "platform": platform,
                    "analysis": analysis,
                }},
                upsert=True
            )

        logger.info("Platform reports saved")

        # -----------------------------------------------------------
        # 6) Build final score
        #    FIX: Real weighted scoring formula — not avg_rating * 20
        # -----------------------------------------------------------
        final_analysis = _build_final_score(ali_analysis, amazon_analysis)

        # -----------------------------------------------------------
        # 7) Generate and save final report via report_generator
        #    FIX: report_generator.py is now actually called
        # -----------------------------------------------------------
        final_report = generate_final_report(
            product_name=product_name,
            country=country,
            markets={
                "aliexpress": ali_analysis,
                "amazon":     amazon_analysis,
            },
            final_analysis=final_analysis,
            ads_count=len(facebook_ads),
        )

        final_reports_collection.update_one(
            {"product": product_name, "country": country},
            {"$set": final_report},
            upsert=True
        )

        logger.info("Final report saved. Score: %s", final_analysis["score"])

        # -----------------------------------------------------------
        # 8) Mark task complete
        # -----------------------------------------------------------
        _update_task_status(product_name, country, "completed", {
            "score":          final_analysis["score"],
            "recommendation": final_analysis["recommendation"],
        })

        return {
            "status":   "completed",
            "score":    final_analysis["score"],
            "recommendation": final_analysis["recommendation"],
        }

    except Exception as e:
        logger.error("Unhandled task failure: %s", e, exc_info=True)
        _update_task_status(product_name, country, "failed", {"error": str(e)})

        # Retry the task (max_retries=2)
        raise self.retry(exc=e, countdown=30)