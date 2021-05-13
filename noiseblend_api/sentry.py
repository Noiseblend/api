import asyncio

import sentry_sdk
from sanic.exceptions import SanicException
from sanic.handlers import ErrorHandler
from sanic.response import text

from .helpers import get_user_dict

REQUEST_ATTRS = (
    "args",
    "body",
    "content_type",
    "cookies",
    "files",
    "form",
    "headers",
    "host",
    "ip",
    "json",
    "path",
    "port",
    "query_string",
    "scheme",
    "socket",
    "token",
    "uri_template",
    "url",
)


def get_request_attr(request, attr):
    try:
        return getattr(request, attr)
    except Exception:
        return None


class SentryLogging(ErrorHandler):
    def __init__(self, *args, config=None, logger=None, **kwargs):
        super().__init__(*args, **kwargs)
        sentry_sdk.init(**config.sentry)
        self.logger = logger

    async def log_to_sentry(self, request, exception):
        spotify = request.get("spotify")
        dbpool = request.get("dbpool")
        try:
            with sentry_sdk.push_scope() as scope:
                if spotify and dbpool:
                    try:
                        user_dict = await get_user_dict(spotify, dbpool)
                        scope.user = user_dict
                    except:
                        pass

                for k in REQUEST_ATTRS:
                    scope.set_extra(k, get_request_attr(request, k))
                sentry_sdk.capture_exception(exception)
        except Exception as e:
            self.logger.exception(e)

    def default(self, request, exception):
        asyncio.get_event_loop().create_task(self.log_to_sentry(request, exception))
        if issubclass(type(exception), SanicException):
            return super().default(request, exception)

        self.logger.exception(exception)
        return text("Internal Server Error", status=500)
