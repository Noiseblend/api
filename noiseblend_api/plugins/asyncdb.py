from spf import SanicPlugin

from .. import DBPOOL
from .priority import PRIORITY


class AsyncDB(SanicPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_registered(self, context, reg, *args, **kwargs):
        context.shared.dbpool = DBPOOL


asyncdb = AsyncDB()


@asyncdb.middleware(priority=PRIORITY.request.add_db_pool, with_context=True)
async def add_db_pool(request, context):
    request["dbpool"] = context.shared.dbpool
