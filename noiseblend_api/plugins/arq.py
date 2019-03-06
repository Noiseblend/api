from sanic.exceptions import InvalidUsage, Unauthorized
from spf import SanicPlugin
from spfy.exceptions import SpotifyDeviceUnavailableException

from ..actors import Blender, Player, Radio, VolumeFader
from ..blends import BLEND_MAPPING
from ..helpers import start_playback
from .priority import PRIORITY


class ARQ(SanicPlugin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def on_registered(self, context, reg, *args, **kwargs):
        context.player = None
        context.volume_fader = None
        context.blender = None
        context.radio = None


arq = ARQ()


@arq.middleware(priority=PRIORITY.request.add_arq_actors, with_context=True)
async def add_arq_actors(request, context):
    if request.method == "OPTIONS":
        return

    if not context.player:
        context.player = Player()

    if not context.volume_fader:
        context.volume_fader = VolumeFader()

    if not context.blender:
        context.blender = Blender()

    if not context.radio:
        context.radio = Radio()

    request["player"] = context.player
    request["volume_fader"] = context.volume_fader
    request["blender"] = context.blender
    request["radio"] = context.radio


# pylint: disable=too-many-locals
@arq.route("/play", methods=["POST"], with_context=True)
async def play(request, context):
    spotify = context.shared.request[id(request)].spotify

    await start_playback(spotify, request.json, context.player, context.volume_fader)

    try:
        playback = await spotify.current_playback(retries=0)
    except SpotifyDeviceUnavailableException:
        playback = None

    return {"playback": playback and playback.to_dict()}


# pylint: disable=redefined-outer-name
@arq.route("/blend", methods=["POST"], with_context=True)
async def blend(request, context):
    spotify = context.shared.request[id(request)].spotify

    blend_id = request.json.get("blend")
    if not blend_id:
        raise InvalidUsage("Missing parameter `blend`")
    if spotify.blend and blend_id != spotify.blend.name:
        raise Unauthorized(f"You're not authorized to play `{blend_id}`")

    return_early = request.json.get("return_early")
    Blend = BLEND_MAPPING[blend_id]

    if return_early:
        request.json.pop("play", None)
        await context.blender.blend(
            spotify.user_id, spotify.username, blend_id, play=True, **request.json
        )
        return Blend.ATTRIBUTES

    tracks, blend_playlist = await context.blender.blend.direct(
        spotify.user_id, spotify.username, blend_id, **request.json
    )
    return {"tracks": tracks, "playlist": blend_playlist}


@arq.route("/fade", methods=["POST"], with_context=True)
async def fade(request, context):
    spotify = context.shared.request[id(request)].spotify
    device = request.json.get("device")
    time_minutes = request.json.get("time_minutes") or 5
    start_volume = request.json.get("start_volume")
    stop_volume = request.json.get("stop_volume")
    direction = request.json.get("direction") or 1

    await context.volume_fader.fade(
        spotify.user_id,
        spotify.username,
        limit=stop_volume,
        start=start_volume,
        seconds=time_minutes * 60,
        step=direction * 3,
        device=device,
    )
    return {}


@arq.route("/radio", methods=["POST"], with_context=True)
async def radio(request, context):
    spotify = context.shared.request[id(request)].spotify

    return_early = request.json.pop("return_early", False)

    if return_early:
        await context.radio.play_radio(
            spotify.user_id, spotify.username, **request.json
        )
    else:
        return await context.radio.play_radio.direct(
            spotify.user_id, spotify.username, **request.json
        )

    return {}
