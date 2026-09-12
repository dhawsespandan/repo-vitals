"""Request-scoped log context — §10 Phase 9's "structured logging".

One middleware, one job: give every log line written while handling a request
the id of that request and the id of whoever made it, and hand the id back on
the response so a person reporting "it failed at 14:32" can be answered with a
grep instead of a guess.

**The request id is generated here and an inbound one is ignored.** Honouring
`X-Request-ID` from the client is a common convenience and it puts a
client-controlled string into every log line this request writes; a newline in
it forges a log entry, and there is no tracing system upstream of this service
whose id would be worth adopting anyway.

**Resolving `request.user` here costs nothing and buys the attribution.**
`request.user` is lazy, so touching it forces the session decode one frame
earlier than the view would have. For an authenticated API route that work was
going to happen regardless and Django caches it on the request; for a request
with no session cookie — the keepalive pinger hitting `/api/health/` every ten
minutes (§1.17) — there is no session to decode and nothing to pay.

It sits *after* `AuthenticationMiddleware` in the stack, because before it
there is no `request.user` to read.
"""

from __future__ import annotations

from apps.common.logging import bind, new_request_id

#: The response header carrying the id back. Named for the near-universal
#: convention rather than invented, so a proxy or a browser devtools pane that
#: already knows the header shows it without being configured.
HEADER = "X-Request-ID"


def _user_id(request) -> str | None:
    """The requester's primary key, or None for anyone not signed in.

    Defensive because this runs on every request including error paths: a
    misconfiguration that leaves `request.user` unset must not turn a 500 into
    a 500 *inside the logging middleware*, where the traceback would describe
    the wrong problem.
    """
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return None
    return str(user.pk)


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = new_request_id()
        # Stashed on the request as well as in the context: a view or an
        # exception handler that wants to show the id to the user (or put it in
        # an error envelope) should not have to reach into a contextvar.
        request.request_id = request_id

        with bind(request_id=request_id, user_id=_user_id(request)):
            response = self.get_response(request)

        response[HEADER] = request_id
        return response
