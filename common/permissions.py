"""Reading permissions across every backend that grants them."""

from django.contrib.auth.models import User
from django.db.models import Q

MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"
TEAM_BACKEND = "volunteer.auth_backends.TeamPermissionsBackend"


def users_with_perm(perm, include_superusers=True):
    """Everyone who holds ``perm`` by any route: a group or a direct grant
    (Django's backend) or the active edition's teams.

    ``User.objects.with_perm`` insists on a ``backend`` argument while more
    than one backend can answer, so recipient queries come through here.
    """
    by_group = User.objects.with_perm(
        perm, backend=MODEL_BACKEND, include_superusers=include_superusers
    )
    by_team = User.objects.with_perm(
        perm, backend=TEAM_BACKEND, include_superusers=include_superusers
    )
    return User.objects.filter(
        Q(pk__in=by_group.values("pk")) | Q(pk__in=by_team.values("pk"))
    ).order_by("username")
