# pylint: disable=wrong-import-order
try:
    import asyncio
    import uvloop

    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    print("Using uvloop")
except:
    print("Using asyncio")

import logging
from pathlib import Path

import asyncpg
import sanic
from sanic import Sanic
from sanic_compress import Compress
from spf import SanicPluginsFramework

__version__ = "1.0.0"
APP_NAME = "Noiseblend"

import os  # isort:skip

import kick  # isort:skip

kick.start(APP_NAME)  # isort:skip

from kick import config, logger  # isort:skip
from spfy import config as spfy_config  # isort:skip

try:
    import ujson as json
except:
    import json


ROOT_DIR = Path(__file__).parents[1]
logging.basicConfig()

log_config = sanic.log.LOGGING_CONFIG_DEFAULTS

if os.getenv("DEBUG") == "true":
    print("DEBUG MODE")
    logging.getLogger("sanic_cors").setLevel(logging.DEBUG)
    logger.debug("SPFY Config: %s", json.dumps(spfy_config, indent=2))
    logger.debug("Noiseblend Config: %s", json.dumps(config, indent=2))
if os.getenv("PRODUCTION") == "true":
    del log_config["loggers"]["sanic.error"]
    del log_config["loggers"]["sanic.access"]
    log_config["loggers"]["root"]["level"] = "WARNING"


from .sentry import SentryLogging  # isort:skip


app = Sanic(
    error_handler=SentryLogging(config=config, logger=logger), log_config=log_config
)
Compress(app)
spf = SanicPluginsFramework(app)
app.static("/favicon.ico", str(ROOT_DIR / "favicon.ico"), name="favicon")


async def init_db_connection(conn):
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


loop = asyncio.get_event_loop()
logger.info("Creating DB pool: %s", config.db.pool)
DBPOOL = loop.run_until_complete(
    asyncpg.create_pool(
        **config.db.connection, **config.db.pool, init=init_db_connection
    )
)
