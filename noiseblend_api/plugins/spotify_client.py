import asyncio
import uuid
from collections import OrderedDict

import addict
import aioredis
from sanic.exceptions import Unauthorized
from spf import SanicPlugin

from .. import config, logger
from ..overrides import AppSpotify
from ..sql import SQL
from .priority import PRIORITY


async def close_session(spotify):
    if spotify.session:
        await spotify.session.close()


CLIENT_CACHE = OrderedDict()


# @async_lru(size=10, evict_callback=close_session, cache=CLIENT_CACHE)
async def client(
    auth_token=None, query_token=None, blend_token=None, redis=None, dbpool=None
):
    app_user = None
    blend = None

    queries = []
    if blend_token:
        queries.append(dbpool.fetchrow(SQL.blend_auth, blend_token))

    if query_token:
        queries.append(dbpool.fetchrow(SQL.app_user_auth, query_token))

    if auth_token:
        queries += [
            dbpool.fetchrow(SQL.app_user_auth, auth_token),
            dbpool.fetchrow(SQL.app_user_auth_long_lived, auth_token),
            dbpool.fetchrow(SQL.app_user_by_token, auth_token),
            dbpool.fetchval(SQL.oauth_token_expired, auth_token),
        ]

    result = None
    for query_future in asyncio.as_completed(queries):
        result = await query_future
        if result is True:
            raise Unauthorized(
                "The access token expired",
                scheme="Bearer",
                error="invalid_token",
                error_description="The access token expired",
            )
        if result:
            if "user" in result:
                blend = addict.Dict(dict(result))
            else:
                app_user = result
            break

    user_id, username = None, None
    if app_user:
        user_id = str(app_user["id"])
        username = str(app_user["username"])
    elif blend:
        user_id = str(blend["user"])
        username = str(blend["username"])

    spotify = AppSpotify(
        user_id=user_id,
        username=username,
        client_id=config.spotify.client_id,
        client_secret=config.spotify.client_secret,
        redirect_uri=config.spotify.redirect_uri,
        blend=blend,
        redis=redis,
        dbpool=dbpool,
    )
    await spotify.authenticate_user_pg(scope=config.spotify.scope)
    return spotify


class SpotifyClient(SanicPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_registered(self, context, reg, *args, **kwargs):
        context.shared.redis = None


spotify_client = SpotifyClient()
BLEND_PATHS = {"/blend", "/me", "/is-authenticated", "/authenticate"}
REDIS = config.redis


@spotify_client.middleware(priority=PRIORITY.request.add_redis_pool, with_context=True)
async def add_redis_pool(request, context):
    if request.method == "OPTIONS":
        return
    if not context.shared.redis:
        context.shared.redis = await aioredis.create_redis_pool(
            (REDIS.auth.host or "127.0.0.1", REDIS.auth.port or 6379),
            password=REDIS.auth.password or None,
            db=REDIS.db or 0,
            ssl=REDIS.ssl or False,
            minsize=REDIS.pool.minsize or 1,
            maxsize=REDIS.pool.maxsize or 10,
        )


def create_client_invalidation(key, cache, _client):
    async def invalidate_client():
        cache.pop(key, None)
        await close_session(_client)

    return invalidate_client


@spotify_client.middleware(
    priority=PRIORITY.request.add_spotify_client, with_context=True
)
async def add_spotify_client(request, context):
    if request.method == "OPTIONS":
        return

    ctx = context.shared.request[id(request)]
    query_token = (
        request.headers.get("Token")
        or request.args.get("token")
        or request.cookies.get("authToken")
    )
    blend_token = request.headers.get("BlendToken")
    if blend_token and request.path not in BLEND_PATHS:
        raise Unauthorized("Authentication required", scheme="Bearer")

    try:
        auth_token = str(uuid.UUID(request.token))
    except:
        auth_token = None
    try:
        query_token = str(uuid.UUID(query_token))
    except:
        query_token = None

    logger.debug(
        "Getting Spotify client for auth_token=%s, query_token=%s, blend_token=%s",
        auth_token,
        query_token,
        blend_token,
    )
    client_args = {
        "auth_token": auth_token,
        "query_token": query_token,
        "blend_token": blend_token,
        "redis": context.shared.redis,
        "dbpool": context.shared.dbpool,
    }
    ctx.spotify = await client(**client_args)
    request["spotify"] = ctx.spotify
    request["invalidate_client"] = create_client_invalidation(
        str(((), client_args)), CLIENT_CACHE, ctx.spotify
    )
