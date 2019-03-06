from oauthlib.oauth2.rfc6749.errors import InvalidGrantError
from sanic.exceptions import Unauthorized
from spf import SanicPlugin

from .priority import PRIORITY


class Auth(SanicPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_registered(self, context, reg, *args, **kwargs):
        context.unauthorized_routes = set(kwargs.get("unauthorized_routes", []))


auth = Auth()


@auth.middleware(priority=PRIORITY.request.authorize_request, with_context=True)
async def authorize_request(request, context):
    if request.method == "OPTIONS":
        return
    if request.path in context.unauthorized_routes:
        return

    spotify = context.shared.request[id(request)].spotify
    if not spotify.is_authenticated and request.path != "/logout":
        raise Unauthorized("You have to authenticate first")


@auth.exception(InvalidGrantError, with_context=True)
async def revoked_token_handler(request, _, context=None):
    if context:
        spotify = context.shared.request[id(request)].spotify
        await context.shared.dbpool.execute(
            "UPDATE users SET token = '{}' WHERE id = $1", spotify.user_id
        )
    raise Unauthorized("Refresh token revoked, please reauthenticate")
