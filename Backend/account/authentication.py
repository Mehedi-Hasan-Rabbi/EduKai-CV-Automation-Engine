from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken



class CookieJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that reads the access token from an HttpOnly cookie
    instead of the Authorization header.

    Falls back to the Authorization header if cookie is not present
    (useful for API clients / Swagger UI).
    """

    def authenticate(self, request):
        cookie_name = settings.SIMPLE_JWT.get("AUTH_COOKIE_ACCESS", "access_token")
        raw_token = request.COOKIES.get(cookie_name)

        # Fallback: try Authorization header (for Swagger / API clients)
        if raw_token is None:
            return super().authenticate(request)

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
    

    def get_user(self, validated_token):
        """
        Override to provide a clean, structured error when the token's user
        no longer exists in the database (e.g. account was deleted).

        The 'token_invalid' code signals the client to clear cookies + redirect to login.
        """
        try:
            return super().get_user(validated_token)
        except AuthenticationFailed:
            raise AuthenticationFailed(
                {
                    "detail": "Your session is no longer valid. Please log in again.",
                    "code": "token_invalid",
                }
            )
        

def custom_exception_handler(exc, context):
    from rest_framework.views import exception_handler
    """
    Extends DRF's default exception handler to automatically clear
    auth cookies when the token is invalid or the session has expired.
    """
    response = exception_handler(exc, context)

    if response is not None and isinstance(response.data, dict):
        code = response.data.get("code")
        if code == "token_invalid":
            access_cookie = settings.SIMPLE_JWT.get("AUTH_COOKIE_ACCESS", "access_token")
            refresh_cookie = settings.SIMPLE_JWT.get("REFRESH_COOKIE_NAME", "refresh_token")
            refresh_path = settings.SIMPLE_JWT.get("REFRESH_COOKIE_PATH", "/api/auth")

            response.delete_cookie(access_cookie, path="/")
            response.delete_cookie(refresh_cookie, path=refresh_path)

    return response