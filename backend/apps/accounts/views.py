"""Phase 1 account endpoints: session and logout (§5.5)."""

from __future__ import annotations

import logging

from django.contrib.auth import logout as django_logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserSerializer

logger = logging.getLogger(__name__)


@method_decorator(ensure_csrf_cookie, name="dispatch")
class SessionView(APIView):
    """`GET /api/auth/session/` — who, if anyone, is signed in.

    Returns 200 either way. The SPA calls this once on boot to decide between
    the login screen and the dashboard; an anonymous visitor is a normal
    outcome, not an error, and modelling it as a 401 would make every cold load
    look like a failure in the console and in the client's error handling.

    It also plants the CSRF cookie, which the client echoes as `X-CSRFToken` on
    the only unsafe Phase 1 route (logout).
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def get(self, request):
        user = request.user
        if user is None or not user.is_authenticated:
            return Response({"authenticated": False, "user": None})
        return Response({"authenticated": True, "user": UserSerializer(user).data})


class LogoutView(APIView):
    """`POST /api/auth/logout/` — end the RepoVitals session.

    POST-only on purpose: a GET logout is trivially triggered by any embedded
    image or a prefetching browser, and the front-end's back-navigation guard
    depends on logout being a deliberate act (§10 Phase 1).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        django_logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)
