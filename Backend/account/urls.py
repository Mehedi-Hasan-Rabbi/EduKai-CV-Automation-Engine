from django.urls import path
from rest_framework_simplejwt.views import TokenVerifyView
from account.views import (
    LoginView,
    LogoutView,
    MeView,
    RegisterView,
    TokenRefreshView,
    ProfileUpdateView,
    PasswordUpdateView,
    ForgotPasswordView,
    VerifyOTPView,
    ResetPasswordView,
    DashboardView,
    ActivityLogView,
    MarkNotificationsReadView,
)

app_name = "account"

urlpatterns = [
    # Authentication endpoints
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),

    # Current user endpoints
    path("me/", MeView.as_view(), name="me"),
    path("profile/update/", ProfileUpdateView.as_view(), name="profile_update"),
    path("password/update/", PasswordUpdateView.as_view(), name="password_update"),

    # Password reset flow
    path("forgot-password/", ForgotPasswordView.as_view(), name="forgot_password"),
    path("verify-otp/", VerifyOTPView.as_view(), name="verify_otp"),
    path("reset-password/", ResetPasswordView.as_view(), name="reset_password"),
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("activity/", ActivityLogView.as_view(), name="activity_log"),
    path("activity/mark-read/", MarkNotificationsReadView.as_view(), name="mark_notifications_read"),
]
