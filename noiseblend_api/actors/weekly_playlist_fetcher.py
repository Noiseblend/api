from concurrent.futures import CancelledError

from arq import cron

from ..overrides import AppSpotify
from .actor import Actor


class WeeklyPlaylistFetcher(Actor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @cron(
        weekday="fri", hour=12, minute=0, timeout_seconds=-1, dft_queue=Actor.LOW_QUEUE
    )
    async def fetch(self):
        try:
            spotify = AppSpotify(
                dbpool=self.dbpool, redis=self.local_redis or self.redis
            )
            await spotify.authenticate_server_pg(conn=self.dbpool)
            await spotify.fetch_playlists_pg(conn=self.dbpool)
        except CancelledError:
            pass
