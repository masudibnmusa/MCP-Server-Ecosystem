"""Bearer-token check for remote (streamable HTTP) servers. Pure ASGI so streaming works."""
import hmac
import os

from dotenv import load_dotenv
from starlette.responses import JSONResponse

load_dotenv()


class BearerAuthMiddleware:
    def __init__(self, app, token: str | None = None):
        self.app = app
        self.token = token or os.getenv("HTTP_SERVER_TOKEN", "")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if not self.token:
            response = JSONResponse({"error": "Server token is not configured."}, status_code=500)
            await response(scope, receive, send)
            return

        headers = dict(scope["headers"])
        auth = headers.get(b"authorization", b"").decode()
        supplied = auth[7:] if auth.lower().startswith("bearer ") else ""

        if not hmac.compare_digest(supplied.encode(), self.token.encode()):
            response = JSONResponse({"error": "Unauthorized"}, status_code=401)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)