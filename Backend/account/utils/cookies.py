from django.conf import settings


def set_auth_cookies(response, access_token: str, refresh_token: str) -> None:
    """
    Sets both access and refresh tokens as HttpOnly, Secure cookies.
    This prevents XSS attacks — JavaScript cannot read these cookies.
    """
    is_secure = getattr(settings, "SESSION_COOKIE_SECURE", False)
    samesite  = getattr(settings, "SESSION_COOKIE_SAMESITE", "Lax")

    # Access Token Cookie
    response.set_cookie(
        key=settings.SIMPLE_JWT.get("AUTH_COOKIE_ACCESS", "access_token"),
        value=access_token,
        max_age=int(settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,          # Not accessible via JavaScript
        secure=is_secure,       # Only sent over HTTPS in production
        samesite=samesite,      # Protects against CSRF while allowing normal navigation
        path="/",
    )

    # Refresh Token Cookie
    response.set_cookie(
        key=settings.SIMPLE_JWT.get("REFRESH_COOKIE_NAME", "refresh_token"),
        value=refresh_token,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        httponly=True,
        secure=is_secure,
        samesite=samesite,
        path=settings.SIMPLE_JWT.get("REFRESH_COOKIE_PATH", "/api/auth"),
    )


def unset_auth_cookies(response) -> None:
    """
    Clears both auth cookies on logout.
    """
    response.delete_cookie(
        key=settings.SIMPLE_JWT.get("AUTH_COOKIE_ACCESS", "access_token"),
        path="/",
    )
    response.delete_cookie(
        key=settings.SIMPLE_JWT.get("REFRESH_COOKIE_NAME", "refresh_token"),
        path=settings.SIMPLE_JWT.get("REFRESH_COOKIE_PATH", "/api/auth"),
    )