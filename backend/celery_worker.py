from celery import Celery

celery_app = Celery(
    "worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
    include=["backend.tasks.scrape_tasks"]
)

celery_app.conf.task_routes = {
    "tasks.scrape_product": {"queue": "scraping"}
}