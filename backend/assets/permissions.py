from rest_framework.permissions import BasePermission

from .models import Role


class IsClusterManager(BasePermission):
    """Maintenance reports and the manager's consumables screens are for Cluster Managers only."""

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user and user.is_authenticated and user.role_id and user.role.name == Role.CLUSTER_MANAGER
        )
