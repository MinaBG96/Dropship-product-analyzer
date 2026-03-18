def generate_basic_report(product_name):

    report = {
        "product": product_name,
        "demand_score": 0,
        "competition_score": 0,
        "profit_score": 0,
        "status": "pending_analysis"
    }

    return report