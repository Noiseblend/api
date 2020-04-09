from inspect import isawaitable

from sanic.response import HTTPResponse, json
from spf import SanicPlugin
from stringcase import camelcase

from ..transform import transform_datetime, transform_keys, transform_values
from .priority import PRIORITY


class CamelcaseResponse(SanicPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


camelcase_response = CamelcaseResponse()


@camelcase_response.middleware(
    attach_to="response",
    priority=PRIORITY.response.snakecase_to_camelcase,
    relative="pre",
)
async def snakecase_to_camelcase(request, response):
    if request.method == "OPTIONS":
        return response
    if isinstance(response, HTTPResponse):
        return response

    cache, invalidate = None, None
    if isawaitable(response):
        try:
            response = await response
        except RuntimeError:
            pass

    if response and ("__cache__" in response or "__invalidate__" in response):
        cache = response.get("__cache__")
        invalidate = response.get("__invalidate__")
        response = response["__response__"]

    initial_response = response
    response = json(
        transform_values(transform_keys(response, camelcase), transform_datetime)
    )
    response.__cache__ = cache
    response.__invalidate__ = invalidate
    response.__initial__ = initial_response

    return response
