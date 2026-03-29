import uuid

from django.db import models
from django.utils import timezone
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


# Helper function
def user_profile_pic_path(instance, filename):
    """Generates a unique upload path per user: profile_pics/<user_uuid>/<filename>"""
    ext = filename.split(".")[-1]
    return f"profile_pics/{instance.id}/{uuid.uuid4().hex}.{ext}"


# Database models
class GenderChoices(models.TextChoices):
    MALE = "male", "Male"
    FEMALE = "female", "Female"
    OTHER = "other", "Other"
    PREFER_NOT_TO_SAY = "prefer_not_to_say", "Prefer not to say"


class UserRole(models.TextChoices):
    """
    Basic role system:
    - SUPERUSER: Full system control
    - USER: Normal authenticated user
    """

    SUPERUSER = "superuser", "Superuser"
    NORMALUSER = "normaluser", "Normaluser"


class UserManager(BaseUserManager):
    """
    Custom manager for the User model where email is the unique identifier
    for authentication instead of username.
    """

    def create_user(self, email, password, **extra_fields):
        """Create and save a regular user with the given email and password."""
        if not email:
            raise ValueError("The Email field must be set.")

        email = self.normalize_email(email)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault("role", "normaluser")

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", "superuser")

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model for CV Automation System.

    Authentication: Email + Password (no username).
    Roles: Scalable via UserRole choices — add new roles without schema changes.
    JWT: Compatible with djangorestframework-simplejwt out of the box.
    """

    # -------------------------------------------------------------------------
    # Primary Key
    # -------------------------------------------------------------------------
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Unique identifier for the user (UUID4).",
    )

    # -------------------------------------------------------------------------
    # Personal Information
    # -------------------------------------------------------------------------
    first_name = models.CharField(
        max_length=100,
    )
    last_name = models.CharField(
        max_length=100,
    )
    gender = models.CharField(
        max_length=20,
        choices=GenderChoices.choices,
        null=True,
        blank=True,
    )
    country = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="User's country of residence.",
    )

    # -------------------------------------------------------------------------
    # Authentication Fields
    # -------------------------------------------------------------------------
    email = models.EmailField(
        unique=True,
        db_index=True,
        help_text="Used as the login identifier.",
    )

    # -------------------------------------------------------------------------
    # Profile
    # -------------------------------------------------------------------------
    profile_pic = models.ImageField(
        upload_to=user_profile_pic_path,
        null=True,
        blank=True,
    )

    # -------------------------------------------------------------------------
    # Role & Permissions
    # -------------------------------------------------------------------------
    role = models.CharField(
        max_length=30,
        choices=UserRole.choices,
        default=UserRole.NORMALUSER,
        db_index=True,
        help_text="Defines user access level. Add new roles in choices.py.",
    )

    # -------------------------------------------------------------------------
    # Django Auth Flags
    # -------------------------------------------------------------------------
    is_active = models.BooleanField(
        default=True,
        help_text=(
            "Designates whether this user should be treated as active. "
            "Deactivate instead of deleting accounts."
        ),
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can log into the admin site.",
    )

    # -------------------------------------------------------------------------
    # Timestamps
    # -------------------------------------------------------------------------
    date_joined = models.DateTimeField(
        default=timezone.now,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # -------------------------------------------------------------------------
    # Manager & Auth Config
    # -------------------------------------------------------------------------
    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-date_joined"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role"]),
        ]

    # -------------------------------------------------------------------------
    # Properties & Methods
    # -------------------------------------------------------------------------
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_super_user(self) -> bool:
        return self.role == UserRole.SUPERUSER

    def __str__(self) -> str:
        return f"{self.full_name} <{self.email}>"

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email} role={self.role}>"


# ---------------------------------------------------------------------------
# Activity Log — tracks system events and notifications
# ---------------------------------------------------------------------------
class ActivityLog(models.Model):

    class EventType(models.TextChoices):
        # Candidate events
        BATCH_UPLOADED          = "batch_uploaded",           "Batch Uploaded"
        BATCH_COMPLETED         = "batch_completed",          "Batch Completed"
        BATCH_FAILED            = "batch_failed",             "Batch Failed"
        CV_PROCESSED            = "cv_processed",             "CV Processed"
        CV_FAILED               = "cv_failed",                "CV Failed"
        EMAILS_SENT             = "emails_sent",              "Emails Sent"
        CV_REWRITE_COMPLETED    = "cv_rewrite_completed",     "CV Rewrite Completed"
        CV_REWRITE_FAILED       = "cv_rewrite_failed",        "CV Rewrite Failed"
        # Organization events
        ORG_IMPORT_COMPLETED    = "org_import_completed",     "Org Import Completed"
        CONTACT_IMPORT_COMPLETED = "contact_import_completed", "Contact Import Completed"

    class Severity(models.TextChoices):
        INFO    = "info",    "Info"      # normal activity
        SUCCESS = "success", "Success"   # something completed well
        WARNING = "warning", "Warning"   # needs attention
        ERROR   = "error",   "Error"     # something failed ← show as notification

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    event_type = models.CharField(
        max_length=50,
        choices=EventType.choices,
        db_index=True,
    )
    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.INFO,
        db_index=True,
    )
    title   = models.CharField(max_length=255)
    message = models.TextField(blank=True, default="")

    # Optional references — so frontend can link to the relevant item
    candidate_id    = models.UUIDField(null=True, blank=True, db_index=True)
    batch_id        = models.UUIDField(null=True, blank=True, db_index=True)
    organization_id = models.UUIDField(null=True, blank=True, db_index=True)

    # Notification tracking
    is_read = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Activity Log"
        verbose_name_plural = "Activity Logs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event_type", "created_at"]),
            models.Index(fields=["severity", "is_read"]),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.title} — {self.created_at:%Y-%m-%d %H:%M}"