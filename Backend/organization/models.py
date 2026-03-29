from django.db import models

# Create your models here.
import uuid
import logging

from django.db import models
from django.core.validators import RegexValidator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------
class PhaseChoices(models.TextChoices):
    SIXTEEN_PLUS             = "16_plus",                  "16 Plus"
    ALL_THROUGH              = "all_through",               "All Through"
    MIDDLE_DEEMED_PRIMARY    = "middle_deemed_primary",     "Middle Deemed Primary"
    MIDDLE_DEEMED_SECONDARY  = "middle_deemed_secondary",   "Middle Deemed Secondary"
    NOT_APPLICABLE           = "not_applicable",            "Not Applicable"
    NURSERY                  = "nursery",                   "Nursery"
    PRIMARY                  = "primary",                   "Primary"
    SECONDARY                = "secondary",                 "Secondary"


class GenderChoices(models.TextChoices):
    BOYS           = "boys",           "Boys"
    GIRLS          = "girls",          "Girls"
    MIXED          = "mixed",          "Mixed"
    NOT_APPLICABLE = "not_applicable", "Not Applicable"


# ---------------------------------------------------------------------------
# Organization
# ---------------------------------------------------------------------------
class Organization(models.Model):
    """
    Represents a school or educational organization.
    Unique constraint: OrganizationName + LocalAuthority.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ── Identifiers ───────────────────────────────────────────────────────
    urn = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        db_index=True,
        help_text="Unique Reference Number from the client sheet.",
    )

    # ── Core Info ─────────────────────────────────────────────────────────
    name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Organization / School name.",
    )
    local_authority = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Local Authority the organization belongs to.",
    )
    phase = models.CharField(
        max_length=50,
        choices=PhaseChoices.choices,
        default=PhaseChoices.NOT_APPLICABLE,
        db_index=True,
    )
    gender = models.CharField(
        max_length=30,
        choices=GenderChoices.choices,
        default=GenderChoices.MIXED,
    )
    telephone = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    # ── Address ───────────────────────────────────────────────────────────
    street = models.CharField(max_length=255, null=True, blank=True)
    address_line_1 = models.CharField(max_length=255, null=True, blank=True)
    address_line_2 = models.CharField(max_length=255, null=True, blank=True)
    town = models.CharField(max_length=100, null=True, blank=True, db_index=True)
    county = models.CharField(max_length=100, null=True, blank=True)
    postcode = models.CharField(
        max_length=10,
        null=True,
        blank=True,
        db_index=True,
    )

    # ── Geo Coordinates (for radius filtering) ────────────────────────────
    # Populated via geocoding the postcode/address
    latitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Latitude for geo-distance filtering.",
    )
    longitude = models.DecimalField(
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True,
        help_text="Longitude for geo-distance filtering.",
    )

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ["name", "local_authority"]
        constraints = [
            models.UniqueConstraint(
                fields=["name", "local_authority"],
                name="unique_organization_per_local_authority",
            )
        ]
        indexes = [
            models.Index(fields=["name", "local_authority"]),
            models.Index(fields=["postcode"]),
            models.Index(fields=["town"]),
            models.Index(fields=["phase"]),
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self):
        return f"{self.name} — {self.local_authority}"

    def __repr__(self):
        return (
            f"<Organization name={self.name!r} "
            f"local_authority={self.local_authority!r}>"
        )


# ---------------------------------------------------------------------------
# OrganizationContact
# ---------------------------------------------------------------------------
class OrganizationContact(models.Model):
    """
    A contact person at an Organization.
    One organization can have multiple contacts.
    Email is unique across all contacts.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="contacts",
        help_text="The organization this contact belongs to.",
    )

    contact_person = models.CharField(
        max_length=255,
        help_text="Full name of the contact person.",
    )
    job_title = models.CharField(
        max_length=255,
        null=True,
        blank=True,
    )
    work_email = models.EmailField(
        unique=True,
        db_index=True,
        help_text="Unique work email for this contact.",
    )

    # ── Timestamps ────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Organization Contact"
        verbose_name_plural = "Organization Contacts"
        ordering = ["contact_person"]
        indexes = [
            models.Index(fields=["work_email"]),
            models.Index(fields=["organization"]),
        ]

    def __str__(self):
        return f"{self.contact_person} <{self.work_email}> @ {self.organization.name}"

    def __repr__(self):
        return (
            f"<OrganizationContact person={self.contact_person!r} "
            f"email={self.work_email!r}>"
        )