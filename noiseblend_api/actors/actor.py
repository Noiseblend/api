import asyncio

from arq import Actor as BaseActor
from arq.utils import RedisSettings, create_pool_lenient

from .. import DBPOOL, config

REDIS = config.worker.redis or config.redis


class Actor(BaseActor):
    local_redis = None
    local_redis_settings = RedisSettings(
        pool_maxsize=config.redis.pool.maxsize,
        pool_minsize=config.redis.pool.minsize,
        **config.redis.auth
    )

    def __init__(self, *args, with_redis_pool=False, **kwargs):
        self.redis_settings = RedisSettings(
            pool_maxsize=REDIS.pool.maxsize,
            pool_minsize=REDIS.pool.minsize,
            **REDIS.auth
        )
        self.with_redis_pool = with_redis_pool
        self.dbpool = DBPOOL
        super().__init__(*args, **kwargs)

    async def startup(self):
        if config.worker.redis and not Actor.local_redis and self.with_redis_pool:
            Actor.local_redis = await create_pool_lenient(
                Actor.local_redis_settings, asyncio.get_event_loop()
            )

    async def shutdown(self):
        if Actor.local_redis:
            Actor.local_redis.close()
            await Actor.local_redis.wait_closed()
            Actor.local_redis = None
