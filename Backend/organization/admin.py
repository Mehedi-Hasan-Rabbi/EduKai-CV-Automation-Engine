from django.contrib import admin
from organization.models import Organization, OrganizationContact


class OrganizationContactInline(admin.TabularInline):
    model = OrganizationContact
    extra = 0
    fields = ["contact_person", "job_title", "work_email"]
    ordering = ["contact_person"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = [
        "name", "local_authority", "phase", "gender",
        "town", "postcode", "telephone", "contact_count", "created_at",
    ]
    list_filter  = ["phase", "gender", "local_authority", "town"]
    search_fields = ["name", "local_authority", "postcode", "town", "urn"]
    ordering     = ["name", "local_authority"]
    inlines      = [OrganizationContactInline]

    fieldsets = [
        ("Core Info", {
            "fields": ["urn", "name", "local_authority", "phase", "gender", "telephone"]
        }),
        ("Address", {
            "fields": [
                "street", "address_line_1", "address_line_2",
                "town", "county", "postcode",
            ]
        }),
        ("Geo Coordinates", {
            "fields": ["latitude", "longitude"],
            "description": "Used for radius-based candidate filtering.",
        }),
    ]

    def contact_count(self, obj):
        return obj.contacts.count()
    contact_count.short_description = "Contacts"


@admin.register(OrganizationContact)
class OrganizationContactAdmin(admin.ModelAdmin):
    list_display  = ["contact_person", "job_title", "work_email", "organization", "created_at"]
    list_filter   = ["job_title"]
    search_fields = ["contact_person", "work_email", "organization__name"]
    ordering      = ["contact_person"]