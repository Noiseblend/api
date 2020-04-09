from typing import Any

from sanic.response import HTTPResponse, json
from stringcase import camelcase

from .transform import transform_datetime, transform_keys, transform_values


def camelcase_json(response: Any) -> HTTPResponse:
    return json(
        transform_values(transform_keys(response, camelcase), transform_datetime)
    )
