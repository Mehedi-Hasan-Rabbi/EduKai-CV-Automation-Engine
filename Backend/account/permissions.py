from rest_framework.permissions import BasePermission
from account.models import UserRole


class IsSuperUser(BasePermission):
    """Allows access only to users with the SUPERUSER role."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.SUPERUSER
        )


class IsNormalUser(BasePermission):
    """Allows access only to users with the NORMALUSER role."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.NORMALUSER
        )


class IsSuperUserOrReadOnly(BasePermission):
    """
    Full access for SUPERUSER.
    Read-only access for authenticated normal users.
    """

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return request.user.role == UserRole.SUPERUSER