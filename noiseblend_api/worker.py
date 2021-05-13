import asyncio
from uuid import UUID

import addict
import sentry_sdk
from arq import BaseWorker
from arq.utils import RedisSettings
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.sanic import SanicIntegration

from . import DBPOOL, config, logger
from .actors import Blender, Player, Radio, VolumeFader, WeeklyPlaylistFetcher
from .helpers import get_user_dict

REDIS = config.worker.redis or config.redis

sentry_sdk.init(
    integrations=[SanicIntegration(), AioHttpIntegration()], **config.sentry
)


class Worker(BaseWorker):
    redis_settings = RedisSettings(
        pool_maxsize=REDIS.pool.maxsize, pool_minsize=REDIS.pool.minsize, **REDIS.auth
    )
    shadows = [VolumeFader, Player, WeeklyPlaylistFetcher, Blender, Radio]
    max_concurrent_tasks = 10000
    dbpool = DBPOOL

    async def handle_execute_exc(self, started_at, exc, j):
        try:
            await super().handle_execute_exc(started_at, exc, j)
            with sentry_sdk.push_scope() as scope:
                try:
                    spotify = addict.Dict(
                        user_id=UUID(j.args[0]),
                        dbpool=DBPOOL,
                        ensure_db_pool=(lambda: asyncio.sleep(0)),
                    )
                    user_dict = await get_user_dict(spotify, DBPOOL)
                    scope.user = user_dict
                except:
                    pass

                scope.set_tag("job", f"{j.class_name}.{j.func_name}")
                scope.set_extra("id", j.id)
                scope.set_extra("queue", j.queue)
                scope.set_extra("queued_at", j.queued_at)
                scope.set_extra("unique", j.unique)
                scope.set_extra("timeout_seconds", j.timeout_seconds)
                scope.set_extra("args", j.args)
                scope.set_extra("kwargs", j.kwargs)
                scope.set_extra("started_at", started_at)
                sentry_sdk.capture_exception(exc)
        except Exception as e:
            logger.exception(e)
