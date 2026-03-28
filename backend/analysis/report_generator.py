"""
report_generator.py — Fixed & Hardened
========================================
Changes from original:
1. File was essentially empty — returned a hardcoded placeholder with zeros
2. Was never called anywhere in the codebase
3. Now generates a complete, structured final report
4. Includes human-readable interpretation of every score component
5. Includes data reliability warnings when quality is low
6. Includes actionable recommendations based on score breakdown
7. Includes market comparison summary (price gap, demand gap)
8. Timestamps every report for cache/freshness tracking
9. Called properly from scrape_tasks.py
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Thresholds for human-readable interpretation
# ------------------------------------------------------------------

def _interpret_score(score: float, label: str) -> str:
    """
    Converts a 0-100 sub-score into a human-readable label.
    Used in the report so users understand what the number means.
    """
    if score >= 75:
        return f"{label}: Strong"
    elif score >= 50:
        return f"{label}: Moderate"
    elif score >= 25:
        return f"{label}: Weak"
    else:
        return f"{label}: Very weak"


def _build_warnings(markets: dict) -> list[str]:
    """
    Generates a list of data quality warnings to include in the report.
    These warn the user when the analysis is based on unreliable data
    so they do not blindly trust a score built on fabricated ratings
    or unrecognized currency values.

    FIX: Original had no concept of warnings — a score of 82.7 looked
    equally trustworthy whether it was based on 20 real products or
    2 products with all ratings defaulted to 3.5.
    """
    warnings = []

    for platform, analysis in markets.items():
        dq = analysis.get("data_quality", {})

        products_found   = analysis.get("products_found", 0)
        ratings_real     = dq.get("ratings_real", 0)
        ratings_defaulted = dq.get("ratings_defaulted", 0)
        unknown_currencies = dq.get("unknown_currencies", 0)
        orders_parsed    = dq.get("orders_parsed", 0)

        if products_found == 0:
            warnings.append(
                f"{platform.capitalize()}: No products found — "
                f"this platform was excluded from scoring."
            )
            continue

        if products_found < 5:
            warnings.append(
                f"{platform.capitalize()}: Only {products_found} products found — "
                f"small sample, treat results with caution."
            )

        total_ratings = ratings_real + ratings_defaulted
        if total_ratings > 0:
            fabrication_ratio = ratings_defaulted / total_ratings
            if fabrication_ratio > 0.5:
                warnings.append(
                    f"{platform.capitalize()}: {ratings_defaulted} out of "
                    f"{total_ratings} ratings were missing and replaced with "
                    f"a default value of 3.5 — average rating may be inaccurate."
                )

        if unknown_currencies > 0:
            warnings.append(
                f"{platform.capitalize()}: {unknown_currencies} product(s) had "
                f"unrecognized currency — excluded from price analysis."
            )

        if orders_parsed == 0:
            warnings.append(
                f"{platform.capitalize()}: No order/review data could be parsed — "
                f"demand score for this platform is estimated."
            )

    return warnings


def _build_market_comparison(markets: dict) -> dict:
    """
    Builds a side-by-side market comparison block.
    This is the section that shows the price gap between AliExpress
    (supplier cost) and Amazon (market price) — the core profit signal.

    FIX: Original never compared markets at all.
    """
    ali    = markets.get("aliexpress", {})
    amazon = markets.get("amazon", {})

    ali_price    = ali.get("avg_price_usd", 0) or 0
    amazon_price = amazon.get("avg_price_usd", 0) or 0

    price_gap     = round(amazon_price - ali_price, 2)
    margin_pct    = 0.0

    if amazon_price > 0 and ali_price > 0:
        margin_pct = round(((amazon_price - ali_price) / amazon_price) * 100, 1)

    ali_orders    = ali.get("avg_orders", 0) or 0
    amazon_orders = amazon.get("avg_orders", 0) or 0

    return {
        "price_gap_usd":       price_gap,
        "estimated_margin_pct": margin_pct,
        "margin_interpretation": (
            "Excellent margin" if margin_pct >= 50 else
            "Acceptable margin" if margin_pct >= 30 else
            "Thin margin — high risk" if margin_pct >= 15 else
            "Negative or no margin" if margin_pct <= 0 else
            "Insufficient data"
        ),
        "demand_comparison": {
            "aliexpress_avg_orders": ali_orders,
            "amazon_avg_reviews":    amazon_orders,
            "stronger_demand_signal": (
                "aliexpress" if ali_orders > amazon_orders * 30
                else "amazon" if amazon_orders > 0
                else "insufficient data"
            )
        },
        "competition_comparison": {
            "aliexpress": ali.get("competition", "unknown"),
            "amazon":     amazon.get("competition", "unknown"),
        }
    }


def _build_action_items(final_analysis: dict, warnings: list) -> list[str]:
    """
    Generates specific, actionable next steps based on the score breakdown.
    This is what separates a useful report from a number on a screen.

    FIX: Original had no actionable output — just a score and emoji.
    """
    actions      = []
    breakdown    = final_analysis.get("breakdown", {})
    score        = final_analysis.get("score", 0)
    confidence   = final_analysis.get("confidence", "low")

    demand_score      = breakdown.get("demand_score", 0)
    profit_score      = breakdown.get("profit_score", 0)
    competition_score = breakdown.get("competition_score", 0)
    quality_score     = breakdown.get("data_quality_score", 0)

    # Demand actions
    if demand_score < 40:
        actions.append(
            "Demand is weak — validate with Google Trends before investing. "
            "Look for seasonal spikes rather than consistent interest."
        )
    elif demand_score >= 70:
        actions.append(
            "Strong demand signal — move quickly. "
            "High demand products attract competitors fast."
        )

    # Profit actions
    if profit_score < 30:
        actions.append(
            "Profit margin is thin — negotiate a lower supplier price on AliExpress "
            "or find an alternative supplier before listing."
        )
    elif profit_score >= 70:
        actions.append(
            "Good profit margin — factor in shipping, platform fees (8-15%), "
            "and ad spend before finalizing your price."
        )

    # Competition actions
    if competition_score < 40:
        actions.append(
            "High competition detected — differentiate through bundling, "
            "better photography, or targeting a niche audience."
        )
    elif competition_score >= 75:
        actions.append(
            "Low competition — opportunity to establish early. "
            "Consider building a brand rather than just dropshipping."
        )

    # Data quality actions
    if quality_score < 50:
        actions.append(
            "Data quality is low — re-run the analysis after 24 hours "
            "or manually verify prices and order counts on each platform."
        )

    # Warning-driven actions
    if warnings:
        actions.append(
            f"Review {len(warnings)} data warning(s) above before making "
            "a sourcing decision."
        )

    # Final score actions
    if score >= 75 and confidence == "high":
        actions.append(
            "Overall: Strong candidate. Order a test batch of 10-20 units "
            "and validate with a small ad spend ($50-100) before scaling."
        )
    elif score < 35:
        actions.append(
            "Overall: Not recommended at this time. "
            "Search for a variation of this product with stronger demand."
        )

    return actions


def generate_final_report(
    product_name: str,
    country: str,
    markets: dict,
    final_analysis: dict,
    ads_count: int = 0,
) -> dict:
    """
    Builds the complete final report document.

    This is the document stored in final_reports_collection
    and returned by GET /report/{product_name}.

    FIX: Original returned {"demand_score": 0, "status": "pending_analysis"}.
    This now returns a complete, explainable, actionable report.

    Parameters:
        product_name:   The searched keyword
        country:        Target market country
        markets:        Dict with aliexpress and amazon analysis from market_analyzer
        final_analysis: Weighted score dict from _build_final_score in scrape_tasks
        ads_count:      Number of Facebook ads found (paid demand signal)
    """
    logger.info("Generating final report for '%s'", product_name)

    warnings         = _build_warnings(markets)
    market_comparison = _build_market_comparison(markets)
    action_items     = _build_action_items(final_analysis, warnings)

    breakdown = final_analysis.get("breakdown", {})

    report = {
        # Identity
        "product":   product_name,
        "country":   country,
        "generated_at": datetime.now(timezone.utc).isoformat(),

        # Raw market data
        "markets": markets,

        # Market comparison (the profit signal)
        "market_comparison": market_comparison,

        # Paid demand signal
        "paid_demand": {
            "facebook_ads_found": ads_count,
            "interpretation": (
                "Strong paid demand — competitors are spending on ads"
                if ads_count >= 5 else
                "Moderate paid demand" if ads_count >= 2 else
                "Low paid demand — may be untapped or low margin"
            )
        },

        # Final scoring
        "final_analysis": {
            "score":          final_analysis.get("score", 0),
            "recommendation": final_analysis.get("recommendation", "Insufficient data"),
            "confidence":     final_analysis.get("confidence", "low"),
            "breakdown": {
                "demand_score":       breakdown.get("demand_score", 0),
                "demand_label":       _interpret_score(breakdown.get("demand_score", 0), "Demand"),
                "profit_score":       breakdown.get("profit_score", 0),
                "profit_label":       _interpret_score(breakdown.get("profit_score", 0), "Profit"),
                "competition_score":  breakdown.get("competition_score", 0),
                "competition_label":  _interpret_score(breakdown.get("competition_score", 0), "Competition"),
                "data_quality_score": breakdown.get("data_quality_score", 0),
                "data_quality_label": _interpret_score(breakdown.get("data_quality_score", 0), "Data quality"),
            },
            "weights_used": final_analysis.get("weights_used", {}),
        },

        # Warnings about data reliability
        "warnings":     warnings,
        "warning_count": len(warnings),

        # Actionable next steps
        "action_items": action_items,
    }

    logger.info(
        "Report generated: score=%.1f, confidence=%s, warnings=%d",
        final_analysis.get("score", 0),
        final_analysis.get("confidence", "low"),
        len(warnings)
    )

    return report