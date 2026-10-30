"""A support ID for every request, and a safe answer when one fails unexpectedly.

Validation, authorization and conflict errors are raised deliberately and
already say what went wrong. What had no answer was the unexpected failure: an
unhandled exception came back as a bare "Internal Server Error" that the person
could not quote and nobody could find in the log. Each request now carries an
ID (the caller's ``X-Request-ID`` if it sent a sane one), returned on every
response and written on the log line of any failure, and an unexpected
exception answers with that ID — never with the exception text or a trace.

The middleware is plain ASGI rather than ``@app.middleware("http")``: the
latter wraps responses in a way that interferes with the server-sent event
stream and large file downloads this API serves.
"""
from __future__ import annotations

import logging
import re
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("app.request")

HEADER = "X-Request-ID"
_HEADER_BYTES = HEADER.lower().encode()
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def request_id_of(request: Request) -> str:
    return request.scope.get("state", {}).get("request_id") or "unknown"


class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = next((value.decode("latin-1") for key, value in scope.get("headers", []) if key == _HEADER_BYTES), "")
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != _HEADER_BYTES]
                headers.append((_HEADER_BYTES, request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_id)


def install(app: FastAPI) -> None:
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(Exception)
    async def unexpected_failure(request: Request, exc: Exception):
        support_id = request_id_of(request)
        # Method and path only: no query string, headers or body, which can
        # carry tokens, credentials or uploaded content.
        logger.exception("Unhandled error support_id=%s %s %s", support_id, request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": {
                "message": "Something went wrong on the server and the request did not complete. If it keeps happening, contact support with this support ID.",
                "supportId": support_id,
            }},
            headers={HEADER: support_id},
        )
