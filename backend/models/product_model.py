"""
product_model.py — Fixed & Hardened
=====================================
Changes from original:
1. Original had only one model (ProductInput) with zero validation
2. Response models added for every API endpoint — no more raw dict returns
3. ProductInput validators hardened — empty, injected, and oversized inputs rejected
4. ScoreBreakdown model added — score components are typed, not free-form dicts
5. DataQuality model added — tracks reliability of scraped data
6. MarketAnalysis model added — typed output from market_analyzer
7. FinalReport model added — the full response shape for GET /report
8. TaskStatus model added — typed response for GET /status
9. PaginatedResponse generic model added — reusable for /products and /ads
10. All models use model_config with populate_by_name and from_attributes
    for clean MongoDB document hydration
"""

import re
from datetime import datetime
from typing import Generic, Optional, TypeVar
from pydantic import BaseModel, Field, field_validator, model_config

T = TypeVar("T")


# ------------------------------------------------------------------
# Shared config — applied to all models
# ------------------------------------------------------------------

SHARED_CONFIG = model_config(
    populate_by_name=True,   # allow field aliases and real names both
    from_attributes=True,    # allow building from ORM/dict objects
)


# ------------------------------------------------------------------
# INPUT MODELS
# ------------------------------------------------------------------

class ProductInput(BaseModel):
    """
    Input model for POST /analyze.

    FIX: Original accepted any string with no validation at all.
    Empty strings, injections, and 10,000-char inputs all passed through.
    """
    model_config = SHARED_CONFIG

    product_name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Product keyword to analyze (e.g. 'electric cleaning brush')",
        examples=["electric cleaning brush", "wireless earbuds"],
    )

    country: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Target market country (e.g. 'Saudi Arabia')",
        examples=["Saudi Arabia", "Egypt", "UAE"],
    )

    @field_validator("product_name")
    @classmethod
    def validate_product_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("product_name cannot be empty or whitespace")
        # Only allow safe characters — blocks NoSQL injection patterns
        if re.search(r"[^\w\s\-]", v):
            raise ValueError(
                "product_name contains invalid characters. "
                "Only letters, numbers, spaces, and hyphens are allowed."
            )
        return v

    @field_validator("country")
    @classmethod
    def validate_country(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("country cannot be empty or whitespace")
        if re.search(r"[^\w\s\-]", v):
            raise ValueError("country contains invalid characters")
        return v


# ------------------------------------------------------------------
# TASK / STATUS MODELS
# ------------------------------------------------------------------

class AnalyzeResponse(BaseModel):
    """
    Response model for POST /analyze.

    FIX: Original returned an untyped dict.
    Now the response shape is explicit and documented in the API schema.
    """
    model_config = SHARED_CONFIG

    status:  str = Field(..., examples=["queued"])
    task_id: str = Field(..., description="Celery task ID — use with GET /status")
    message: str = Field(..., examples=["Analysis started for 'electric cleaning brush'"])


class TaskStatus(BaseModel):
    """
    Response model for GET /status/{product_name}.

    FIX: This endpoint did not exist in the original.
    Users had no way to check job progress after submitting.
    """
    model_config = SHARED_CONFIG

    product_name: str
    country:      str
    status:       str = Field(
        ...,
        description="One of: queued, running, completed, failed"
    )
    score:          Optional[float] = Field(None, description="Final score — populated when completed")
    recommendation: Optional[str]  = Field(None, description="Populated when completed")
    error:          Optional[str]  = Field(None, description="Populated when failed")


# ------------------------------------------------------------------
# DATA QUALITY MODEL
# ------------------------------------------------------------------

class DataQuality(BaseModel):
    """
    Tracks how reliable the scraped data is for a given platform.

    FIX: Original had no data quality concept.
    A score built on fabricated ratings looked identical to one
    built on real data.
    """
    model_config = SHARED_CONFIG

    prices_parsed:      int = Field(0, description="Number of products with successfully parsed prices")
    orders_parsed:      int = Field(0, description="Number of products with successfully parsed order counts")
    ratings_real:       int = Field(0, description="Number of products with real scraped ratings")
    ratings_defaulted:  int = Field(0, description="Number of products where rating defaulted to 3.5")
    unknown_currencies: int = Field(0, description="Number of products with unrecognized currency — excluded from price avg")


# ------------------------------------------------------------------
# MARKET ANALYSIS MODEL
# ------------------------------------------------------------------

class MarketAnalysis(BaseModel):
    """
    Typed output from market_analyzer.analyze_market().

    FIX: Original returned raw untyped dicts everywhere.
    This enforces the shape coming out of the analyzer.

    Note: avg_price_usd replaces avg_price from original —
    all prices are now normalized to USD.
    """
    model_config = SHARED_CONFIG

    platform:      str
    products_found: int
    avg_price_usd: float = Field(0.0, description="Average price in USD across all products")
    avg_orders:    float = Field(0.0, description="Average orders (AliExpress) or reviews (Amazon)")
    avg_rating:    float = Field(0.0, description="Average rating 0.0–5.0")
    competition:   str   = Field("unknown", description="low / medium / high / unknown")
    data_quality:  DataQuality = Field(default_factory=DataQuality)


# ------------------------------------------------------------------
# SCORING MODELS
# ------------------------------------------------------------------

class ScoreBreakdown(BaseModel):
    """
    Typed breakdown of the weighted final score.

    FIX: Original score was a single number with no explanation.
    Now every component is typed and labeled.
    """
    model_config = SHARED_CONFIG

    demand_score:        float = Field(..., ge=0, le=100)
    demand_label:        str
    profit_score:        float = Field(..., ge=0, le=100)
    profit_label:        str
    competition_score:   float = Field(..., ge=0, le=100)
    competition_label:   str
    data_quality_score:  float = Field(..., ge=0, le=100)
    data_quality_label:  str


class FinalAnalysis(BaseModel):
    """
    The final scoring result returned inside the full report.
    """
    model_config = SHARED_CONFIG

    score:          float = Field(..., ge=0, le=100, description="Weighted final score 0–100")
    recommendation: str   = Field(..., description="Human-readable verdict")
    confidence:     str   = Field(..., description="high / medium / low")
    breakdown:      ScoreBreakdown
    weights_used:   dict  = Field(default_factory=dict)


# ------------------------------------------------------------------
# MARKET COMPARISON MODEL
# ------------------------------------------------------------------

class DemandComparison(BaseModel):
    model_config = SHARED_CONFIG

    aliexpress_avg_orders:   float
    amazon_avg_reviews:      float
    stronger_demand_signal:  str


class CompetitionComparison(BaseModel):
    model_config = SHARED_CONFIG

    aliexpress: str
    amazon:     str


class MarketComparison(BaseModel):
    """
    Side-by-side comparison of AliExpress and Amazon.
    The price gap here is the core profit signal.

    FIX: Original never compared markets at all.
    """
    model_config = SHARED_CONFIG

    price_gap_usd:            float = Field(..., description="Amazon avg price minus AliExpress avg price in USD")
    estimated_margin_pct:     float = Field(..., description="Estimated gross margin as percentage")
    margin_interpretation:    str
    demand_comparison:        DemandComparison
    competition_comparison:   CompetitionComparison


# ------------------------------------------------------------------
# PAID DEMAND MODEL
# ------------------------------------------------------------------

class PaidDemand(BaseModel):
    """
    Facebook Ads signal — how many ads are running for this product.
    More ads = competitors are spending money = validated demand.
    """
    model_config = SHARED_CONFIG

    facebook_ads_found: int
    interpretation:     str


# ------------------------------------------------------------------
# FULL REPORT MODEL
# ------------------------------------------------------------------

class FinalReport(BaseModel):
    """
    Complete response model for GET /report/{product_name}.

    FIX: Original returned a raw dict with no enforced shape.
    This is the full typed response the frontend will consume.
    """
    model_config = SHARED_CONFIG

    product:      str
    country:      str
    generated_at: datetime

    markets: dict[str, MarketAnalysis] = Field(
        ...,
        description="Per-platform analysis keyed by platform name"
    )

    market_comparison: MarketComparison
    paid_demand:       PaidDemand
    final_analysis:    FinalAnalysis

    warnings:      list[str] = Field(default_factory=list, description="Data reliability warnings")
    warning_count: int       = Field(0)
    action_items:  list[str] = Field(default_factory=list, description="Actionable next steps")


# ------------------------------------------------------------------
# RAW PRODUCT MODEL
# ------------------------------------------------------------------

class RawProduct(BaseModel):
    """
    Shape of a single scraped product returned by GET /products/{product_name}.

    FIX: Original returned raw MongoDB documents with no schema.
    _id field (non-serializable BSON) would crash the endpoint.
    """
    model_config = SHARED_CONFIG

    title:  str
    price:  Optional[str] = None
    orders: Optional[str] = None
    rating: Optional[str] = None
    link:   Optional[str] = None
    source: str = Field(..., description="aliexpress or amazon")


# ------------------------------------------------------------------
# RAW AD MODEL
# ------------------------------------------------------------------

class RawAd(BaseModel):
    """
    Shape of a single Facebook ad returned by GET /ads/{product_name}.
    """
    model_config = SHARED_CONFIG

    title:   Optional[str] = None
    page:    Optional[str] = None
    link:    Optional[str] = None
    source:  str = Field(default="facebook")


# ------------------------------------------------------------------
# PAGINATED RESPONSE (generic — reused for /products and /ads)
# ------------------------------------------------------------------

class PaginatedResponse(BaseModel, Generic[T]):
    """
    Generic paginated wrapper used by GET /products and GET /ads.

    FIX: Original had no pagination — all results returned in one dump.
    Usage:
        PaginatedResponse[RawProduct]
        PaginatedResponse[RawAd]
    """
    model_config = SHARED_CONFIG

    product:   str
    page:      int
    page_size: int
    total:     int
    results:   list[T]