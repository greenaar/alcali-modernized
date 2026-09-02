"""Recording Alcali's own changes.

Deliberately best effort: an audit write must never be the reason a user's
action fails, so failures here are swallowed rather than propagated.
"""
import json
import logging

from django_currentuser.middleware import get_current_user

logger = logging.getLogger(__name__)


def record(action, target="", detail=None, user=None):
    from api.models import AuditLog

    try:
        if user is None:
            user = get_current_user()
        if user is not None and not getattr(user, "is_authenticated", False):
            user = None
        if isinstance(detail, (dict, list)):
            detail = json.dumps(detail, default=str, sort_keys=True)
        AuditLog.objects.create(
            user=user,
            username=getattr(user, "username", "") or "",
            action=action,
            target=str(target)[:255],
            detail=detail or "",
        )
    except Exception:  # pragma: no cover - never break the caller
        logger.exception("could not write audit entry for %s", action)


class AuditedModelViewSet:
    """Mixin recording create, update and delete on a ModelViewSet."""

    audit_name = None

    def _audit_name(self):
        return self.audit_name or self.queryset.model._meta.model_name

    def perform_create(self, serializer):
        super().perform_create(serializer)
        record(
            "{}.create".format(self._audit_name()),
            target=str(serializer.instance),
        )

    def perform_update(self, serializer):
        super().perform_update(serializer)
        record(
            "{}.update".format(self._audit_name()),
            target=str(serializer.instance),
        )

    def perform_destroy(self, instance):
        target = str(instance)
        super().perform_destroy(instance)
        record("{}.delete".format(self._audit_name()), target=target)
