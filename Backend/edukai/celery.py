import os
from celery import Celery
from celery.signals import task_prerun, task_postrun

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "edukai.settings")

app = Celery("edukai")
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

# ✅ Close DB connections after each task to prevent stale connection errors
@task_postrun.connect
def close_db_connections(**kwargs):
    from django.db import connection
    connection.close()