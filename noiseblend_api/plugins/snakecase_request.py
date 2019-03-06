from sanic.request import RequestParameters
from spf import SanicPlugin
from stringcase import snakecase

from ..transform import transform_keys
from .priority import PRIORITY


class SnakecaseRequest(SanicPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


snakecase_request = SnakecaseRequest()


@snakecase_request.middleware(priority=PRIORITY.request.camelcase_to_snakecase)
async def camelcase_to_snakecase(request):
    if request.method == "OPTIONS":
        return

    if request.args:
        request.parsed_args = RequestParameters(transform_keys(request.args, snakecase))
    try:
        if request.json:
            request.parsed_json = transform_keys(request.json, snakecase)
    except:
        pass
