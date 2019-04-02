import asyncio
from concurrent.futures import CancelledError

from arq import concurrent
from first import first

from .. import logger
from ..exceptions import NoDeviceAvailable
from ..sql import SQL
from .actor import Actor
from .spotify import SpotifyActor
from .volume_fader import VolumeFader


class Player(SpotifyActor):
    def __init__(self, *args, retries=0, polling=0.5, timeout=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.retries = retries
        self.polling = polling
        self.timeout = timeout
        self.volume_fader = None

    async def wait_for_new_device(self, spotify, device_id):
        devices = {d.id: d for d in await spotify.devices()}
        device_mapping = await self.dbpool.fetchval(
            "SELECT device_mapping FROM app_users WHERE id = $1", spotify.user_id
        )
        real_device_id = device_mapping.get(device_id)
        if real_device_id and real_device_id in devices:
            return real_device_id, False

        steps = int(self.timeout / self.polling)
        last_step = steps - 1

        for step in range(steps):
            current_devices = {d.id: d for d in await spotify.devices()}
            new_device_ids = current_devices.keys() - devices.keys()

            if new_device_ids:
                new_device_id = first(new_device_ids)
                return new_device_id, True

            if step != last_step:
                await asyncio.sleep(self.polling)

        device = await spotify.get_device(only_active=False)
        return device and device.id, True

    # pylint: disable=too-many-locals
    @concurrent(Actor.HIGH_QUEUE, unique=True)
    async def play(
        self,
        user_id,
        username,
        device=None,
        artist=None,
        album=None,
        playlist=None,
        tracks=None,
        volume=None,
        fade=None,
        device_id=None,
    ):
        try:
            spotify = await self.spotify(user_id, username)
            if not device:
                device, device_is_new = await self.wait_for_new_device(
                    spotify, device_id
                )
            if not device:
                raise NoDeviceAvailable

            if volume is not None:
                await spotify.volume(volume, device=device)

            logger.info(
                "Starting playback with:\n\tartist=%s\n\talbum=%s\n\tplaylist=%s\n\ttracks=%s",
                artist,
                album,
                playlist,
                tracks,
            )

            await spotify.shuffle(False, device=device)
            await spotify.start_playback(
                device=device,
                artist=artist,
                album=album,
                playlist=playlist,
                tracks=tracks,
                retries=self.retries,
            )
            if fade:
                if not self.volume_fader:
                    self.volume_fader = VolumeFader()
                await self.volume_fader.fade(user_id, username, device=device, **fade)

            if device_id and device_is_new:
                await asyncio.sleep(5)
                playback = await spotify.current_playback()
                if playback and playback.is_playing:
                    await self.dbpool.execute(
                        SQL.map_device, {device_id: playback.device.id}, spotify.user_id
                    )
        except CancelledError:
            pass
