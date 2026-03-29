from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from account.models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "full_name", "role", "is_active", "date_joined",)
    list_filter = ("role", "is_active", "is_staff", "gender")
    search_fields = ("email", "first_name", "last_name")
    ordering = ("-date_joined",)
    readonly_fields = ("id", "date_joined", "updated_at")

    fieldsets = (
        ("Login Credentials", {
            "fields": ("email", "password"),
        }),
        ("Personal Info", {
            "fields": ("first_name", "last_name", "gender", "country", "profile_pic"),
        }),
        ("Role & Permissions", {
            "fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
        }),
        ("Timestamps", {
            "fields": ("id", "date_joined", "updated_at"),
        }),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "password1", "password2", "role"),
        }),
    )