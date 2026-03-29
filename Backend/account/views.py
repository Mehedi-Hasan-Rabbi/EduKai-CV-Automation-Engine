import email

from django.conf import settings
from django.contrib.auth import get_user_model

from drf_spectacular.utils import extend_schema, OpenApiResponse

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from account.permissions import IsSuperUser, IsNormalUser, IsSuperUserOrReadOnly

from account.serializers import (
    CookieTokenRefreshSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserProfileSerializer,
    ProfileUpdateSerializer,
    PasswordUpdateSerializer,
    ForgotPasswordSerializer,
    VerifyOTPSerializer,
    ResetPasswordSerializer,
)

from account.utils.cookies import set_auth_cookies, unset_auth_cookies

User = get_user_model()


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------
class RegisterView(APIView):
    """
    POST /api/auth/register/
    Register a new user. Returns user profile + sets auth cookies.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=RegisterSerializer,
        responses={
            201: UserProfileSerializer,
            400: OpenApiResponse(description="Validation error"),
        },
        summary="Register a new user",
        tags=["Auth"],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Generate tokens immediately after registration (auto-login)
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        response = Response(
            {
                "message": "Registration successful.",
                "user": UserProfileSerializer(user, context={"request": request}).data,
            },
            status=status.HTTP_201_CREATED,
        )
        set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
        return response


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
class LoginView(APIView):
    """
    POST /api/auth/login/
    Authenticate with email + password. Sets HttpOnly auth cookies.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: UserProfileSerializer,
            401: OpenApiResponse(description="Invalid credentials"),
        },
        summary="Login with email and password",
        tags=["Auth"],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        user = validated["user"]
        access_token = validated["access"]
        refresh_token = validated["refresh"]

        response = Response(
            {
                "message": "Login successful.",
                "user": UserProfileSerializer(user, context={"request": request}).data,
            },
            status=status.HTTP_200_OK,
        )
        set_auth_cookies(response, access_token=access_token, refresh_token=refresh_token)
        return response


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------
class TokenRefreshView(APIView):
    """
    POST /api/auth/token/refresh/
    Reads refresh token from HttpOnly cookie, returns a new access token cookie.
    No body required.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(description="Access token refreshed successfully"),
            401: OpenApiResponse(description="Invalid or expired refresh token"),
        },
        summary="Refresh access token using cookie",
        tags=["Auth"],
    )
    def post(self, request):
        serializer = CookieTokenRefreshSerializer(context={"request": request})

        try:
            data = serializer.validate({})
        except (InvalidToken, TokenError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)

        response = Response({"message": "Token refreshed successfully."}, status=status.HTTP_200_OK)

        is_secure = getattr(settings, "SESSION_COOKIE_SECURE", False)
        samesite  = getattr(settings, "SESSION_COOKIE_SAMESITE", "Lax")

        # Always set the new access token cookie
        response.set_cookie(
            key=settings.SIMPLE_JWT.get("AUTH_COOKIE_ACCESS", "access_token"),
            value=data["access"],
            max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
            httponly=True,
            secure=is_secure,
            samesite=samesite,
            path="/",
        )

        # If refresh token was rotated, set the new one too
        if "refresh" in data:
            response.set_cookie(
                key=settings.SIMPLE_JWT.get("REFRESH_COOKIE_NAME", "refresh_token"),
                value=data["refresh"],
                max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
                httponly=True,
                secure=is_secure,
                samesite=samesite,
                path=settings.SIMPLE_JWT.get("REFRESH_COOKIE_PATH", "/api/auth"),
            )

        return response


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------
class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Blacklists the refresh token and clears both auth cookies.
    Requires authentication.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=None,
        responses={
            200: OpenApiResponse(description="Logout successful"),
            400: OpenApiResponse(description="Invalid or missing refresh token"),
        },
        summary="Logout and invalidate tokens",
        tags=["Auth"],
    )
    def post(self, request):
        from django.conf import settings

        refresh_cookie_name = settings.SIMPLE_JWT.get("REFRESH_COOKIE_NAME", "refresh_token")
        refresh_token = request.COOKIES.get(refresh_cookie_name)

        if not refresh_token:
            return Response(
                {"detail": "Refresh token not found. You may already be logged out."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()  # Invalidate token in DB (requires token_blacklist app)
        except TokenError:
            # Token already invalid/expired — still clear cookies
            pass

        response = Response({"message": "Logout successful."}, status=status.HTTP_200_OK)
        unset_auth_cookies(response)
        return response


# ---------------------------------------------------------------------------
# Profile (Me)
# ---------------------------------------------------------------------------
class MeView(APIView):
    """
    GET /api/auth/me/
    Returns the currently authenticated user's profile.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: UserProfileSerializer},
        summary="Get current user profile",
        tags=["Auth"],
    )
    def get(self, request):
        serializer = UserProfileSerializer(request.user, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------
# Profile Update
# ---------------------------------------------------
class ProfileUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={200: UserProfileSerializer},
        summary="Update current user profile",
        tags=["Auth"],
    )
    def patch(self, request):
        serializer = ProfileUpdateSerializer(
            request.user,
            data=request.data,
            partial=True
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                {
                    "message": "Profile updated successfully.",
                    "data": UserProfileSerializer(request.user, context={"request": request}).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------
# Password Update
# ---------------------------------------------------
class PasswordUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=PasswordUpdateSerializer,
        responses={
            200: OpenApiResponse(description="Password updated successfully"),
            400: OpenApiResponse(description="Validation error"),
        },
        summary="Change current user's password",
        tags=["Auth"],
    )

    def post(self, request):
        serializer = PasswordUpdateSerializer(
            data=request.data,
            context={"request": request}
        )

        if serializer.is_valid():
            serializer.save()
            return Response(
                {"message": "Password updated successfully."},
                status=status.HTTP_200_OK,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Forgot Password
# ---------------------------------------------------------------------------
class ForgotPasswordView(APIView):
    """
    POST /api/auth/forgot-password/
    Sends an OTP to the provided email if an account exists.
    Always returns a generic success message (security best practice).
    """
    permission_classes = [AllowAny]

    @extend_schema(
        request=ForgotPasswordSerializer,
        responses={
            200: OpenApiResponse(description="OTP sent if account exists"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        summary="Request a password reset OTP",
        tags=["Auth - Password Reset"],
    )
    def post(self, request):
        from account.utils.password_reset import (
            can_request_otp, generate_numeric_otp,
            store_otp_for_email, send_otp_email,
        )

        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        allowed, reason, retry_after, remaining_reqs = can_request_otp(email)
        if not allowed:
            return Response(
                {"detail": reason, "retry_after": retry_after, "remaining_requests": remaining_reqs},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        otp = generate_numeric_otp()
        store_otp_for_email(email, otp)

        # Only send if the user exists — but don't reveal this to the caller
        if User.objects.filter(email__iexact=email).exists():
            try:
                send_otp_email(email, otp)
            except Exception:
                pass  # keep silent in production — don't reveal email existence

        cooldown = getattr(settings, "PASSWORD_RESET_RESEND_COOLDOWN", 60)
        return Response(
            {
                "detail": "If an account exists for that email, you will receive an OTP shortly.",
                "retry_after": retry_after or cooldown,
                "remaining_requests": remaining_reqs,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Verify OTP
# ---------------------------------------------------------------------------
class VerifyOTPView(APIView):
    """
    POST /api/auth/verify-otp/
    Verifies the OTP. On success, sets a short-lived verified flag in Redis.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        request=VerifyOTPSerializer,
        responses={
            200: OpenApiResponse(description="OTP verified successfully"),
            400: OpenApiResponse(description="Invalid or expired OTP"),
            403: OpenApiResponse(description="Too many failed attempts"),
        },
        summary="Verify password reset OTP",
        tags=["Auth - Password Reset"],
    )
    def post(self, request):
        from django.conf import settings as django_settings
        from account.utils.password_reset import (
            increment_verify_attempts, verify_otp,
            set_verified_for_email, clear_otp_for_email, clear_verified_for_email,
        )

        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        otp = serializer.validated_data["otp"]

        max_attempts = getattr(django_settings, "PASSWORD_RESET_MAX_VERIFY_ATTEMPTS", 5)
        attempts = increment_verify_attempts(email)

        if attempts > max_attempts:
            clear_otp_for_email(email)
            clear_verified_for_email(email)
            return Response(
                {"detail": "Too many incorrect attempts. Please request a new OTP."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not verify_otp(email, otp):
            remaining = max(0, max_attempts - attempts)
            return Response(
                {"detail": "Invalid or expired OTP.", "attempts_remaining": remaining},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # OTP is valid — mark verified and invalidate OTP (prevent reuse)
        set_verified_for_email(email)
        clear_otp_for_email(email)

        return Response(
            {"detail": "OTP verified. You may now reset your password."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Reset Password
# ---------------------------------------------------------------------------
class ResetPasswordView(APIView):
    """
    POST /api/auth/reset-password/
    Resets the password. Requires prior OTP verification.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        request=ResetPasswordSerializer,
        responses={
            200: OpenApiResponse(description="Password reset successfully"),
            400: OpenApiResponse(description="OTP not verified or validation error"),
        },
        summary="Reset password after OTP verification",
        tags=["Auth - Password Reset"],
    )
    def post(self, request):
        from account.utils.password_reset import (
            is_verified_for_email, clear_verified_for_email, clear_otp_for_email,
        )

        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]
        new_password = serializer.validated_data["new_password"]

        if not is_verified_for_email(email):
            return Response(
                {"detail": "OTP not verified or session expired. Please verify your OTP first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            # Clear verified flag and return generic message
            clear_verified_for_email(email)
            return Response(
                {"detail": "Password has been reset successfully."},
                status=status.HTTP_200_OK,
            )

        user.set_password(new_password)
        user.save()

        clear_verified_for_email(email)
        clear_otp_for_email(email)

        return Response(
            {"detail": "Password reset successfully. Please log in with your new password."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class DashboardView(APIView):
    """
    GET /api/auth/dashboard/
    Returns system-wide statistics for the superuser dashboard.
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    @extend_schema(
        responses={200: OpenApiResponse(description="Dashboard statistics")},
        summary="Get dashboard statistics",
        tags=["Dashboard"],
    )
    def get(self, request):
        from django.utils import timezone
        from datetime import timedelta
        from django.db.models import Count, Sum
        from candidate.models import Candidate, CandidateUploadBatch
        from organization.models import Organization, OrganizationContact

        now     = timezone.now()
        last_7  = now - timedelta(days=7)
        last_30 = now - timedelta(days=30)

        # ── Candidate stats ───────────────────────────────────────────────
        total_candidates = Candidate.objects.count()

        ai_status_counts = dict(
            Candidate.objects.values("ai_processing_status")
            .annotate(count=Count("id"))
            .values_list("ai_processing_status", "count")
        )
        quality_counts = dict(
            Candidate.objects.values("quality_status")
            .annotate(count=Count("id"))
            .values_list("quality_status", "count")
        )
        availability_counts = dict(
            Candidate.objects.values("availability_status")
            .annotate(count=Count("id"))
            .values_list("availability_status", "count")
        )
        source_counts = dict(
            Candidate.objects.values("source")
            .annotate(count=Count("id"))
            .values_list("source", "count")
        )

        new_last_7  = Candidate.objects.filter(created_at__gte=last_7).count()
        new_last_30 = Candidate.objects.filter(created_at__gte=last_30).count()

        emailed_candidates = Candidate.objects.filter(
            contacts_emailed_count__gt=0
        ).count()

        total_emails_sent = Candidate.objects.aggregate(
            total=Sum("contacts_emailed_count")
        )["total"] or 0

        # ── Batch stats ───────────────────────────────────────────────────
        total_batches      = CandidateUploadBatch.objects.count()
        total_uploaded     = CandidateUploadBatch.objects.aggregate(
            total=Sum("total_count")
        )["total"] or 0
        total_processed    = CandidateUploadBatch.objects.aggregate(
            total=Sum("processed_count")
        )["total"] or 0
        total_batch_failed = CandidateUploadBatch.objects.aggregate(
            total=Sum("failed_count")
        )["total"] or 0

        success_rate = (
            round((total_processed / total_uploaded) * 100, 1)
            if total_uploaded > 0 else 0
        )

        # ── Organization stats ────────────────────────────────────────────
        total_organizations = Organization.objects.count()
        total_contacts      = OrganizationContact.objects.count()

        phase_counts = dict(
            Organization.objects.values("phase")
            .annotate(count=Count("id"))
            .values_list("phase", "count")
        )

        orgs_geocoded = Organization.objects.exclude(
            latitude=None
        ).exclude(
            longitude=None
        ).count()

        # ── Recent batches (last 5) ───────────────────────────────────────
        recent_batches = []
        for batch in CandidateUploadBatch.objects.order_by("-created_at")[:5]:
            finished = batch.processed_count + batch.failed_count
            progress = (
                int((batch.processed_count / batch.total_count) * 100)
                if batch.total_count > 0 else 0
            )
            if batch.total_count == 0:
                batch_status = "empty"
            elif finished < batch.total_count:
                batch_status = "in_progress"
            elif batch.failed_count == 0:
                batch_status = "completed"
            elif batch.processed_count == 0:
                batch_status = "failed"
            else:
                batch_status = "partial"

            recent_batches.append({
                "id":              str(batch.id),
                "total_count":     batch.total_count,
                "processed_count": batch.processed_count,
                "failed_count":    batch.failed_count,
                "progress":        progress,
                "status":          batch_status,
                "created_at":      batch.created_at,
            })

        return Response({
            "summary": {
                "total_candidates":    total_candidates,
                "total_uploaded":      total_uploaded,
                "total_processed":     total_processed,
                "total_failed":        total_batch_failed,
                "success_rate":        success_rate,
                "total_batches":       total_batches,
                "emailed_candidates":  emailed_candidates,
                "total_emails_sent":   total_emails_sent,
                "total_organizations": total_organizations,
                "total_contacts":      total_contacts,
            },
            "quality": {
                "passed":        quality_counts.get("passed", 0),
                "failed":        quality_counts.get("failed", 0),
                "pending":       quality_counts.get("pending", 0),
                "manual_review": quality_counts.get("manual", 0),
            },
            "ai_processing": {
                "completed":   ai_status_counts.get("completed", 0),
                "in_progress": ai_status_counts.get("in_progress", 0),
                "failed":      ai_status_counts.get("failed", 0),
                "not_started": ai_status_counts.get("not_started", 0),
            },
            "availability": {
                "available":      availability_counts.get("available", 0),
                "not_available":  availability_counts.get("not_available", 0),
                "open_to_offers": availability_counts.get("open_to_offers", 0),
            },
            "sources": {
                "local_upload": source_counts.get("local_upload", 0),
                "crm":          source_counts.get("crm", 0),
                "previous_db":  source_counts.get("previous_db", 0),
            },
            "recent_activity": {
                "new_candidates_last_7_days":  new_last_7,
                "new_candidates_last_30_days": new_last_30,
            },
            "organizations": {
                "total":           total_organizations,
                "total_contacts":  total_contacts,
                "geocoded":        orgs_geocoded,
                "not_geocoded":    total_organizations - orgs_geocoded,
                "phase_breakdown": phase_counts,
            },
            "recent_batches": recent_batches,
        })


# ---------------------------------------------------------------------------
# Activity Log
# ---------------------------------------------------------------------------
class ActivityLogView(APIView):
    """
    GET /api/auth/activity/
    Returns recent activity log entries.

    Query params:
        ?severity=error          filter by severity (info/success/warning/error)
        ?unread=true             only unread notifications
        ?limit=50                number of entries (default 50, max 100)
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    @extend_schema(
        responses={200: OpenApiResponse(description="Activity log entries")},
        summary="Get activity log and notifications",
        tags=["Dashboard"],
    )
    def get(self, request):
        from account.models import ActivityLog
        from candidate.utils.pagination import StandardPagination

        qs = ActivityLog.objects.all()

        severity = request.query_params.get("severity")
        unread   = request.query_params.get("unread")

        if severity:
            qs = qs.filter(severity=severity)
        if unread == "true":
            qs = qs.filter(is_read=False)

        unread_count = ActivityLog.objects.filter(is_read=False).count()

        paginator  = StandardPagination()
        page       = paginator.paginate_queryset(qs, request)

        data = [
            {
                "id":              str(log.id),
                "event_type":      log.event_type,
                "severity":        log.severity,
                "title":           log.title,
                "message":         log.message,
                "is_read":         log.is_read,
                "candidate_id":    str(log.candidate_id) if log.candidate_id else None,
                "batch_id":        str(log.batch_id) if log.batch_id else None,
                "organization_id": str(log.organization_id) if log.organization_id else None,
                "created_at":      log.created_at,
            }
            for log in page
        ]

        response_data              = paginator.get_paginated_response(data).data
        response_data["unread_count"] = unread_count
        return Response(response_data)


class MarkNotificationsReadView(APIView):
    """
    POST /api/auth/activity/mark-read/
    Marks all or specific notifications as read.

    Body (optional):
    { "ids": ["uuid1", "uuid2"] }   → mark specific ones
    {}                               → mark all as read
    """
    permission_classes = [IsAuthenticated, IsSuperUser]

    @extend_schema(
        responses={200: OpenApiResponse(description="Marked as read")},
        summary="Mark notifications as read",
        tags=["Dashboard"],
    )
    def post(self, request):
        from account.models import ActivityLog

        ids = request.data.get("ids", [])

        if ids:
            updated = ActivityLog.objects.filter(
                id__in=ids, is_read=False
            ).update(is_read=True)
        else:
            updated = ActivityLog.objects.filter(is_read=False).update(is_read=True)

        return Response({
            "message": f"{updated} notification(s) marked as read.",
            "updated": updated,
        })