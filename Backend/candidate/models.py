import uuid
import logging

from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.core.validators import MinValueValidator, MaxValueValidator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Upload path helpers
# ---------------------------------------------------------------------------
def candidate_cv_upload_path(instance, filename):
    """Original CV: candidates/original/<uuid>/<filename>"""
    ext = filename.split(".")[-1]
    return f"candidates/original/{instance.id}/{uuid.uuid4().hex}.{ext}"


def candidate_enhanced_cv_upload_path(instance, filename):
    """AI Enhanced CV PDF: candidates/enhanced/<uuid>/<filename>"""
    ext = filename.split(".")[-1]
    return f"candidates/enhanced/{instance.id}/{uuid.uuid4().hex}.{ext}"


def candidate_profile_photo_upload_path(instance, filename):
    """Profile photo: candidates/photos/<uuid>/<filename>"""
    ext = filename.split(".")[-1]
    return f"candidates/photos/{instance.id}/{uuid.uuid4().hex}.{ext}"


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------
class SourceChoices(models.TextChoices):
    LOCAL_UPLOAD = "local_upload", "Local Upload"
    CRM = "crm", "CRM"
    PREVIOUS_DB = "previous_db", "Previous DB"


class AvailabilityStatus(models.TextChoices):
    AVAILABLE = "available", "Available"
    NOT_AVAILABLE = "not_available", "Not Available"
    OPEN_TO_OFFERS = "open_to_offers", "Open to Offers"


class QualityStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    PASSED = "passed", "Passed"
    FAILED = "failed", "Failed"
    MANUAL = "manual", "Manual Review"


class AIProcessingStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not Started"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


# ---------------------------------------------------------------------------
# Upload Batch — tracks a group of CVs submitted together
# ---------------------------------------------------------------------------
class CandidateUploadBatch(models.Model):
    """
    Represents a single bulk upload session.
    One batch = one form submission (e.g. 500 CVs with the same additional_info).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # The additional_info sent to the AI for every CV in this batch
    additional_info = models.JSONField(
        default=dict,
        help_text=(
            'Additional info sent to AI for all CVs in this batch. '
            'Example: {"experience": 2.0, "skills": ["math"], "job_role": ["math teacher"]}'
        ),
    )

    total_count = models.PositiveIntegerField(default=0, help_text="Total CVs in this batch.")
    processed_count = models.PositiveIntegerField(default=0, help_text="CVs processed successfully.")
    failed_count = models.PositiveIntegerField(default=0, help_text="CVs that failed processing.")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Upload Batch"
        verbose_name_plural = "Upload Batches"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Batch {self.id} — {self.processed_count}/{self.total_count} processed"


# ---------------------------------------------------------------------------
# Candidate
# ---------------------------------------------------------------------------
class Candidate(models.Model):
    """
    Central model for all candidate-related data in EduKai.
    """

    # -------------------------------------------------------------------------
    # Primary Key
    # -------------------------------------------------------------------------
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # -------------------------------------------------------------------------
    # Batch Reference
    # -------------------------------------------------------------------------
    batch = models.ForeignKey(
        CandidateUploadBatch,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="candidates",
        help_text="The upload batch this candidate belongs to.",
    )

    # -------------------------------------------------------------------------
    # Personal Information (populated from AI personal_info)
    # -------------------------------------------------------------------------
    name = models.CharField(max_length=255, db_index=True, blank=True, default="")
    email = models.EmailField(
        db_index=True,
        null=True,
        blank=True,
        help_text="Extracted from CV by AI. Null if not found.",
    )
    whatsapp_number = models.CharField(max_length=30, null=True, blank=True)
    location = models.CharField(max_length=255, null=True, blank=True)
    # ── Geo Coordinates (populated on demand when filtering) ──────────────
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Populated on demand when geo filtering is used.",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Populated on demand when geo filtering is used.",
    )

    # -------------------------------------------------------------------------
    # Professional Information (populated from AI personal_info)
    # -------------------------------------------------------------------------
    years_of_experience = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(60)],
    )
    skills = models.JSONField(
        default=list,
        blank=True,
        help_text='Example: ["Math Teacher", "Physics", "SEND Support"]',
    )

    # -------------------------------------------------------------------------
    # Recruitment Status
    # -------------------------------------------------------------------------
    source = models.CharField(
        max_length=30,
        choices=SourceChoices.choices,
        default=SourceChoices.LOCAL_UPLOAD,
        db_index=True,
    )
    availability_status = models.CharField(
        max_length=20,
        choices=AvailabilityStatus.choices,
        default=AvailabilityStatus.NOT_AVAILABLE,
        db_index=True,
    )
    quality_status = models.CharField(
        max_length=20,
        choices=QualityStatus.choices,
        default=QualityStatus.PENDING,
        db_index=True,
    )

    # -------------------------------------------------------------------------
    # Profile Photo (extracted by AI — may be null if CV has no photo)
    # -------------------------------------------------------------------------
    profile_photo = models.ImageField(
        upload_to=candidate_profile_photo_upload_path,
        null=True,
        blank=True,
        help_text="Profile photo stored in MinIO. Extracted by AI or uploaded manually.",
    )

    # -------------------------------------------------------------------------
    # Job Titles (extracted by AI from data_extracted.role)
    # -------------------------------------------------------------------------
    job_titles = models.JSONField(
        default=list,
        blank=True,
        help_text='Example: ["Math Teacher", "Science Teacher", "English Teacher"]',
    )


    # -------------------------------------------------------------------------
    # CV Files
    # -------------------------------------------------------------------------
    original_cv_file = models.FileField(
        upload_to=candidate_cv_upload_path,
        null=True,
        blank=True,
        help_text="Candidate's original uploaded CV (PDF).",
    )

    # -------------------------------------------------------------------------
    # AI Processing
    # -------------------------------------------------------------------------
    ai_processing_status = models.CharField(
        max_length=20,
        choices=AIProcessingStatus.choices,
        default=AIProcessingStatus.NOT_STARTED,
        db_index=True,
    )
    ai_task_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Task ID returned by the AI service. Used for polling.",
    )
    rewrite_task_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        db_index=True,
        help_text="Task ID for AI rewrite. Separate from the original ai_task_id.",
    )
    rewrite_status = models.CharField(
        max_length=20,
        choices=[
            ("idle",       "Idle"),
            ("processing", "Processing"),
            ("completed",  "Completed"),
            ("failed",     "Failed"),
        ],
        default="idle",
        help_text="Tracks the status of the AI rewrite request.",
    )
    ai_enhanced_cv_content = models.JSONField(
        null=True,
        blank=True,
        help_text="Full structured JSON output from AI.",
    )
    ai_enhanced_cv_file = models.FileField(
        upload_to=candidate_enhanced_cv_upload_path,
        null=True,
        blank=True,
        help_text="WeasyPrint-generated enhanced CV PDF.",
    )
    ai_failure_reason = models.TextField(
        null=True,
        blank=True,
        help_text="Stores error message if AI processing failed.",
    )
    rewrite_failure_reason = models.TextField(
        null=True,
        blank=True,
        help_text="Stores error message if AI rewrite failed.",
    )
    ai_retry_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of times AI processing was retried.",
    )

    # -------------------------------------------------------------------------
    # Email Communication (populated from AI output)
    # -------------------------------------------------------------------------
    email_subject = models.CharField(max_length=500, null=True, blank=True)
    email_body = models.TextField(null=True, blank=True)

# -------------------------------------------------------------------------
    # Contact Outreach Tracking
    # -------------------------------------------------------------------------
    last_contacted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When candidate info was last sent to organization contacts.",
    )
    contacts_emailed_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of contacts emailed for this candidate so far.",
    )

    # -------------------------------------------------------------------------
    # Internal Notes
    # -------------------------------------------------------------------------
    notes = models.TextField(null=True, blank=True)

    # -------------------------------------------------------------------------
    # Timestamps
    # -------------------------------------------------------------------------
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Candidate"
        verbose_name_plural = "Candidates"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source"]),
            models.Index(fields=["availability_status"]),
            models.Index(fields=["quality_status"]),
            models.Index(fields=["ai_processing_status"]),
            models.Index(fields=["ai_task_id"]),
            models.Index(fields=["rewrite_task_id"]),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    def __repr__(self):
        return (
            f"<Candidate id={self.id} name={self.name!r} "
            f"quality={self.quality_status} ai={self.ai_processing_status}>"
        )


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------
@receiver(post_delete, sender=Candidate)
def log_candidate_deletion(sender, instance, **kwargs):
    logger.info(
        f"[signal] Candidate {instance.id} ({instance.name!r}) "
        f"deleted from DB."
    )
