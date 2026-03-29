import os
import json

from django.conf import settings
from rest_framework import serializers

from candidate.models import Candidate, CandidateUploadBatch

# =============================================================================
# Bulk Upload Serializer — for validating the initial batch upload request
# =============================================================================
class BulkCVUploadSerializer(serializers.Serializer):

    files = serializers.ListField(
        child=serializers.FileField(
            max_length=100,
            allow_empty_file=False,
        ),
        min_length=1,
        max_length=10000,
    )

    experience = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        default=None,
        help_text="e.g. 2.0 — minimum years of experience",
    )

    skills = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
    )

    job_role = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
    )

    def validate_experience(self, value):
        if value in (None, "", "null", "none"):
            return None
        try:
            result = float(value)
        except (ValueError, TypeError):
            raise serializers.ValidationError("Enter a valid number. e.g. 2.0, 1.5, 0.5")
        if result < 0 or result > 60:
            raise serializers.ValidationError("Experience must be between 0 and 60.")
        return result

    def validate_skills(self, value):
        return self._parse_list_field(value, "skills")

    def validate_job_role(self, value):
        return self._parse_list_field(value, "job_role")

    def validate_files(self, files):
        allowed_extensions = {"pdf", "doc", "docx"}
        max_size_mb = 10
        for f in files:
            ext = f.name.rsplit(".", 1)[-1].lower()
            if ext not in allowed_extensions:
                raise serializers.ValidationError(
                    f"File '{f.name}' has unsupported type '.{ext}'. "
                    f"Allowed: {', '.join(allowed_extensions)}"
                )
            if f.size > max_size_mb * 1024 * 1024:
                raise serializers.ValidationError(
                    f"File '{f.name}' exceeds {max_size_mb}MB limit."
                )
        return files

    def _parse_list_field(self, value, field_name: str) -> list:
        if not value:
            return []
        if isinstance(value, list):
            if len(value) == 1 and isinstance(value[0], str):
                stripped = value[0].strip()
                if stripped.startswith("["):
                    try:
                        parsed = json.loads(stripped)
                        if isinstance(parsed, list):
                            return [str(i).strip() for i in parsed if str(i).strip()]
                    except json.JSONDecodeError:
                        raise serializers.ValidationError(
                            f"Invalid JSON array for '{field_name}'. "
                            f'Use: ["val1", "val2"] or send as repeated keys.'
                        )
            return [str(i).strip() for i in value if str(i).strip()]
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                try:
                    parsed = json.loads(stripped)
                    if isinstance(parsed, list):
                        return [str(i).strip() for i in parsed if str(i).strip()]
                except json.JSONDecodeError:
                    raise serializers.ValidationError(
                        f"Invalid JSON array for '{field_name}'."
                    )
            return [stripped] if stripped else []
        return []

    def get_additional_info(self) -> dict:
        data = self.validated_data
        info = {}
        if data.get("experience") is not None:
            info["experience"] = data["experience"]
        if data.get("skills"):
            info["skills"] = data["skills"]
        if data.get("job_role"):
            info["job_role"] = data["job_role"]
        return info


# =============================================================================
# Mixin — reusable pre-signed URL fields for any Candidate serializer
# =============================================================================
class CandidateFileMixin:
    """
    Adds pre-signed (or local) URLs for:
      - original_cv_file  → original_cv_url
      - ai_enhanced_cv_file → enhanced_cv_url
    """

    def get_original_cv_url(self, obj) -> str | None:
        from candidate.utils.minio_utils import resolve_file_url
        return resolve_file_url(obj.original_cv_file)

    def get_enhanced_cv_url(self, obj) -> str | None:
        from candidate.utils.minio_utils import resolve_file_url
        return resolve_file_url(obj.ai_enhanced_cv_file)
    
    def get_profile_photo_url(self, obj) -> str | None:
        from candidate.utils.minio_utils import resolve_file_url
        return resolve_file_url(obj.profile_photo)


# =============================================================================
# List Serializer — lightweight, includes CV URLs
# =============================================================================
class CandidateListSerializer(CandidateFileMixin, serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    # ✅ These replace the raw FileField values with pre-signed URLs
    # original_cv_url  = serializers.SerializerMethodField()
    # enhanced_cv_url  = serializers.SerializerMethodField()
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Candidate
        fields = [
            "id",
            "name",
            "email",
            "whatsapp_number",
            "location",
            "years_of_experience",
            "skills",
            "job_titles",
            "profile_photo_url",
            "source",
            "availability_status",
            "quality_status",
            "ai_processing_status",
            # "original_cv_url",        # ✅ pre-signed original CV URL
            # "enhanced_cv_url",        # ✅ pre-signed enhanced CV URL
            "created_at",
        ]


# =============================================================================
# Detail Serializer — full data, includes CV URLs
# =============================================================================
class CandidateDetailSerializer(CandidateFileMixin, serializers.ModelSerializer):
    """Full serializer for detail view."""

    original_cv_url   = serializers.SerializerMethodField()
    enhanced_cv_url   = serializers.SerializerMethodField()
    profile_photo_url = serializers.SerializerMethodField()
    cv_status_message = serializers.SerializerMethodField()  # 👈 new

    class Meta:
        model = Candidate
        fields = [
            "id",
            "batch",
            "name",
            "email",
            "whatsapp_number",
            "location",
            "years_of_experience",
            "skills",
            "job_titles",
            "profile_photo_url",
            "source",
            "availability_status",
            "quality_status",
            "ai_processing_status",
            "ai_task_id",
            "ai_enhanced_cv_content",
            "ai_failure_reason",
            "ai_retry_count",
            "email_subject",
            "email_body",
            "notes",
            "original_cv_url",
            "enhanced_cv_url",        # null when CV is regenerating
            "cv_status_message",      # 👈 new — message when regenerating, null otherwise
            "created_at",
            "updated_at",
        ]

    def _is_regenerating(self) -> bool:
        """Check if CV regeneration was triggered in this request."""
        request = self.context.get("request")
        return bool(request and getattr(request, "_cv_regenerating", False))

    def get_cv_status_message(self, obj) -> str | None:
        if self._is_regenerating():
            return "CV is being regenerated, please allow a few moments."
        return None

    def get_enhanced_cv_url(self, obj) -> str | None:
        # ✅ Hide stale PDF URL while regeneration is in progress
        if self._is_regenerating():
            return None
        from candidate.utils.minio_utils import resolve_file_url
        return resolve_file_url(obj.ai_enhanced_cv_file)


# =============================================================================
# Batch Serializer
# =============================================================================
class UploadBatchSerializer(serializers.ModelSerializer):
    """Serializer for batch status tracking."""

    progress_percentage = serializers.SerializerMethodField()
    status              = serializers.SerializerMethodField()
    active_count        = serializers.SerializerMethodField()
    deleted_count       = serializers.SerializerMethodField()

    class Meta:
        model = CandidateUploadBatch
        fields = [
            "id",
            "additional_info",
            "total_count",          # original upload count — never changes (audit trail)
            "processed_count",      # AI completed successfully
            "failed_count",         # AI failed
            "active_count",         # currently in DB (decreases on manual delete)
            "deleted_count",        # manually deleted since upload
            "progress_percentage",  # 0-100 integer
            "status",               # in_progress / completed / partial / failed / empty
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_progress_percentage(self, obj) -> int:
        """0-100 integer. Based on AI processed count vs total uploaded."""
        if not obj.total_count:
            return 0
        return int((obj.processed_count / obj.total_count) * 100)

    def get_status(self, obj) -> str:
        """
        in_progress → AI still working
        completed   → all processed, none failed
        partial     → some processed, some failed
        failed      → all failed
        empty       → no CVs in batch
        """
        if obj.total_count == 0:
            return "empty"

        finished = obj.processed_count + obj.failed_count
        if finished < obj.total_count:
            return "in_progress"

        if obj.failed_count == 0:
            return "completed"
        elif obj.processed_count == 0:
            return "failed"
        else:
            return "partial"

    def get_active_count(self, obj) -> int:
        """Candidates currently in DB for this batch."""
        return obj.candidates.count()

    def get_deleted_count(self, obj) -> int:
        """Candidates manually deleted from this batch since upload."""
        return max(0, obj.total_count - obj.candidates.count())


class CandidateUpdateSerializer(serializers.ModelSerializer):
    """
    PATCH /api/candidates/<id>/update/

    Editable fields:
        profile_photo, years_of_experience, skills, job_titles,
        availability_status, quality_status, email_subject, email_body,
        source, name, email, whatsapp_number, location, notes

    After save, if job_titles changed → regenerate PDF automatically.
    """

    class Meta:
        model = Candidate
        fields = [
            # Personal info
            "name",
            "email",
            "whatsapp_number",
            "location",
            # Professional info
            "years_of_experience",
            "skills",
            "job_titles",
            # Profile photo
            "profile_photo",
            # Recruitment status
            "source",
            "availability_status",
            "quality_status",
            # Email content
            "email_subject",
            "email_body",
            # Internal notes
            "notes",
        ]
        extra_kwargs = {
            "profile_photo":        {"required": False},
            "years_of_experience":  {"required": False},
            "skills":               {"required": False},
            "job_titles":           {"required": False},
            "source":               {"required": False},
            "availability_status":  {"required": False},
            "quality_status":       {"required": False},
            "email_subject":        {"required": False},
            "email_body":           {"required": False},
            "notes":                {"required": False},
            "name":                 {"required": False},
            "email":                {"required": False},
            "whatsapp_number":      {"required": False},
            "location":             {"required": False},
        }

    def validate_years_of_experience(self, value):
        if value is not None and (value < 0 or value > 60):
            raise serializers.ValidationError(
                "Years of experience must be between 0 and 60."
            )
        return value

    def validate_skills(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Skills must be a list.")
        return [str(s).strip() for s in value if str(s).strip()]

    def validate_job_titles(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("Job titles must be a list.")
        return [str(s).strip() for s in value if str(s).strip()]

    def validate_email(self, value):
        if value:
            qs = Candidate.objects.filter(email__iexact=value)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError(
                    "A candidate with this email already exists."
                )
        return value

    def validate_availability_status(self, value):
        valid = [c[0] for c in Candidate.availability_status.field.choices]
        if value not in valid:
            raise serializers.ValidationError(
                f"Invalid availability status. Choose from: {valid}"
            )
        return value

    def validate_quality_status(self, value):
        valid = [c[0] for c in Candidate.quality_status.field.choices]
        if value not in valid:
            raise serializers.ValidationError(
                f"Invalid quality status. Choose from: {valid}"
            )
        return value