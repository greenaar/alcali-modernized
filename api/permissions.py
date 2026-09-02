from rest_framework import permissions


class IsLoggedInUserOrAdmin(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        return obj == request.user or request.user.is_staff


class IsAdminUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.user and request.user.is_staff

    def has_object_permission(self, request, view, obj):
        return request.user and request.user.is_staff


class IsAdminUserOrReadOnly(permissions.BasePermission):
    """Anyone signed in may read; only staff may change Alcali's own records.

    Actions that Alcali delegates to the master (running a job, managing keys
    or schedules) stay open, because salt-api applies that user's eauth ACL to
    them. The records below never reach Salt, so nothing else would check.
    """

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_staff)

    def has_object_permission(self, request, view, obj):
        return self.has_permission(request, view)
