# Import all tasks here so Celery's autodiscover_tasks() can find them.
# autodiscover_tasks() looks for a 'tasks' module in each app.
# Since our tasks live in a sub-package, we explicitly import them here.

from candidate.tasks.process_cv import process_cv_task
from candidate.tasks.poll_ai_result import poll_ai_result_task
from candidate.tasks.generate_pdf import generate_enhanced_cv_pdf_task
from candidate.tasks.cleanup import cleanup_minio_files_task
from candidate.tasks.sync_batch import sync_batch_counts
from candidate.tasks.send_email import send_availability_email_task
from candidate.tasks.rewrite_cv import poll_rewrite_result_task
from candidate.tasks.geocode import geocode_candidate_task
from candidate.tasks.send_to_contacts import send_to_contacts_task

__all__ = [
    "process_cv_task",
    "poll_ai_result_task",
    "generate_enhanced_cv_pdf_task",
    "cleanup_minio_files_task",
    "sync_batch_counts",
    "send_availability_email_task",
    "poll_rewrite_result_task",
    "geocode_candidate_task",
    "send_to_contacts_task",
]