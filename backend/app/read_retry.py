"""
Retry a read request once when the database connection drops or times out.

The live database is reached over a long network path (Supabase pooler), where a connection can be
closed, a DNS lookup can fail or a connect can time out for a moment. A GET that fails that way is
run once more on a fresh pooled connection (the pool's pre-ping discards the dead one) before the
error is returned. Only reads are retried, only before any part of the response was sent, and never
the GETs that start work (an extraction, an AI summary), so a retry cannot repeat a change.
"""
import asyncio
import logging
import re

from .services.audit import is_connection_error

logger = logging.getLogger("app.read_retry")

RETRY_DELAY_SECONDS = 0.5
# GET endpoints that start work and must not run twice
NOT_RETRIED = (
    re.compile(r"^/api/v1/documents/[^/]+/extract$"),
    re.compile(r"^/api/v1/generation/case/[^/]+/summary$"),
)


class ReadRetryMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("GET", "HEAD") \
                or any(rx.match(scope["path"]) for rx in NOT_RETRIED):
            await self.app(scope, receive, send)
            return

        started = False

        async def tracking_send(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        async def empty_body():
            # A GET has no body; the retry gets the same (empty) request body again
            return {"type": "http.request", "body": b"", "more_body": False}

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started or not is_connection_error(exc):
                raise
            logger.warning("Database connection failed on %s (%s); retrying once on a fresh connection",
                           scope["path"], type(exc).__name__)
            await asyncio.sleep(RETRY_DELAY_SECONDS)
            await self.app(scope, empty_body, tracking_send)
