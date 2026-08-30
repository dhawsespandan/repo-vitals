"""Ownership scoping for every resource route (§5.5, §11 "BOLA").

§5.5 says every resource route sits behind `OwnedQuerySetMixin`, and §11
tracks BOLA — reaching another user's resource by guessing its id — as a risk
verified "structurally" rather than by a check somewhere in each view. This
module is that structure.

The mixin narrows the queryset itself, so a foreign id is not *rejected*, it
is simply not in the set: DRF's `get_object()` then 404s on its own. That
matters more than it sounds. A permission check that runs after the object is
fetched has to be remembered in every view, and a 403 on a foreign id still
confirms the id exists. Filtering the queryset makes forgetting impossible
(the view has no unfiltered queryset to reach for) and leaks nothing.

Views must therefore never bypass `get_queryset()` — no `Model.objects.get()`
inside a handler. Phase 9's BOLA suite covers every route to keep that honest.
"""

from __future__ import annotations


class OwnedQuerySetMixin:
    """Restrict the view's queryset to rows owned by the requesting user."""

    #: Path from the model to its owning user. Resources that reach the user
    #: indirectly override it (Phase 3's scans use "repository__user").
    owner_field = "user"

    def get_queryset(self):
        queryset = super().get_queryset()
        user = getattr(self.request, "user", None)
        if user is None or not user.is_authenticated:
            # Belt and braces: DRF's IsAuthenticated has already run by here,
            # so this is unreachable through the API. It exists so that a view
            # configured with the wrong permission class fails closed (empty)
            # instead of open (every row).
            return queryset.none()
        return queryset.filter(**{self.owner_field: user})
