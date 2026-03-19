---

# 🌐 API DESIGN (DETAILED)

The backend exposes RESTful APIs using FastAPI.

All APIs are designed to trigger analysis tasks and retrieve reports.

---

# 1️⃣ START PRODUCT ANALYSIS

## Endpoint:
POST /analyze

## Description:
Triggers a full product analysis pipeline using Celery.

## Request Body (JSON):
```json
{
  "product_name": "electric cleaning brush",
  "country": "Saudi Arabia"
}
```
## Flow:
- API receives request
- Sends task to Celery
- Returns immediately (async processing)

## Response:
```json
{
  "status": "processing",
  "message": "Analysis started successfully"
}
```
---

# 2️⃣ GET FINAL REPORT

## Endpoint:
**GET** /report/{product_name}

## Description:
Returns the final combined report from all markets.

## Example Request:

GET /report/electric cleaning brush

## Response:
```json
{
  "product": "electric cleaning brush",
  "country": "Saudi Arabia",

  "markets": {
    "aliexpress": {
      "products_found": 19,
      "avg_price": 577,
      "avg_orders": 575,
      "avg_rating": 3.9,
      "competition": "medium"
    },
    "amazon": {
      "products_found": 20,
      "avg_price": 1588,
      "avg_orders": 37,
      "avg_rating": 4.37,
      "competition": "medium"
    }
  },

  "final_analysis": {
    "score": 82.7,
    "recommendation": "🔥 Winning Product"
  }
}
```
---

# 3️⃣ GET PLATFORM REPORTS

## Endpoint:
**GET** /reports/{product_name}

## Description:
Returns individual reports for each platform.

## Response:
```json
[
  {
    "platform": "aliexpress",
    "analysis": {...}
  },
  {
    "platform": "amazon",
    "analysis": {...}
  }
]
```
---

# 4️⃣ GET RAW PRODUCTS

## Endpoint:
**GET** /products/{product_name}

## Description:
Returns raw scraped products.

## Response:
```json
[
  {
    "title": "...",
    "price": "...",
    "orders": "...",
    "rating": "...",
    "source": "aliexpress"
  }
]
```
---

# 5️⃣ GET FACEBOOK ADS

## Endpoint:
GET /ads/{product_name}

## Description:
Returns collected Facebook ads.

## Response:
```json
[
  {
    "title": "...",
    "page": "...",
    "link": "...",
    "source": "facebook"
  }
]
```
---

# 🔁 FULL API FLOW
```
User → POST /analyze  
        ↓  
Celery Task starts  
        ↓  
Scrapers run  
        ↓  
Data saved  
        ↓  
User calls GET /report  
        ↓  
Receives final decision
```
---

# ⚙️ API BEST PRACTICES

- Use async endpoints (FastAPI)
- Use background tasks (Celery)
- Never block request thread
- Always validate input
- Return consistent JSON format

---

# 🔐 FUTURE API IMPROVEMENTS

- Authentication (JWT)
- Rate limiting
- API keys (for SaaS)
- Pagination for large data
- Caching (Redis)

---

# 🧪 EXAMPLE CURL REQUESTS

## Start analysis:

curl -X POST http://localhost:8000/analyze \
-H "Content-Type: application/json" \
-d '{"product_name":"electric cleaning brush","country":"Saudi Arabia"}'

---

## Get report:

curl http://localhost:8000/report/electric%20cleaning%20brush

---

# 🧠 SYSTEM DESIGN NOTE

This API is designed for scalability:

- Stateless API layer
- Background processing via Celery
- MongoDB for flexible schema
- Easily extendable with new data sources

---
