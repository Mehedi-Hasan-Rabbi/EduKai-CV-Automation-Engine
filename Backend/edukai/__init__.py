# This ensures Celery app is loaded when Django starts
from edukai.celery import app as celery_app

__all__ = ("celery_app",)