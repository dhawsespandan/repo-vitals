"""One error shape for the whole API: ``{"code": ..., "message": ...}``.

The frontend's typed client (`frontend/src/api/client.ts`) reads exactly these
two keys, and the pre-scan validation table (§5.6) specifies its outcomes as
`code` values, so the envelope has to be stable from Phase 1 onward.
"""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

# Default human-readable text for the codes DRF raises on its own behalf.
_STATUS_DEFAULTS = {
    400: ("bad_request", "That request wasn't valid."),
    401: ("not_authenticated", "You need to sign in to do that."),
    403: ("forbidden", "You don't have access to that."),
    404: ("not_found", "We couldn't find that."),
    405: ("method_not_allowed", "That method isn't allowed here."),
    429: ("throttled", "Too many requests. Please slow down."),
    500: ("server_error", "Something went wrong on our side."),
}


class ApiError(APIException):
    """Raise this anywhere a specific `code` matters to the frontend."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int | None = None,
        extra: dict | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.extra = extra or {}
        if status_code is not None:
            self.status_code = status_code
        super().__init__(detail=message, code=code)


def exception_handler(exc, context):
    """DRF exception hook that flattens everything into the standard envelope."""
    if isinstance(exc, ApiError):
        return Response(
            {"code": exc.code, "message": exc.message, **exc.extra},
            status=exc.status_code,
        )

    response = drf_exception_handler(exc, context)
    if response is None:
        # Unhandled exception: let Django's own 500 machinery log it. Returning
        # None here keeps the traceback in the logs instead of swallowing it.
        return None

    code, message = _STATUS_DEFAULTS.get(
        response.status_code, ("error", "Request failed.")
    )
    detail = response.data
    if isinstance(detail, dict) and "detail" in detail:
        message = str(detail["detail"])
        drf_code = getattr(detail["detail"], "code", None)
        if drf_code:
            code = str(drf_code)
    response.data = {"code": code, "message": message}
    return response
