import addict
from spfy.asynch import Spotify

from .db import AppUser
from .sql import SQL


# pylint: disable=too-few-public-methods,too-many-ancestors
class AppSpotify(Spotify):
    def __init__(self, *args, blend=None, **kwargs):
        self.blend = blend
        super().__init__(*args, **kwargs)

    @property
    def app_user(self):
        if not self.user:
            return None
        return AppUser.get(id=self.user.id) or AppUser(id=self.user.id)

    async def fetch_app_user(self, conn=None):
        if not self.user_id:
            return None

        app_user = await conn.fetchrow(SQL.app_user, self.user_id)
        if not app_user:
            return None
        return addict.Dict(dict(app_user))
