from .. import config
from ..overrides import AppSpotify
from .actor import Actor


class SpotifyActor(Actor):
    def __init__(self, *args, **kwargs):
        self.clients = {}
        super().__init__(*args, **kwargs)

    # @async_lru(size=10, evict_callback=close_session)
    async def spotify(self, user_id, username):
        if (user_id, username) in self.clients:
            return self.clients[(user_id, username)]

        spotify = AppSpotify(
            user_id=user_id,
            username=username,
            client_id=config.spotify.client_id,
            client_secret=config.spotify.client_secret,
            redirect_uri=config.spotify.redirect_uri,
            redis=Actor.local_redis or self.redis,
            dbpool=self.dbpool,
        )
        await spotify.authenticate_user_pg(scope=config.spotify.scope)
        self.clients[(user_id, username)] = spotify
        return spotify

    async def shutdown(self):
        await super().shutdown()
        for spotify in self.clients.values():
            if spotify.session:
                await spotify.session.close()
        self.clients.clear()
