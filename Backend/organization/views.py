import os
import tempfile
from rest_framework.parsers import MultiPartParser, FormParser

from django.shortcuts import render
from organization.tasks.geocode import geocode_organization_task
from django.db import models

# Create your views here.
import logging
from geopy.distance import geodesic

from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from account.permissions import IsSuperUser
from organization.models import Organization, OrganizationContact
from organization.serializers import (
    OrganizationListSerializer,
    OrganizationDetailSerializer,
    OrganizationCreateUpdateSerializer,
    OrganizationContactSerializer,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Organization Views
# =============================================================================
class OrganizationListCreateView(APIView):
    """
    GET  /api/organizations/         — list all organizations
    POST /api/organizations/         — create new organization
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    @extend_schema(
        responses={200: OrganizationListSerializer(many=True)},
        summary="List all organizations",
        tags=["Organizations"],
    )
    def get(self, request):
        from candidate.utils.pagination import StandardPagination

        qs = Organization.objects.prefetch_related("contacts").all()

        phase           = request.query_params.get("phase")
        local_authority = request.query_params.get("local_authority")
        town            = request.query_params.get("town")
        postcode        = request.query_params.get("postcode")

        if phase:
            qs = qs.filter(phase=phase)
        if local_authority:
            qs = qs.filter(local_authority__icontains=local_authority)
        if town:
            qs = qs.filter(town__icontains=town)
        if postcode:
            qs = qs.filter(postcode__icontains=postcode)

        # Geo radius filter
        lat       = request.query_params.get("lat")
        lng       = request.query_params.get("lng")
        radius_km = request.query_params.get("radius_km")

        if lat and lng and radius_km:
            try:
                from geopy.distance import geodesic
                center    = (float(lat), float(lng))
                radius_km = float(radius_km)
                qs        = qs.exclude(latitude=None).exclude(longitude=None)

                filtered_ids = []
                for org in qs:
                    org_point = (float(org.latitude), float(org.longitude))
                    if geodesic(center, org_point).km <= radius_km:
                        filtered_ids.append(org.id)
                qs = qs.filter(id__in=filtered_ids)

            except (ValueError, TypeError) as exc:
                return Response(
                    {"detail": f"Invalid geo parameters: {exc}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        paginator  = StandardPagination()
        page       = paginator.paginate_queryset(qs, request)
        serializer = OrganizationListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        request=OrganizationCreateUpdateSerializer,
        responses={201: OrganizationDetailSerializer},
        summary="Create a new organization",
        tags=["Organizations"],
    )
    def post(self, request):
        serializer = OrganizationCreateUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        organization = serializer.save()

        # ✅ Auto geocode if lat/lng not provided
        if not organization.latitude or not organization.longitude:
            from organization.tasks import geocode_organization_task
            geocode_organization_task.apply_async(
                args=[str(organization.id)],
                queue="default",
            )
            logger.info(
                f"[org] Geocoding queued for new organization '{organization.name}'."
            )

        return Response(
            OrganizationDetailSerializer(organization).data,
            status=status.HTTP_201_CREATED,
        )


class OrganizationDetailView(APIView):
    """
    GET   /api/organizations/<id>/   — retrieve
    PATCH /api/organizations/<id>/   — partial update
    DELETE /api/organizations/<id>/  — delete
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def _get_object(self, org_id):
        try:
            return Organization.objects.prefetch_related("contacts").get(id=org_id)
        except Organization.DoesNotExist:
            return None

    @extend_schema(
        responses={200: OrganizationDetailSerializer},
        summary="Get organization details",
        tags=["Organizations"],
    )
    def get(self, request, org_id):
        org = self._get_object(org_id)
        if not org:
            return Response(
                {"detail": "Organization not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OrganizationDetailSerializer(org).data)

    @extend_schema(
        request=OrganizationCreateUpdateSerializer,
        responses={200: OrganizationDetailSerializer},
        summary="Partially update an organization",
        tags=["Organizations"],
    )
    def patch(self, request, org_id):
            org = self._get_object(org_id)
            if not org:
                return Response(
                    {"detail": "Organization not found."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            serializer = OrganizationCreateUpdateSerializer(
                org, data=request.data, partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()

            # ✅ Re-geocode if postcode/address changed and lat/lng now missing
            changed_fields = set(serializer.validated_data.keys())
            address_fields = {"postcode", "town", "county", "street"}

            if address_fields & changed_fields:
                # Clear old coordinates so geocoder runs fresh
                org.latitude  = None
                org.longitude = None
                org.save(update_fields=["latitude", "longitude"])

                from organization.tasks import geocode_organization_task
                geocode_organization_task.apply_async(
                    args=[str(org.id)],
                    queue="default",
                )
                logger.info(
                    f"[org] Address changed for '{org.name}' — "
                    f"re-geocoding queued."
                )

            return Response(OrganizationDetailSerializer(org).data)

    @extend_schema(
        responses={200: OpenApiResponse(description="Deleted successfully")},
        summary="Delete an organization and all its contacts",
        tags=["Organizations"],
    )
    def delete(self, request, org_id):
        org = self._get_object(org_id)
        if not org:
            return Response(
                {"detail": "Organization not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        name = str(org)
        org.delete()
        logger.info(f"[org] Organization '{name}' deleted.")
        return Response(
            {"message": f"Organization '{name}' deleted."},
            status=status.HTTP_200_OK,
        )


# =============================================================================
# Contact Views
# =============================================================================
class AllContactsListView(APIView):
    """
    GET /api/organizations/contacts/
    Returns all contacts across all organizations.
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    @extend_schema(
        responses={200: OrganizationContactSerializer(many=True)},
        summary="List all contacts across all organizations",
        tags=["Organization Contacts"],
    )
    def get(self, request):
        from candidate.utils.pagination import StandardPagination

        qs = OrganizationContact.objects.select_related("organization").all()

        job_title = request.query_params.get("job_title")
        search    = request.query_params.get("search")

        if job_title:
            qs = qs.filter(job_title__icontains=job_title)
        if search:
            qs = qs.filter(
                models.Q(contact_person__icontains=search) |
                models.Q(work_email__icontains=search)     |
                models.Q(organization__name__icontains=search)
            )

        paginator  = StandardPagination()
        page       = paginator.paginate_queryset(qs, request)
        serializer = OrganizationContactSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class ContactListCreateView(APIView):
    """
    GET  /api/organizations/<org_id>/contacts/   — list contacts
    POST /api/organizations/<org_id>/contacts/   — add contact
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def _get_org(self, org_id):
        try:
            return Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            return None

    @extend_schema(
        responses={200: OrganizationContactSerializer(many=True)},
        summary="List contacts for an organization",
        tags=["Organization Contacts"],
    )
    def get(self, request, org_id):
        org = self._get_org(org_id)
        if not org:
            return Response(
                {"detail": "Organization not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        contacts = org.contacts.all()
        return Response(OrganizationContactSerializer(contacts, many=True).data)

    @extend_schema(
        request=OrganizationContactSerializer,
        responses={201: OrganizationContactSerializer},
        summary="Add a contact to an organization",
        tags=["Organization Contacts"],
    )
    def post(self, request, org_id):
        org = self._get_org(org_id)
        if not org:
            return Response(
                {"detail": "Organization not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        data = {**request.data, "organization": str(org.id)}
        serializer = OrganizationContactSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        contact = serializer.save()
        logger.info(f"[org] Contact '{contact.work_email}' added to '{org}'.")
        return Response(
            OrganizationContactSerializer(contact).data,
            status=status.HTTP_201_CREATED,
        )


class ContactDetailView(APIView):
    """
    GET    /api/organizations/contacts/<contact_id>/  — retrieve
    PATCH  /api/organizations/contacts/<contact_id>/  — update
    DELETE /api/organizations/contacts/<contact_id>/  — delete
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    def _get_contact(self, contact_id):
        try:
            return OrganizationContact.objects.select_related("organization").get(
                id=contact_id
            )
        except OrganizationContact.DoesNotExist:
            return None

    @extend_schema(
        responses={200: OrganizationContactSerializer},
        summary="Get contact details",
        tags=["Organization Contacts"],
    )
    def get(self, request, contact_id):
        contact = self._get_contact(contact_id)
        if not contact:
            return Response(
                {"detail": "Contact not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(OrganizationContactSerializer(contact).data)

    @extend_schema(
        request=OrganizationContactSerializer,
        responses={200: OrganizationContactSerializer},
        summary="Update a contact",
        tags=["Organization Contacts"],
    )
    def patch(self, request, contact_id):
        contact = self._get_contact(contact_id)
        if not contact:
            return Response(
                {"detail": "Contact not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = OrganizationContactSerializer(
            contact, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(OrganizationContactSerializer(contact).data)

    @extend_schema(
        responses={200: OpenApiResponse(description="Contact deleted")},
        summary="Delete a contact",
        tags=["Organization Contacts"],
    )
    def delete(self, request, contact_id):
        contact = self._get_contact(contact_id)
        if not contact:
            return Response(
                {"detail": "Contact not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        email = contact.work_email
        contact.delete()
        logger.info(f"[org] Contact '{email}' deleted.")
        return Response(
            {"message": f"Contact '{email}' deleted."},
            status=status.HTTP_200_OK,
        )


#=============================================================================
# Excel file upload for organizatin and contacts  Views
#=============================================================================
class ImportOrganizationsView(APIView):
    """
    POST /api/organizations/import/
    Upload an Excel file to bulk import organizations.
    Runs as a background Celery task.
    Returns task_id to poll for results.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, IsSuperUser]

    @extend_schema(
        request={"multipart/form-data": {"type": "object", "properties": {
            "file": {"type": "string", "format": "binary"}
        }}},
        responses={202: OpenApiResponse(description="Import started")},
        summary="Import organizations from Excel file",
        tags=["Organizations"],
    )
    def post(self, request):
        file = request.FILES.get("file")

        if not file:
            return Response(
                {"detail": "No file provided. Send file as multipart/form-data."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not file.name.endswith(".xlsx"):
            return Response(
                {"detail": "Only .xlsx files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Save to shared volume so celery_default can access it ─────────
        import_dir = "/tmp/imports"
        os.makedirs(import_dir, exist_ok=True)

        suffix = f"_org_import_{file.name}"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, dir=import_dir
        ) as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        from organization.tasks.import_excel import import_organizations_task
        task = import_organizations_task.apply_async(
            args=[tmp_path],
            queue="default",
        )

        logger.info(
            f"[import_org] Organization import queued. "
            f"File: '{file.name}', Task: {task.id}, Path: {tmp_path}"
        )

        return Response(
            {
                "message": "Organization import started.",
                "task_id": task.id,
                "note":    "Poll /api/organizations/import/status/<task_id>/ for results.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ImportContactsView(APIView):
    """
    POST /api/organizations/import/contacts/
    Upload an Excel file to bulk import contacts.
    Organizations must be imported first.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated, IsSuperUser]

    @extend_schema(
        request={"multipart/form-data": {"type": "object", "properties": {
            "file": {"type": "string", "format": "binary"}
        }}},
        responses={202: OpenApiResponse(description="Import started")},
        summary="Import contacts from Excel file",
        tags=["Organization Contacts"],
    )
    def post(self, request):
        file = request.FILES.get("file")

        if not file:
            return Response(
                {"detail": "No file provided. Send file as multipart/form-data."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not file.name.endswith(".xlsx"):
            return Response(
                {"detail": "Only .xlsx files are supported."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Save to shared volume so celery_default can access it ─────────
        import_dir = "/tmp/imports"
        os.makedirs(import_dir, exist_ok=True)

        suffix = f"_contact_import_{file.name}"
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=suffix, dir=import_dir
        ) as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            tmp_path = tmp.name

        from organization.tasks.import_excel import import_contacts_task
        task = import_contacts_task.apply_async(
            args=[tmp_path],
            queue="default",
        )

        logger.info(
            f"[import_contact] Contact import queued. "
            f"File: '{file.name}', Task: {task.id}, Path: {tmp_path}"
        )

        return Response(
            {
                "message": "Contact import started.",
                "task_id": task.id,
                "note":    "Poll /api/organizations/import/status/<task_id>/ for results.",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class ImportStatusView(APIView):
    """
    GET /api/organizations/import/status/<task_id>/
    Poll for import task results.
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    @extend_schema(
        responses={200: OpenApiResponse(description="Task status and summary")},
        summary="Get import task status and summary",
        tags=["Organizations"],
    )
    def get(self, request, task_id):
        from celery.result import AsyncResult
        result = AsyncResult(task_id)

        if result.state == "PENDING":
            return Response({
                "status":  "pending",
                "message": "Import is still in progress.",
            })

        if result.state in ("FAILURE", "REVOKED"):
            return Response({
                "status": "failed",
                "error":  str(result.result),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        if result.state == "SUCCESS":
            return Response({
                "status":  "completed",
                "summary": result.result,
            })

        # RETRY, STARTED, or anything else — still processing
        return Response({
            "status":  "processing",
            "message": f"Import is in progress (state: {result.state}).",
        })