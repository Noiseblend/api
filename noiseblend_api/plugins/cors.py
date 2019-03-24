from sanic import response
from spf import SanicPlugin

from .priority import PRIORITY


# pylint: disable=unused-argument
class CORS(SanicPlugin):
    async def route_wrapper(
        self,
        route,
        request,
        context,
        request_args,
        request_kw,
        *decorator_args,
        with_context=None,
        **decorator_kw
    ):
        if request.method == "OPTIONS":
            return response.HTTPResponse(status=204)


cors = CORS()


@cors.middleware(priority=PRIORITY.request.cors, relative="pre")
async def cors_request(request):
    if request.method == "OPTIONS":
        return response.HTTPResponse(status=204)
