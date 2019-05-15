import asyncio
from concurrent.futures import CancelledError

from arq import concurrent
from first import first
from spfy.constants import VolumeBackend

from ..exceptions import NoDeviceAvailable
from .spotify import SpotifyActor


def cap(val, _min, _max):
    return min(max(val, _min), _max)


class VolumeFader(SpotifyActor):
    def __init__(self, *args, polling=0.5, timeout=10, **kwargs):
        super().__init__(*args, **kwargs)
        self.polling = polling
        self.timeout = timeout

    async def get_playing_device(self, spotify):
        playback, devices = await asyncio.gather(
            spotify.current_playback(), spotify.devices()
        )
        if playback and playback.is_playing:
            return first(devices, key=lambda d: d.is_active)

    async def wait_for_playing_device(self, spotify):
        steps = int(self.timeout / self.polling)
        last_step = steps - 1

        for step in range(steps):
            device = await self.get_playing_device(spotify)

            if device:
                return device

            if step != last_step:
                await asyncio.sleep(self.polling)

    @concurrent(unique=True, timeout_seconds=2500, expire_seconds=60)
    async def fade(
        self,
        user_id,
        username,
        limit=None,
        start=None,
        seconds=60,
        step=3,
        device=None,
        force=False,
    ):
        try:
            spotify = await self.spotify(user_id, username)
            device = device or await self.wait_for_playing_device(spotify)
            if not device:
                raise NoDeviceAvailable

            if start is None:
                start = device.volume_percent

            if limit is None:
                limit = cap((start + 40 if step > 0 else 0), 0, 100)

            if step > 0 and limit <= start:
                limit = cap((start + 40), 0, 100)
            elif step < 0 and limit >= start:
                limit = 0

            if abs(limit - start) <= step * 2:
                return

            if device and not isinstance(device, str):
                device = device.id

            await spotify.fade(
                limit=limit,
                start=start,
                seconds=seconds,
                backend=VolumeBackend.SPOTIFY,
                step=step,
                device=device,
                blocking=True,
                force=force,
            )
        except CancelledError:
            pass
