# Dropship-product-analyzer

- uvicorn backend.main:app --reload
- celery -A backend.celery_worker worker --loglevel=info --pool=solo
