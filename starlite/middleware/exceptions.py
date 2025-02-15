from typing import TYPE_CHECKING, Any

from starlette.middleware.errors import ServerErrorMiddleware

from starlite.connection import Request
from starlite.enums import ScopeType
from starlite.exceptions import WebSocketException
from starlite.status_codes import HTTP_500_INTERNAL_SERVER_ERROR
from starlite.utils import create_exception_response
from starlite.utils.exception import get_exception_handler

if TYPE_CHECKING:
    from starlite.response import Response
    from starlite.types import ASGIApp, ExceptionHandlersMap, Receive, Scope, Send
    from starlite.types.asgi_types import WebSocketCloseEvent


class ExceptionHandlerMiddleware:
    def __init__(self, app: "ASGIApp", debug: bool, exception_handlers: "ExceptionHandlersMap") -> None:
        """This middleware is used to wrap an ASGIApp inside a try catch block
        and handles any exceptions raised.

        Notes:
            * It's used in multiple layers of Starlite.

        Args:
            app: The 'next' ASGI app to call.
            debug: Whether 'debug' mode is enabled
            exception_handlers: A dictionary mapping status codes and/or exception types to handler functions.
        """
        self.app = app
        self.exception_handlers = exception_handlers
        self.debug = debug

    async def __call__(self, scope: "Scope", receive: "Receive", send: "Send") -> None:
        """
        Args:
            scope: The ASGI connection scope.
            receive: The ASGI receive function.
            send: The ASGI send function.

        Returns:
            None
        """
        try:
            await self.app(scope, receive, send)
        except Exception as e:  # pylint: disable=broad-except
            starlite_app = scope["app"]
            for hook in starlite_app.after_exception:
                await hook(e, scope, starlite_app.state)

            if scope["type"] == ScopeType.HTTP:
                exception_handler = (
                    get_exception_handler(self.exception_handlers, e) or self.default_http_exception_handler
                )
                response = exception_handler(Request(scope=scope, receive=receive, send=send), e)
                await response(scope=scope, receive=receive, send=send)
                return

            if isinstance(e, WebSocketException):
                code = e.code
                reason = e.detail
            else:
                code = 4000 + getattr(e, "status_code", HTTP_500_INTERNAL_SERVER_ERROR)
                reason = getattr(e, "detail", repr(e))
            event: "WebSocketCloseEvent" = {"type": "websocket.close", "code": code, "reason": reason}
            await send(event)

    def default_http_exception_handler(self, request: Request, exc: Exception) -> "Response[Any]":
        """Default handler for exceptions subclassed from HTTPException."""
        status_code = getattr(exc, "status_code", HTTP_500_INTERNAL_SERVER_ERROR)
        if status_code == HTTP_500_INTERNAL_SERVER_ERROR and self.debug:
            # in debug mode, we just use the serve_middleware to create an HTML formatted response for us
            server_middleware = ServerErrorMiddleware(app=self)  # type: ignore[arg-type]
            return server_middleware.debug_response(request=request, exc=exc)  # type: ignore
        return create_exception_response(exc)
