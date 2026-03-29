import logging
logger = logging.getLogger(__name__)


def log_activity(
    event_type: str,
    title: str,
    message: str = "",
    severity: str = "info",
    candidate_id=None,
    batch_id=None,
    organization_id=None,
):
    """
    Creates an ActivityLog entry.
    Enforces 1000 entry limit — deletes oldest entries when exceeded.
    Call this from any task or view.
    """
    try:
        from account.models import ActivityLog

        ActivityLog.objects.create(
            event_type      = event_type,
            severity        = severity,
            title           = title,
            message         = message,
            candidate_id    = candidate_id,
            batch_id        = batch_id,
            organization_id = organization_id,
        )

        # ── Enforce 1000 entry limit ──────────────────────────────────────
        MAX_ENTRIES = 1000
        total = ActivityLog.objects.count()
        if total > MAX_ENTRIES:
            excess = total - MAX_ENTRIES
            oldest_ids = ActivityLog.objects.order_by(
                "created_at"
            ).values_list("id", flat=True)[:excess]
            ActivityLog.objects.filter(id__in=list(oldest_ids)).delete()
            logger.debug(f"[activity] Pruned {excess} old activity log entries.")

    except Exception as exc:
        # Never let logging crash the main task
        logger.error(f"[activity] Failed to log activity: {exc}")