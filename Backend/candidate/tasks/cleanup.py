import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    name="candidate.tasks.cleanup_minio_files",
)
def cleanup_minio_files_task(self, file_keys: list[str]):
    """
    Deletes a list of MinIO object keys asynchronously.
    Called after batch/candidate deletion so the API responds instantly.

    Args:
        file_keys: List of MinIO object key strings
                   e.g. ["candidates/original/<uuid>/file.pdf", ...]
    """
    from django.conf import settings
    from candidate.utils.minio_utils import _get_s3_client

    if not file_keys:
        return

    # Filter out empty strings
    keys = [k for k in file_keys if k and k.strip()]
    if not keys:
        return

    if not getattr(settings, "USE_S3", False):
        # Local filesystem — delete files directly
        import os
        from django.conf import settings as s
        media_root = getattr(s, "MEDIA_ROOT", "")
        for key in keys:
            try:
                full_path = os.path.join(str(media_root), key)
                if os.path.exists(full_path):
                    os.remove(full_path)
                    logger.info(f"[cleanup] ✅ Deleted local file: {full_path}")
            except Exception as exc:
                logger.error(f"[cleanup] ❌ Failed to delete local file {key}: {exc}")
        return

    # MinIO — batch delete using S3 delete_objects API (much faster than one-by-one)
    try:
        s3 = _get_s3_client()
        bucket = settings.AWS_STORAGE_BUCKET_NAME

        # S3 delete_objects accepts up to 1000 keys per request
        # Split into chunks of 1000
        chunk_size = 1000
        chunks = [keys[i:i + chunk_size] for i in range(0, len(keys), chunk_size)]

        total_deleted = 0
        for chunk in chunks:
            objects = [{"Key": key} for key in chunk]
            response = s3.delete_objects(
                Bucket=bucket,
                Delete={
                    "Objects": objects,
                    "Quiet":   True,    # Don't return list of deleted objects
                },
            )

            # Log any errors from MinIO
            errors = response.get("Errors", [])
            for err in errors:
                logger.error(
                    f"[cleanup] ❌ MinIO failed to delete {err.get('Key')}: "
                    f"{err.get('Code')} — {err.get('Message')}"
                )

            total_deleted += len(chunk) - len(errors)

        logger.info(
            f"[cleanup] ✅ Deleted {total_deleted}/{len(keys)} files from MinIO in "
            f"{len(chunks)} batch request(s)."
        )

    except Exception as exc:
        logger.error(f"[cleanup] ❌ MinIO batch delete failed: {exc}")
        raise self.retry(exc=exc)