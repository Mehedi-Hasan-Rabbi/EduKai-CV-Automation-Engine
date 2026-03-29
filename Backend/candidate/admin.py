from django.contrib import admin
from django.utils.html import format_html
import json

from candidate.models import Candidate, CandidateUploadBatch


# =============================================================================
# Upload Batch Admin
# =============================================================================
@admin.register(CandidateUploadBatch)
class CandidateUploadBatchAdmin(admin.ModelAdmin):

    list_display = (
        "id",
        "total_count",
        "processed_count",
        "failed_count",
        "progress_percentage",
        "created_at",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "progress_percentage",
    )

    search_fields = ("id",)
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    @admin.display(description="Progress")
    def progress_percentage(self, obj):
        if obj.total_count == 0:
            return "0%"
        percent = int((obj.processed_count / obj.total_count) * 100)
        return f"{percent}%"


# =============================================================================
# Candidate Admin
# =============================================================================
@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):

    # -------------------------------------------------------------------------
    # List View
    # -------------------------------------------------------------------------
    list_display = (
        "name",
        "email",
        "batch",
        "years_of_experience",
        "source",
        "availability_badge",
        "quality_badge",
        "ai_status_badge",
        "ai_retry_count",
        "created_at",
    )

    list_filter = (
        "batch",
        "source",
        "availability_status",
        "quality_status",
        "ai_processing_status",
        "created_at",
    )

    search_fields = (
        "name",
        "email",
        "whatsapp_number",
        "location",
        "ai_task_id",
    )

    ordering = ("-created_at",)
    list_per_page = 25
    date_hierarchy = "created_at"

    # -------------------------------------------------------------------------
    # Readonly Fields
    # -------------------------------------------------------------------------
    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
        "skills_preview",
        "job_titles_preview",
        "ai_enhanced_cv_content_preview",
        "profile_photo_preview",
    )

    # -------------------------------------------------------------------------
    # Detail View
    # -------------------------------------------------------------------------
    fieldsets = (

        ("Batch Information", {
            "fields": ("batch",),
        }),

        ("Personal Information", {
            "fields": (
                "id",
                "name",
                "email",
                "whatsapp_number",
                "location",
                "profile_photo",
                "profile_photo_preview",
            ),
        }),

        ("Professional Information", {
            "fields": (
                "years_of_experience",
                "skills",
                "skills_preview",
                "job_titles",
                "job_titles_preview",
            ),
        }),

        ("Recruitment Status", {
            "fields": (
                "source",
                "availability_status",
                "quality_status",
            ),
        }),

        ("CV Files", {
            "fields": (
                "original_cv_file",
                "ai_enhanced_cv_file",
            ),
        }),

        ("AI Processing", {
            "fields": (
                "ai_processing_status",
                "ai_task_id",
                "ai_retry_count",
                "ai_failure_reason",
                "ai_enhanced_cv_content",
                "ai_enhanced_cv_content_preview",
            ),
        }),

        ("Email Communication", {
            "fields": (
                "email_subject",
                "email_body",
            ),
            "classes": ("collapse",),
        }),

        ("Internal Notes", {
            "fields": ("notes",),
            "classes": ("collapse",),
        }),

        ("Timestamps", {
            "fields": (
                "created_at",
                "updated_at",
            ),
        }),
    )

    # -------------------------------------------------------------------------
    # Colored Badges
    # -------------------------------------------------------------------------
    @admin.display(description="Availability")
    def availability_badge(self, obj):
        colors = {
            "available": "#28a745",
            "not_available": "#dc3545",
            "open_to_offers": "#fd7e14",
        }
        color = colors.get(obj.availability_status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color,
            obj.get_availability_status_display(),
        )

    @admin.display(description="Quality")
    def quality_badge(self, obj):
        colors = {
            "pending": "#6c757d",
            "passed": "#28a745",
            "failed": "#dc3545",
            "manual": "#ffc107",
        }
        color = colors.get(obj.quality_status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color,
            obj.get_quality_status_display(),
        )

    @admin.display(description="AI Status")
    def ai_status_badge(self, obj):
        colors = {
            "not_started": "#6c757d",
            "in_progress": "#007bff",
            "completed": "#28a745",
            "failed": "#dc3545",
        }
        color = colors.get(obj.ai_processing_status, "#6c757d")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:12px;font-size:11px;font-weight:600;">{}</span>',
            color,
            obj.get_ai_processing_status_display(),
        )

    # -------------------------------------------------------------------------
    # JSON Previews
    # -------------------------------------------------------------------------
    @admin.display(description="Skills Preview")
    def skills_preview(self, obj):
        if not obj.skills:
            return "—"
        formatted = json.dumps(obj.skills, indent=2)
        return format_html(
            '<pre style="background:#f8f9fa;padding:10px;border-radius:4px;'
            'font-size:12px;max-height:200px;overflow:auto;">{}</pre>',
            formatted,
        )

    @admin.display(description="Job Titles Preview")
    def job_titles_preview(self, obj):
        if not obj.job_titles:
            return "—"
        formatted = json.dumps(obj.job_titles, indent=2)
        return format_html(
            '<pre style="background:#f8f9fa;padding:10px;border-radius:4px;'
            'font-size:12px;max-height:200px;overflow:auto;">{}</pre>',
            formatted,
        )

    @admin.display(description="AI Enhanced CV Content Preview")
    def ai_enhanced_cv_content_preview(self, obj):
        if not obj.ai_enhanced_cv_content:
            return "—"
        formatted = json.dumps(obj.ai_enhanced_cv_content, indent=2)
        return format_html(
            '<pre style="background:#f8f9fa;padding:10px;border-radius:4px;'
            'font-size:12px;max-height:300px;overflow:auto;">{}</pre>',
            formatted,
        )

    # -------------------------------------------------------------------------
    # Profile Photo Preview
    # -------------------------------------------------------------------------
    @admin.display(description="Profile Photo")
    def profile_photo_preview(self, obj):
        if not obj.profile_photo:
            return "—"
        return format_html(
            '<img src="{}" style="height:120px;border-radius:6px;" />',
            obj.profile_photo.url
        )

    # -------------------------------------------------------------------------
    # Bulk Actions
    # -------------------------------------------------------------------------
    actions = [
        "mark_available",
        "mark_not_available",
        "mark_quality_passed",
        "mark_quality_failed",
        "reset_ai_status",
    ]

    @admin.action(description="Mark selected as Available")
    def mark_available(self, request, queryset):
        updated = queryset.update(availability_status="available")
        self.message_user(request, f"{updated} candidate(s) marked as Available.")

    @admin.action(description="Mark selected as Not Available")
    def mark_not_available(self, request, queryset):
        updated = queryset.update(availability_status="not_available")
        self.message_user(request, f"{updated} candidate(s) marked as Not Available.")

    @admin.action(description="Mark quality as Passed")
    def mark_quality_passed(self, request, queryset):
        updated = queryset.update(quality_status="passed")
        self.message_user(request, f"{updated} candidate(s) marked as Passed.")

    @admin.action(description="Mark quality as Failed")
    def mark_quality_failed(self, request, queryset):
        updated = queryset.update(quality_status="failed")
        self.message_user(request, f"{updated} candidate(s) marked as Failed.")

    @admin.action(description="Reset AI status to Not Started")
    def reset_ai_status(self, request, queryset):
        updated = queryset.update(
            ai_processing_status="not_started",
            ai_retry_count=0,
            ai_failure_reason=None,
        )
        self.message_user(request, f"{updated} candidate(s) AI status reset.")