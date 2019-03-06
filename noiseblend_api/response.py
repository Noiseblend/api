from typing import Any

from sanic.response import HTTPResponse, json
from stringcase import camelcase

from .transform import transform_keys


def camelcase_json(response: Any) -> HTTPResponse:
    return json(transform_keys(response, camelcase))
