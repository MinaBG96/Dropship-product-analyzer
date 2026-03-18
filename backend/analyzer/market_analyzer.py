import re
from statistics import mean


def clean_price(price):
    try:
        return float(price.replace("EGP", "").replace("$", "").replace(",", "").strip())
    except:
        return 0


def clean_orders(orders):
    try:
        return int(orders.split()[0].replace("+", ""))
    except:
        return 0


def clean_rating(rating):
    try:
        return float(rating)
    except:
        return 0


def analyze_market(products):

    if not products:
        return {
            "products_found": 0,
            "avg_price": 0,
            "avg_orders": 0,
            "avg_rating": 0,
            "competition": "unknown"
        }

    prices = []
    orders = []
    ratings = []

    for p in products:
        prices.append(clean_price(p.get("price", "")))
        orders.append(clean_orders(p.get("orders", "")))
        ratings.append(clean_rating(p.get("rating", "")))

    avg_price = sum(prices) / len(prices) if prices else 0
    avg_orders = sum(orders) / len(orders) if orders else 0
    avg_rating = sum(ratings) / len(ratings) if ratings else 0

    return {
        "products_found": len(products),
        "avg_price": round(avg_price, 2),
        "avg_orders": round(avg_orders, 2),
        "avg_rating": round(avg_rating, 2),
        "competition": "high" if len(products) > 20 else "low"
    }