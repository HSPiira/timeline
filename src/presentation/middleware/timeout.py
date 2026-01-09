"""Request timeout middleware."""

import asyncio
import time
from collections.abc import Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class TimeoutMiddleware(BaseHTTPMiddleware):
    """
    Middleware to enforce request timeouts.

    Prevents long-running requests from consuming resources indefinitely.
    """

    def __init__(self, app, timeout: float = 30.0):
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with timeout."""
        start_time = time.time()

        try:
            # Apply timeout to request processing
            response = await asyncio.wait_for(call_next(request), timeout=self.timeout)

            # Add response time header
            process_time = time.time() - start_time
            response.headers["X-Process-Time"] = str(process_time)

            return response

        except asyncio.TimeoutError:
            process_time = time.time() - start_time
            return JSONResponse(
                status_code=504,
                content={
                    "error": "REQUEST_TIMEOUT",
                    "message": f"Request timeout after {process_time:.2f} seconds",
                },
            )
