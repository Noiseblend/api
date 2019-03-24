from sanic import response
from spf import SanicPlugin


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
