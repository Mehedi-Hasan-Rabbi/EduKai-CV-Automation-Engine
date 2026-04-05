from rest_framework import serializers
from organization.models import Organization, OrganizationContact


# =============================================================================
# Contact Serializers
# =============================================================================
class OrganizationContactSerializer(serializers.ModelSerializer):
    """Full CRUD serializer for contacts."""

    class Meta:
        model = OrganizationContact
        fields = [
            "id",
            "organization",
            "contact_person",
            "job_title",
            "work_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_work_email(self, value):
        """Ensure email is unique excluding current instance on update."""
        qs = OrganizationContact.objects.filter(work_email__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "A contact with this email already exists."
            )
        return value.lower()


class OrganizationContactInlineSerializer(serializers.ModelSerializer):
    """Lightweight contact serializer — used inside OrganizationDetailSerializer."""

    class Meta:
        model = OrganizationContact
        fields = [
            "id",
            "contact_person",
            "job_title",
            "work_email",
        ]
        read_only_fields = fields


# =============================================================================
# Organization Serializers
# =============================================================================
class OrganizationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views."""

    contact_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization
        fields = [
            "id",
            "urn",
            "name",
            "local_authority",
            "phase",
            "gender",
            "town",
            "postcode",
            "telephone",
            "contact_count",
            "created_at",
        ]

    def get_contact_count(self, obj) -> int:
        return obj.contacts.count()


class OrganizationDetailSerializer(serializers.ModelSerializer):
    """Full serializer with nested contacts."""

    contacts = OrganizationContactInlineSerializer(many=True, read_only=True)

    class Meta:
        model = Organization
        fields = [
            "id",
            "urn",
            "name",
            "local_authority",
            "phase",
            "gender",
            "telephone",
            "street",
            "address_line_1",
            "address_line_2",
            "town",
            "county",
            "postcode",
            "latitude",
            "longitude",
            "contacts",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, data):
        """Enforce unique_together: name + local_authority."""
        name = data.get("name", getattr(self.instance, "name", None))
        local_authority = data.get(
            "local_authority",
            getattr(self.instance, "local_authority", None)
        )
        qs = Organization.objects.filter(
            name__iexact=name,
            local_authority__iexact=local_authority,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Organization '{name}' already exists in '{local_authority}'."
            )
        return data


class OrganizationCreateUpdateSerializer(serializers.ModelSerializer):
    """Used for POST and PATCH — no nested contacts."""

    class Meta:
        model = Organization
        fields = [
            "id",
            "urn",
            "name",
            "local_authority",
            "phase",
            "gender",
            "telephone",
            "street",
            "address_line_1",
            "address_line_2",
            "town",
            "county",
            "postcode",
            "latitude",
            "longitude",
        ]
        read_only_fields = ["id"]
        extra_kwargs = {
            "name":           {"required": True},
            "local_authority": {"required": True},
        }

    def validate(self, data):
        name = data.get("name", getattr(self.instance, "name", None))
        local_authority = data.get(
            "local_authority",
            getattr(self.instance, "local_authority", None)
        )
        qs = Organization.objects.filter(
            name__iexact=name,
            local_authority__iexact=local_authority,
        )
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                f"Organization '{name}' already exists in '{local_authority}'."
            )
        return data


class OrganizationContactWithOrgSerializer(serializers.ModelSerializer):
    """Contact serializer that embeds basic organization info."""
    organization = OrganizationListSerializer(read_only=True)

    class Meta:
        model = OrganizationContact
        fields = [
            "id",
            "organization",
            "contact_person",
            "job_title",
            "work_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields