from collections import defaultdict
from hashlib import sha1
from uuid import uuid4

import addict
from sanic.response import text
from spf import SanicPlugin

from .. import logger
from ..helpers import get_request_id
from .priority import PRIORITY


def generate_etag():
    return sha1(uuid4().bytes).hexdigest()


class CacheControl(SanicPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_registered(self, context, reg, *args, **kwargs):
        context.responses = defaultdict(dict)


cache_control = CacheControl()


@cache_control.middleware(
    priority=PRIORITY.request.check_etag, with_context=True, relative="post"
)
async def check_etag(request, context):
    if request.method == "OPTIONS":
        return

    etag = request.headers.get("If-None-Match")
    if etag:
        request_id = get_request_id(request)
        if request_id in context.responses and etag in context.responses[request_id]:
            return text("", headers=context.responses[request_id][etag], status=304)


def get_cache_control_header(cache):
    header = []

    if not cache.max_age:
        header.append("no-cache")
    else:
        header.append(f"max-age={int(cache.max_age)}")

    if not cache.without_user_id:
        header.append("private")

    return ", ".join(header)


@cache_control.middleware(
    priority=PRIORITY.response.cache_response,
    with_context=True,
    attach_to="response",
    relative="post",
)
async def cache_response(request, response, context):
    cache, invalidate = None, None
    try:
        invalidate = response.__invalidate__
        cache = response.__cache__
        if cache is True:
            cache = addict.Dict(without_user_id=False)
        elif isinstance(cache, dict):
            cache = addict.Dict(cache)
    except:
        if isinstance(response, dict):
            logger.error("Response is dict: %s", response)

        return response

    if invalidate:
        for inv in invalidate:
            context.responses.pop(get_request_id(**inv), None)

    if cache:
        try:
            request_id = get_request_id(request, without_user_id=cache.without_user_id)
        except ValueError:
            return response

        etag = generate_etag()
        cache_headers = {"Cache-Control": get_cache_control_header(cache)}
        if not cache.without_etag:
            context.responses[request_id][etag] = cache_headers
            cache_headers["ETag"] = etag

        response.headers.update(cache_headers)

    if len(context.responses) > 20:
        context.responses.clear()

    return response
