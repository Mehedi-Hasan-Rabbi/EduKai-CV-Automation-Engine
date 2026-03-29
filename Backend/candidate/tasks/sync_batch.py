import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from django.db import models

logger = logging.getLogger(__name__)


@shared_task(name="candidate.tasks.sync_batch_counts")
def sync_batch_counts():
    """
    Recalculates batch progress from actual candidate statuses every 5 minutes.
    Fixes batches stuck at 0% due to silent worker crashes or lost tasks.
    """
    from candidate.models import CandidateUploadBatch, Candidate, AIProcessingStatus

    cutoff = timezone.now() - timedelta(hours=6)

    stale_batches = CandidateUploadBatch.objects.filter(
        created_at__gte=cutoff,
    ).exclude(
        processed_count=models.F("total_count")
    )

    fixed = 0
    for batch in stale_batches:
        completed = Candidate.objects.filter(
            batch=batch,
            ai_processing_status=AIProcessingStatus.COMPLETED,
        ).count()

        failed = Candidate.objects.filter(
            batch=batch,
            ai_processing_status=AIProcessingStatus.FAILED,
        ).count()

        batch.processed_count = completed
        batch.failed_count = failed
        batch.save(update_fields=["processed_count", "failed_count"])
        fixed += 1

    logger.info(f"[sync_batch] Synced {fixed} incomplete batch(es).")