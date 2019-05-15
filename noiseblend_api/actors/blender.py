import asyncio

from arq import concurrent
from first import first
from sanic.exceptions import NotFound

from .. import logger
from ..blends import BLEND_MAPPING
from ..constants import BLEND_PLAYLIST_DESCRIPTION, BLEND_PLAYLIST_NAME
from .actor import Actor
from .player import Player
from .spotify import SpotifyActor


class Blender(SpotifyActor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.player = None

    # pylint: disable=too-many-locals
    @concurrent(Actor.HIGH_QUEUE, unique=True, expire_seconds=60)
    async def blend(
        self,
        user_id,
        username,
        blend_id,
        device=None,
        volume=None,
        filter_explicit=None,
        fade_params=None,
        device_id=None,
        play=False,
        attributes=None,
        order=None,
        **_,
    ):
        spotify = await self.spotify(user_id, username)
        Blend = BLEND_MAPPING[blend_id]
        blend = Blend(spotify, self.dbpool)
        tracks, user_playlists = await asyncio.gather(
            blend.generate_tracks(
                filter_explicit=filter_explicit, attributes=attributes, order=order
            ),
            spotify.current_user_playlists(limit=50),
        )

        if not tracks:
            raise NotFound(f"No tracks could be generated for blend {blend_id}")

        blend_playlist = first(
            user_playlists, key=lambda p: p.name == BLEND_PLAYLIST_NAME
        )
        if not blend_playlist:
            blend_playlist = await spotify.user_playlist_create(
                spotify.username,
                BLEND_PLAYLIST_NAME,
                description=BLEND_PLAYLIST_DESCRIPTION,
            )
        await spotify.user_playlist_replace_tracks(
            spotify.username, blend_playlist.id, tracks
        )

        if play:
            uri = f"spotify:user:{blend_playlist.owner.id}:playlist:{blend_playlist.id}"
            logger.info(
                "Playing blend %s with id=%s and uri=%s",
                blend_id,
                blend_playlist.id,
                uri,
            )
            if not self.player:
                self.player = Player()
            await self.player.play(
                spotify.user_id,
                spotify.username,
                device=device,
                playlist=uri,
                volume=volume,
                fade=fade_params,
                device_id=device_id,
            )

        return tracks, blend_playlist.to_dict()
