# pylint: disable=too-many-lines
import asyncio
import signal
from base64 import b64decode
from collections import OrderedDict
from datetime import timedelta
from itertools import chain
from uuid import uuid4

import ujson
from sanic.exceptions import InvalidUsage, Unauthorized
from sanic.response import json
from sanic_cors import CORS
from spfy.asynch import API, TimeRange
from spfy.cache import Artist, Country, Image, User
from spfy.constants import AudioFeature, VolumeBackend
from spfy.exceptions import SpotifyDeviceUnavailableException
from spfy.sql import SQL as SPFY_SQL
from stringcase import camelcase, snakecase

from . import app, config, logger, spf
from .constants import APP_USER_FLAGS
from .db import cap, gentoken
from .helpers import (
    add_image,
    assign_audio_features,
    assign_best_image,
    assign_images,
    get_devices_and_playback,
    get_playlist_description,
    get_tuneable_attributes,
    get_user_dict,
    plural,
    seconds_until_next_playlist_fetch,
    start_playback,
    user_disliked_artists,
    with_cache,
    with_cache_invalidation,
)
from .plugins import (
    arq,
    asyncdb,
    auth,
    cache_control,
    camelcase_response,
    cors,
    snakecase_request,
    spotify_client,
)
from .sql import SQL
from .transform import transform_keys
from .worker import Worker


def oauth_error(error_type, description, code=400):
    return json({"error": error_type, "error_description": description}, status=code)


@app.get("/oauth-code")
async def oauth_code(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    code = str(uuid4())
    await conn.execute(
        "UPDATE app_users SET oauth_code = $1 WHERE id = $2", code, spotify.user_id
    )
    return {"code": code}


async def oauth_check(request):
    if not request.token:
        return oauth_error("invalid_request", "Missing authentication header")

    auth_type, credentials = request.token.split(" ")
    if auth_type.lower() != config.alexa.auth_type:
        return oauth_error("invalid_request", f"Bad authentication type: {auth_type}")

    try:
        client_id, client_secret = b64decode(credentials).decode().split(":")
        if (
            client_id != config.alexa.client_id
            or client_secret != config.alexa.client_secret
        ):
            return oauth_error("invalid_client", "Bad credentials", code=401)
    except:
        return oauth_error("invalid_client", "Bad credentials", code=401)

    return None


@app.post("/oauth-token")
async def oauth_token(request):
    conn = request["dbpool"]

    grant_type = request.form.get("grant_type")
    code = request.form.get("code")
    token = request.form.get("refresh_token")

    error = None
    if grant_type not in ("refresh_token", "authorization_code"):
        error = oauth_error(
            "unsupported_grant_type", f"Unsupported grant type {grant_type}"
        )
    elif not token and grant_type == "refresh_token":
        error = oauth_error("invalid_request", "Missing parameter `refresh_token`")
    elif not code and grant_type == "authorization_code":
        error = oauth_error("invalid_request", "Missing parameter `code`")
    elif not code and not token:
        error = oauth_error(
            "invalid_request", "Missing parameter `code` or `refresh_token`"
        )

    if error:
        return error

    oauth_error_response = await oauth_check(request)
    if oauth_error_response:
        return oauth_error_response

    if code:
        user = await conn.fetchrow(SQL.app_user_by_code, code)
        if not user:
            return oauth_error("invalid_grant", "Invalid code")
    else:
        user = await conn.fetchrow(SQL.app_user_by_refresh_token, token)
        if not user:
            return oauth_error("invalid_grant", "Invalid refresh token")

    token = await conn.fetchrow(SQL.insert_token, user["id"])
    resp = {
        "access_token": str(token["id"]),
        "token_type": "Bearer",
        "expires_in": 3600,
    }
    if code:
        resp["refresh_token"] = str(user["oauth_refresh_token"])
    return json(resp, headers={"Cache-Control": "no-store", "Pragma": "no-cache"})


@app.get("/blend-token")
async def blend_token(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    blend = request.args.get("blend")
    if not blend:
        raise InvalidUsage("Missing parameter `blend`")

    token = await conn.fetchval(SQL.blend_token, spotify.user_id, blend)
    if not token:
        token = await conn.fetchval(
            SQL.upsert_blend, spotify.user_id, blend, gentoken()
        )

    return with_cache(
        {"token": token}, without_etag=True, max_age=timedelta(days=30).total_seconds()
    )


@app.get("/is-authenticated")
async def is_authenticated(request):
    spotify = request["spotify"]
    return {"authenticated": spotify.is_authenticated}


@app.get("/authorization-url")
async def authorization_url(request):
    spotify = request["spotify"]
    url, _ = spotify.session.authorization_url(API.AUTHORIZE.value, nosignup="true")
    return {"authorization_url": url}


@app.get("/authenticate")
async def authenticate(request):
    conn = request["dbpool"]

    code = request.args.get("code")
    state = request.args.get("state")
    if not code:
        raise InvalidUsage("Missing parameter `code`")

    if not state:
        raise InvalidUsage("Missing parameter `state`")

    spotify = request["spotify"]
    user = await spotify.authenticate_user_pg(
        code=code, state=state, scope=config.spotify.scope
    )
    # pylint: disable=unused-variable
    app_user = await conn.fetchrow(SQL.upsert_app_user, user.id, bool(user.email))
    if not app_user:
        raise Unauthorized("Authentication error")
    user_dict = await get_user_dict(spotify, conn)

    await request["invalidate_client"]()
    return with_cache_invalidation(
        user_dict, method="GET", path="/me", user_id=spotify.user_id
    )


@app.get("/logout")
async def logout(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    if not spotify.user_id:
        return {}

    del spotify.session.access_token
    await conn.execute("UPDATE users SET token = '{}' WHERE id = $1", spotify.user_id)
    await conn.execute(
        "UPDATE app_users SET auth_token = $2 WHERE id = $1", spotify.user_id, uuid4()
    )

    await request["invalidate_client"]()
    return with_cache_invalidation(
        {}, method="GET", path="/me", user_id=spotify.user_id
    )


@app.get("/reset-token")
async def reset_token(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    if not spotify.user_id:
        return {}

    token = uuid4()
    await conn.execute(
        "UPDATE app_users SET long_lived_token = $2 WHERE id = $1",
        spotify.user_id,
        token,
    )

    return {"token": token}


@app.get("/me")
async def me(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    return with_cache(await get_user_dict(spotify, conn))


@app.get("/fetch-dislikes")
async def fetch_dislikes(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    _type = request.args.get("type")
    if not _type:
        raise InvalidUsage("Missing parameter `type`")

    keys = {"artists", "genres", "countries", "cities"}
    key_suffix = {k: k[:2].upper() for k in keys}
    singular = {
        "artists": "artist",
        "genres": "genre",
        "countries": "country",
        "cities": "city",
    }

    if _type not in keys and _type != "all":
        raise InvalidUsage(
            f'Wrong value. Pass at least one of `{", ".join([*keys, "all"])}`'
        )

    dislikes = {}
    if _type == "all":
        dislike_rows = [
            d[0] for d in await conn.fetch(SPFY_SQL.user_dislikes, spotify.user_id)
        ]

        for dislike_type, suffix in key_suffix.items():
            dislikes[dislike_type] = [
                dislike[:-3] for dislike in dislike_rows if dislike[-2:] == suffix
            ]
    else:
        dislike_rows = await conn.fetch(
            f"""SELECT {singular[_type]}
            FROM {singular[_type]}_haters
            WHERE "user" = $1""",
            spotify.user_id,
        )
        dislikes[_type] = [d[0] for d in dislike_rows]

    if dislikes.get("artists"):
        dislikes["artists"] = [
            a.to_dict() for a in await spotify.artists(dislikes["artists"])
        ]
        for artist in dislikes["artists"]:
            if artist["images"]:
                artist["image"] = Artist.get_optimal_image(
                    artist["images"], width=64, height=64
                )

    async def get_smallest_images(key, values):
        images = await conn.fetch(SQL.smallest_image.format(key), values)
        images = {r[key]: dict(r).pop(key) for r in images}
        return images

    if dislikes.get("genres"):
        images = await get_smallest_images("genre", dislikes["genres"])
        dislikes["genres"] = [
            {"name": genre, "image": images.get(genre)} for genre in dislikes["genres"]
        ]

    if dislikes.get("cities"):
        images = await get_smallest_images("city", dislikes["cities"])
        dislikes["cities"] = [
            {"name": city, "image": images.get(city)} for city in dislikes["cities"]
        ]

    if dislikes.get("countries"):
        images = await get_smallest_images("country", dislikes["countries"])
        dislikes["countries"] = [
            {"code": c, "name": Country.get_iso_country(c).name, "image": images.get(c)}
            for c in dislikes["countries"]
        ]

    if _type != "all":
        return with_cache(dislikes[_type])
    return with_cache(dislikes)


@app.post("/confirm-email")
async def confirm_email(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    email_token = request.json.get("token")
    if email_token is None:
        raise Unauthorized("Token is null")

    user_email_token = await conn.fetchval(
        "SELECT email_token FROM app_users WHERE id = $1", spotify.user_id
    )
    if user_email_token != email_token:
        raise Unauthorized("Token is invalid")

    await conn.execute(
        "UPDATE app_users SET email_confirmed=TRUE WHERE id = $1", spotify.user_id
    )
    user_dict = await get_user_dict(spotify, conn)

    return with_cache_invalidation(
        user_dict, method="GET", path="/me", user_id=spotify.user_id
    )


@app.put("/user-details")
async def change_user_details(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    artist_time_range = request.json.get("artist_time_range")
    genre_time_range = request.json.get("genre_time_range")
    preferred_country = request.json.get("preferred_country")
    # email = request.json.get("email")

    app_user_fields = OrderedDict()
    user_fields = OrderedDict()

    if artist_time_range:
        app_user_fields["artist_time_range"] = TimeRange(artist_time_range).value
    if genre_time_range:
        app_user_fields["genre_time_range"] = TimeRange(genre_time_range).value
    if preferred_country:
        user_fields["preferred_country"] = preferred_country

    flags = {
        param: value
        for param, value in request.json.items()
        if param in APP_USER_FLAGS and value is not None
    }
    app_user_fields = {**app_user_fields, **flags}
    if app_user_fields:
        field_str = " ".join(
            f"{field} = ${i + 2}" for i, field in enumerate(app_user_fields.keys())
        )
        await conn.execute(
            f"UPDATE app_users SET {field_str} WHERE id = $1",
            spotify.user_id,
            *app_user_fields.values(),
        )
    if user_fields:
        field_str = " ".join(
            f"{field} = ${i + 2}" for i, field in enumerate(user_fields.keys())
        )
        await conn.execute(
            f"UPDATE users SET {field_str} WHERE id = $1",
            spotify.user_id,
            *user_fields.values(),
        )
    user_dict = await get_user_dict(spotify, conn)

    return with_cache_invalidation(
        user_dict, method="GET", path="/me", user_id=spotify.user_id
    )


def parse_params(request):
    time_range = request.args.get("time_range")
    ignore = request.args.get("ignore")
    if not ignore:
        ignore = []
    else:
        ignore = ignore.split(",")
    limit = int(request.args.get("limit") or 3)
    image_width = request.args.get("image_width")
    image_height = request.args.get("image_height")
    _all = request.args.get("all") == "true"

    if image_width:
        image_width = int(image_width)
    if image_height:
        image_height = int(image_height)
    return time_range, ignore, limit, image_width, image_height, _all


@app.get("/artists")
async def top_artists(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    time_range, ignore, limit, image_width, image_height, _all = parse_params(request)
    time_range_arg = time_range

    if not _all:
        if not time_range:
            time_range = await conn.fetchval(
                SQL.user_artist_time_range, spotify.user_id
            )
        time_ranges = [time_range or TimeRange.MEDIUM_TERM]
    else:
        time_ranges = list(TimeRange)

    dislikes = await spotify.get_dislikes_for_filtering()
    artists = await asyncio.gather(
        *[
            spotify.top_artists_pg(
                time_range=tr,
                ignore=ignore,
                dislikes=dislikes,
                limit=limit if not _all else None,
            )
            for tr in time_ranges
        ]
    )

    def get_artists(results):
        artist_list = []
        for artist in results:
            image = None
            if artist.images:
                image = Artist.get_optimal_image(
                    artist.images, width=image_width, height=image_height
                )
            if image is None:
                artist_list.append(artist.to_dict())
                continue

            artist_dict = {"image": {"url": image.url}, **artist.to_dict()}
            artist_list.append(artist_dict)
        return artist_list

    artists = [get_artists(a) for a in artists]
    if _all:
        artists = {tr.value.lower(): a for tr, a in zip(time_ranges, artists)}
        if time_range_arg:
            return with_cache(artists)
        return artists
    return artists[0]


# pylint: disable=too-many-locals
@app.get("/genres")
async def top_genres(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    time_range, ignore, limit, image_width, image_height, _all = parse_params(request)
    time_range_arg = time_range

    async def get_genres(playlists):
        genres = {p["genre"] for p in playlists}
        genres = [
            {
                "playlists": [dict(p) for p in playlists if p["genre"] == genre],
                "name": genre,
            }
            for genre in genres
        ]

        try:
            await assign_images(
                genres, "name", "genre", image_width, image_height, conn=conn
            )
        except Exception as exc:
            logger.error("Error fetching images:")
            logger.exception(exc)

        for genre in genres:
            image = genre.get("image") or genre["playlists"][0]["image"]
            genre["image"] = {
                **image,
                "unsplash": Image.unsplash_credits(
                    image["unsplash_user_fullname"], image["unsplash_user_username"]
                ),
            }
        return genres

    query_args = {
        "playlist_query": SQL.genre_playlists,
        "singular": "genre",
        "plural": "genres",
    }

    if not _all:
        if not time_range:
            time_range = await conn.fetchval(SQL.user_genre_time_range, spotify.user_id)

        query = SQL.item_playlists.format(limit=limit, **query_args)
        time_ranges = [time_range or TimeRange.MEDIUM_TERM]
    else:
        query = SQL.all_item_playlists.format(**query_args)
        time_ranges = list(TimeRange)

    dislikes = await spotify.get_dislikes_for_filtering(conn)
    genre_requests = [
        spotify.top_genres_pg(
            time_range=tr, ignore=ignore, conn=conn, dislikes=dislikes
        )
        for tr in time_ranges
    ]
    genres = await asyncio.gather(*genre_requests)
    if not any(genres):
        return [] if not _all else {}

    playlists = [await conn.fetch(query, g, image_width, image_height) for g in genres]
    genres = await asyncio.gather(*[get_genres(p) for p in playlists])

    if _all:
        genres = {tr.value.lower(): g for tr, g in zip(time_ranges, genres)}
        if time_range_arg:
            return with_cache(genres)
        return genres
    return genres[0]


@app.get("/countries")
async def fetch_countries(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    _, ignore, limit, image_width, image_height, _all = parse_params(request)

    query_args = {
        "playlist_query": SQL.country_playlists_ignore,
        "singular": "country",
        "plural": "countries",
    }
    if not _all:
        query = SQL.item_playlists.format(limit=limit, **query_args)
    else:
        query = SQL.all_item_playlists.format(**query_args)

    playlists = await conn.fetch(
        query, ignore, image_width, image_height, spotify.user_id
    )
    countries = {p["country"] for p in playlists}
    countries = [
        {
            "playlists": [dict(p) for p in playlists if p["country"] == country],
            "code": country,
            "name": Country.get_iso_country(country).name,
        }
        for country in countries
    ]

    try:
        await assign_images(
            countries, "code", "country", image_width, image_height, conn=conn
        )
    except Exception as exc:
        logger.error("Error fetching images:")
        logger.exception(exc)

    for country in countries:
        image = country.get("image") or country["playlists"][0]["image"]
        country["image"] = {
            **image,
            "unsplash": Image.unsplash_credits(
                image["unsplash_user_fullname"], image["unsplash_user_username"]
            ),
        }

    if _all:
        return with_cache(countries)
    return countries


# pylint: disable=too-many-locals
@app.get("/cities")
async def fetch_cities(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    with_countries = request.args.get("with_countries") == "true"
    country = request.args.get("country")
    country_arg = country
    _, ignore, limit, image_width, image_height, _all = parse_params(request)

    if not country:
        user_country, preferred_country = await conn.fetchrow(
            SQL.user_country, spotify.user_id
        )
        country = preferred_country or user_country

    query_args = {
        "playlist_query": SQL.city_playlists_ignore,
        "singular": "city",
        "plural": "cities",
    }
    if not _all:
        query = SQL.item_playlists.format(limit=limit, **query_args)
    else:
        query = SQL.all_item_playlists.format(**query_args)

    playlists = await conn.fetch(
        query, ignore, image_width, image_height, country, spotify.user_id
    )
    cities = [
        {"playlist": dict(playlist), "name": playlist["city"]} for playlist in playlists
    ]
    if with_countries:
        countries = [
            dict(c) for c in await conn.fetch("SELECT * FROM countries ORDER BY name")
        ]

    try:
        await assign_images(
            cities, "name", "city", image_width, image_height, conn=conn
        )
    except Exception as exc:
        logger.error("Error fetching images:")
        logger.exception(exc)

    for city in cities:
        image = city.get("image") or city["playlist"]["image"]
        city["image"] = {
            **image,
            "unsplash": Image.unsplash_credits(
                image["unsplash_user_fullname"], image["unsplash_user_username"]
            ),
        }

    if with_countries:
        response = {"countries": countries, "cities": cities}
    else:
        response = cities

    if _all and country_arg:
        return with_cache(response)
    return response


@app.post("/recommendations")
async def recommendations(request):
    spotify = request["spotify"]
    artists = request.json.get("seed_artists", [])
    genres = request.json.get("seed_genres", [])
    tracks = request.json.get("seed_tracks", [])
    limit = request.json.get("limit", 50)
    tuneable_attributes = request.json.get("tuneable_attributes")
    with_tuneable_attributes = request.json.get("with_tuneable_attributes")
    tuneable_attributes = get_tuneable_attributes(tuneable_attributes)

    tracks = await spotify.recommendations(
        seed_artists=artists,
        seed_genres=genres,
        seed_tracks=tracks,
        limit=limit,
        **tuneable_attributes,
    )

    if with_tuneable_attributes:
        tracks["tracks"] = await assign_audio_features(spotify, tracks["tracks"])

    return [t.to_dict() for t in tracks]


@app.get("/playlist")
async def fetch_playlist(request):
    spotify = request["spotify"]
    user = request.args.get("user")
    if not user:
        raise InvalidUsage("Missing parameter `user`")

    playlist_id = request.args.get("id")
    if not playlist_id:
        raise InvalidUsage("Missing parameter `id`")

    limit = int(request.args.get("limit", 100))
    offset = int(request.args.get("offset", 0))
    only_tracks = request.args.get("only_tracks") == "true"
    with_tuneable_attributes = request.args.get("with_tuneable_attributes") == "true"

    playlist = {}
    if not only_tracks:
        playlist = (
            await spotify.user_playlist(user, playlist_id=playlist_id)
        ).to_dict()
    if offset + limit > 100:
        playlist["tracks"] = await spotify.user_playlist_tracks(
            user, playlist_id=playlist_id, limit=limit, offset=offset
        )
    else:
        if "tracks" in playlist:
            playlist["tracks"]["items"] = playlist["tracks"]["items"][
                offset : offset + limit
            ]
        else:
            playlist["tracks"] = await spotify.user_playlist_tracks(
                user, playlist_id=playlist_id, limit=limit, offset=offset
            )

    if with_tuneable_attributes:
        playlist = await assign_audio_features(spotify, playlist=playlist)

    if user in spotify.USER_LIST:
        return with_cache(
            playlist,
            without_user_id=True,
            without_etag=True,
            max_age=seconds_until_next_playlist_fetch(),
        )
    return playlist


@app.get("/playback")
async def get_playback(request):
    spotify = request["spotify"]
    playback = await spotify.current_playback(retries=0)
    return playback and playback.to_dict()


@app.get("/devices")
async def get_devices(request):
    spotify = request["spotify"]
    with_playback = request.args.get("playback", "").lower() not in {"false", "1", "no"}
    if with_playback:
        return await get_devices_and_playback(spotify)

    devices = await spotify.devices()
    return list(devices)


@app.post("/save-playlist")
async def save_playlist(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    name = request.json.get("name")
    if not name:
        raise InvalidUsage("Missing parameter `name`")

    tracks = request.json.get("tracks")
    if not tracks:
        raise InvalidUsage("Missing parameter `tracks`")

    image = request.json.get("image")
    artists = request.json.get("artists")
    filter_explicit = request.json.get("filter_explicit")

    description = ""
    if artists:
        if len(artists) > 1:
            artist_string = f"{', '.join(artists[:-1])} & {artists[-1]}"
        else:
            artist_string = artists[0]
        description = f"Recommended songs based on {artist_string}."
    playlist = await spotify.user_playlist_create(
        spotify.username, name, description=description
    )

    if filter_explicit:
        tracks = await asyncio.gather(
            *[spotify.tracks(tracks[i : i + 50]) for i in range(0, len(tracks), 50)]
        )
        tracks = chain.from_iterable(tracks)
        tracks = [t.id for t in tracks if not t.explicit]

    await spotify.user_playlist_replace_tracks(spotify.username, playlist.id, tracks)
    if image:
        await add_image(spotify, playlist.id, image, conn=conn)

    playlist = await spotify.user_playlist(spotify.username, playlist.id)
    playlist = await assign_audio_features(spotify, playlist=playlist)

    return playlist.to_dict()


@app.get("/audio-features")
async def fetch_audio_features(request):
    spotify = request["spotify"]
    owner_id = request.args.get("owner_id")
    playlist_id = request.args.get("playlist_id")
    tracks = request.args.get("tracks")
    request_ok = bool((playlist_id and owner_id) or tracks)
    if not request_ok:
        raise InvalidUsage(
            "Missing parameter (`playlist_id` and `owner_id`) or `tracks`"
        )

    if tracks:
        tracks = tracks.split(",")

    if playlist_id:
        fields = "total,limit,href,next,items(track(id))"
        tracks = await spotify.user_playlist_tracks(
            owner_id, playlist_id, fields=fields
        )
        tracks = await tracks.all()
        tracks = [t.track.id for t in tracks if t.track]
    audio_features = await spotify.audio_features(tracks=tracks)

    audio_feature_keys = {f.value for f in AudioFeature}
    audio_features = {
        a.id: {k: v for k, v in a.items() if k in audio_feature_keys}
        for a in audio_features
        if a
    }

    return with_cache(
        audio_features,
        without_user_id=True,
        without_etag=True,
        max_age=int(timedelta(days=7).total_seconds()),
    )


@app.post("/clone-playlist")
async def clone_playlist(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    playlist_id = request.json.get("id")
    if not playlist_id:
        raise InvalidUsage("Missing parameter `id`")

    owner_id = request.json.get("owner_id", spotify.username)
    name = request.json.get("name")
    order = request.json.get("order")
    image = request.json.get("image")
    fields = "total,limit,href,next,items(track(id,is_playable))"
    tracks = await spotify.user_playlist_tracks(owner_id, playlist_id, fields=fields)
    tracks = await tracks.all()
    if order:
        tracks = await spotify.order_by(
            order, [t.track.id for t in tracks if t.track and t.track.is_playable]
        )
    tracks = [
        t if isinstance(t, str) else (t.track.uri or t.track.id or t.uri or t.id)
        for t in tracks
    ]
    if not name:
        source_playlist = await spotify.user_playlist(owner_id, playlist_id)
        name = source_playlist.name
    description = await get_playlist_description(playlist_id, conn=conn)
    playlist = await spotify.user_playlist_create(
        spotify.username, name, description=description
    )
    await spotify.user_playlist_replace_tracks(spotify.username, playlist.id, tracks)
    if image:
        await add_image(spotify, playlist.id, image, conn=conn)

    playlist = await spotify.user_playlist(spotify.username, playlist.id)
    playlist = await assign_audio_features(spotify, playlist=playlist)

    return playlist.to_dict()


# pylint: disable=too-many-locals
@app.post("/filter-playlist")
async def filter_playlist(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    playlist_id = request.json.get("id")
    if not playlist_id:
        raise InvalidUsage("Missing parameter `id`")

    owner_id = request.json.get("owner_id", spotify.username)
    source_playlist = await spotify.user_playlist(owner_id, playlist_id)

    name = request.json.get("name") or source_playlist.name
    order = request.json.get("order")
    image = request.json.get("image")

    filter_explicit = request.json.get("filter_explicit")
    filter_dislikes = request.json.get("filter_dislikes")

    fields = "total,limit,href,next,items(track(id,is_playable,explicit,artists))"
    tracks = await spotify.user_playlist_tracks(owner_id, playlist_id, fields=fields)
    tracks = await tracks.all()

    if filter_explicit:
        tracks = [t for t in tracks if not t.track.explicit]
    if filter_dislikes:
        disliked_artists = set(await user_disliked_artists(spotify, conn=conn))
        tracks = [
            t
            for t in tracks
            if not set(a.id for a in t.track.artists) & disliked_artists
        ]

    if order:
        tracks = await spotify.order_by(
            order, [t.track.id for t in tracks if t.track and t.track.is_playable]
        )
    tracks = [
        t if isinstance(t, str) else (t.track.uri or t.track.id or t.uri or t.id)
        for t in tracks
    ]

    playlist = await spotify.user_playlist_create(
        spotify.username, name, description=source_playlist.description
    )
    await spotify.user_playlist_replace_tracks(spotify.username, playlist.id, tracks)

    if not image and source_playlist.images:
        image = source_playlist.images[0].url

    if image:
        await add_image(spotify, playlist.id, image, conn=conn)

    playlist = await spotify.user_playlist(spotify.username, playlist.id)
    playlist = await assign_audio_features(spotify, playlist=playlist)

    return playlist.to_dict()


@app.post("/rename-playlist")
async def rename_playlist(request):
    spotify = request["spotify"]
    playlist_id = request.json.get("id")
    if not playlist_id:
        raise InvalidUsage("Missing parameter `id`")

    name = request.json.get("name")
    if not name:
        raise InvalidUsage("Missing parameter `name`")

    await spotify.user_playlist_change_details(spotify.username, playlist_id, name)
    return {"renamed": True}


@app.post("/reorder-playlist")
async def reorder_playlist(request):
    spotify = request["spotify"]
    playlist_id = request.json.get("id")
    if not playlist_id:
        raise InvalidUsage("Missing parameter `id`")

    order = request.json.get("order")
    if not order:
        raise InvalidUsage("Missing parameter `order`")

    order = {feature: value for feature, value in order.items() if value}
    fields = "total,limit,href,next,items(track(id,is_playable))"
    tracks = await spotify.user_playlist_tracks(
        spotify.username, playlist_id, fields=fields
    )
    tracks = await tracks.all()
    tracks = await spotify.order_by(
        order, [t.track.id for t in tracks if t.track and t.track.is_playable]
    )
    await spotify.user_playlist_replace_tracks(spotify.username, playlist_id, tracks)
    return {"reordered": True}


@app.post("/replace-tracks")
async def replace_tracks(request):
    spotify = request["spotify"]
    playlist_id = request.json.get("id")
    if not playlist_id:
        raise InvalidUsage("Missing parameter `id`")

    tracks = request.json.get("tracks")
    if not tracks:
        raise InvalidUsage("Missing parameter `tracks`")

    order = request.json.get("order")
    if order:
        tracks = await spotify.order_by(order, tracks)
    await spotify.user_playlist_replace_tracks(spotify.username, playlist_id, tracks)
    return {"replaced": True}


@app.post("/pause")
async def pause(request):
    spotify = request["spotify"]

    [paused, playback] = await asyncio.gather(
        await spotify.pause_playback(retries=0),
        await spotify.current_playback(retries=0),
        return_exceptions=True,
    )

    reason = None
    if isinstance(paused, SpotifyDeviceUnavailableException):
        reason = "DEVICE_UNAVAILABLE"
    if isinstance(playback, SpotifyDeviceUnavailableException) or not playback:
        reason = "DEVICE_UNAVAILABLE"
        playback = {"is_playing": True}
    else:
        playback = playback.to_dict()

    return {"playback": playback, "reason": reason}


@app.post("/next-track")
async def next_track(request):
    spotify = request["spotify"]

    try:
        await spotify.next_track(retries=0)
    except SpotifyDeviceUnavailableException:
        return {"worked": False, "reason": "DEVICE_UNAVAILABLE"}

    return {"worked": True}


@app.post("/previous-track")
async def previous_track(request):
    spotify = request["spotify"]

    try:
        await spotify.previous_track(retries=0)
    except SpotifyDeviceUnavailableException:
        return {"worked": False, "reason": "DEVICE_UNAVAILABLE"}

    return {"worked": True}


@app.get("/artist-details")
async def artist_details(request):
    spotify = request["spotify"]
    ids = request.args.get("ids")
    if not ids:
        raise InvalidUsage("Missing parameter `ids`")
    ids = ids.split(",")

    artists = await spotify.artists(ids)
    return with_cache(
        [a.to_dict() for a in artists if a],
        without_user_id=True,
        without_etag=True,
        max_age=int(timedelta(days=2).total_seconds()),
    )


@app.post("/dislike")
async def dislike(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    skip = request.json.get("skip", False)
    keys = {"artist", "genre", "country", "city"}
    plurals = {plural(k): k for k in keys}
    valid_keys = keys & set(request.json.keys())
    valid_key_plurals = plurals.keys() & set(request.json.keys())
    if not valid_keys or valid_key_plurals:
        raise InvalidUsage(
            f'Missing parameter. Pass at least one of `{", ".join(keys | plurals.keys())}`'
        )

    values = {k: request.json[k] for k in valid_keys}
    coros = [User.dislike_pg(conn, spotify, **values)]

    for plural_key in valid_key_plurals:
        key = plurals[plural_key]
        ids = request.json[plural_key]
        coros += [User.dislike_pg(conn, spotify, **{key: value}) for value in ids]

    if skip:
        coros.append(spotify.next_track(retries=0))

    await asyncio.gather(*coros)

    invalidate_endpoints = [
        {"method": "GET", "user_id": spotify.user_id, "path": f"/{plural(key)}"}
        for key in valid_keys
    ]
    invalidate_endpoints.append(
        {"method": "GET", "user_id": spotify.user_id, "path": "/fetch-dislikes"}
    )
    return with_cache_invalidation({"disliked": True}, endpoints=invalidate_endpoints)


@app.post("/save-track")
async def save_track(request):
    spotify = request["spotify"]
    track = request.json.get("track")
    if not track:
        playback = await spotify.current_playback(retries=0)
        track = playback.item.id
    await spotify.current_user_saved_tracks_add(tracks=[track])
    return {}


@app.post("/like")
async def like(request):
    spotify = request["spotify"]
    conn = request["dbpool"]

    keys = {"artist", "genre", "country", "city"}
    valid_keys = keys & set(request.json.keys())
    if not valid_keys:
        raise InvalidUsage(
            f'Missing parameter. Pass at least one of `{", ".join(keys)}`'
        )

    values = {k: request.json[k] for k in valid_keys}
    await User.like_pg(conn, spotify.user_id, **values)

    invalidate_endpoints = [
        {"method": "GET", "user_id": spotify.user_id, "path": f"/{plural(key)}"}
        for key in valid_keys
    ]
    invalidate_endpoints.append(
        {"method": "GET", "user_id": spotify.user_id, "path": "/fetch-dislikes"}
    )
    return with_cache_invalidation({"liked": True}, endpoints=invalidate_endpoints)


@app.get("/playlists")
async def fetch_playlists(request):
    conn = request["dbpool"]

    keys = {"genre", "country", "city", "genres", "countries"}
    args = set(request.args.keys())
    if not keys & args:
        raise InvalidUsage(
            f'Missing parameter. Pass at least one of `{", ".join(keys)}`'
        )

    playlists = []

    if "genre" in args:
        genre = request.args.get("genre")
        playlists = await conn.fetch("SELECT * FROM playlists WHERE genre = $1", genre)
    elif "genres" in args:
        genres = request.args.get("genres").split(",")
        playlists = await conn.fetch(SQL.genre_playlists, genres)
    elif "countries" in args:
        countries = request.args.get("countries").split(",")
        playlists = await conn.fetch(SQL.country_playlists, countries)
    elif "country" in args:
        country = request.args.get("country")
        playlists = await conn.fetch(SQL.country_playlists, [country])
    elif "city" in args:
        city = request.args.get("city")
        playlists = await conn.fetch(SQL.city_playlists, [city])

    return with_cache(
        playlists,
        without_user_id=True,
        without_etag=True,
        max_age=seconds_until_next_playlist_fetch(),
    )


@app.post("/search")
async def search(request):
    spotify = request["spotify"]
    query = request.json.get("query")
    if not query:
        raise InvalidUsage("Missing parameter `query`")

    _type = request.json.get("type")
    if not _type:
        raise InvalidUsage("Missing parameter `type`")

    limit = cap(request.json.get("limit") or 1, 1, 10)
    width = request.json.get("image_width")
    height = request.json.get("image_height")
    search_func = getattr(spotify, f"search_{_type}")
    items = await search_func(query, limit)
    items = [assign_best_image(item, width=width, height=height) for item in items]
    return items


@app.post("/volume")
async def set_volume(request):
    spotify = request["spotify"]
    device = request.json.get("device")
    volume = request.json.get("volume")
    if volume is None:
        raise InvalidUsage("Missing parameter `volume`")

    volume = cap(volume, 0, 100)
    new_volume = await spotify.change_volume(
        to=volume, backend=VolumeBackend.SPOTIFY, device=device
    )
    return {"volume": new_volume}


@app.get("/volume")
async def get_volume(request):
    spotify = request["spotify"]
    device = request.args.get("device")

    volume = await spotify.volume(device=device)
    return {"volume": volume}


async def recv_json(ws):
    data = await ws.recv()
    if not data:
        return None

    data = ujson.loads(data)
    if not data:
        return None
    data = transform_keys(data, snakecase)
    return data


@app.websocket("/playlist-tuner")
async def playlist_tuner(request, ws):
    spotify = request["spotify"]

    async def send_recommendations(data):
        try:
            artists = data.get("seed_artists", [])
            genres = data.get("seed_genres", [])
            tracks = data.get("seed_tracks", [])
            limit = data.get("limit", 50)

            with_tuneable_attributes = data.get("with_tuneable_attributes", False)
            tuneable_attributes = data.get("tuneable_attributes", None)
            tuneable_attributes = get_tuneable_attributes(tuneable_attributes)

            tracks = await spotify.recommendations(
                seed_artists=artists,
                seed_genres=genres,
                seed_tracks=tracks,
                limit=limit,
                **tuneable_attributes,
            )

            if with_tuneable_attributes:
                tracks["tracks"] = await assign_audio_features(
                    spotify, tracks["tracks"]
                )

            data = [t.to_dict() for t in tracks]
            data = transform_keys(data, camelcase)
            await ws.send(ujson.dumps(data))

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            await app.error_handler.default(request, exc)
            logger.exception(exc)

    sender_task = None
    while True:
        data = await recv_json(ws)
        if not data:
            continue

        if sender_task and not sender_task.done() and not sender_task.cancelled():
            sender_task.cancel()

        sender_task = asyncio.create_task(send_recommendations(data))


@app.websocket("/playback-controller")
async def playback_controller(request, ws):
    spotify = request["spotify"]

    async def send_playback():
        await asyncio.sleep(0.5)
        data = await get_devices_and_playback(spotify)
        data = transform_keys(data, camelcase)
        await ws.send(ujson.dumps(data))

    async def handle_action(action):
        try:
            if action == "PLAY":
                await start_playback(
                    spotify, data, request["player"], request["volume_fader"]
                )
            elif action == "PAUSE":
                await spotify.pause_playback(retries=0)
            elif action == "NEXT_TRACK":
                await spotify.next_track(retries=0)
            elif action == "PREVIOUS_TRACK":
                await spotify.previous_track(retries=0)
        except SpotifyDeviceUnavailableException:
            pass
        else:
            asyncio.create_task(send_playback())

    while True:
        data = await recv_json(ws)
        if not data:
            continue

        action = data.pop("action", None)
        if not action:
            continue

        asyncio.create_task(handle_action(action))


@app.websocket("/devices-watcher/<polling:int>")
async def devices_watcher(request, ws, polling=30):
    spotify = request["spotify"]
    polling = [polling]

    async def polling_updater():
        while True:
            try:
                data = await ws.recv()
            except:
                break

            if data:
                try:
                    new_polling = int(data)
                    if new_polling != polling[0]:
                        polling[0] = max(new_polling, 2)
                except:
                    pass

    asyncio.create_task(polling_updater())

    while True:
        data = await get_devices_and_playback(spotify)
        data = transform_keys(data, camelcase)
        await ws.send(ujson.dumps(data))

        old_polling = polling[0]
        for _ in range(0, old_polling, 2):
            await asyncio.sleep(2)
            if polling[0] != old_polling:
                break


if config.api.cors:
    spf.register_plugin(
        CORS(), origins=config.api.allow_origins, automatic_options=True
    )
else:
    spf.register_plugin(cors)

spf.register_plugin(arq)
spf.register_plugin(
    auth,
    unauthorized_routes=[
        "/oauth-token",
        "/authorization-url",
        "/is-authenticated",
        "/authenticate",
    ],
)
spf.register_plugin(camelcase_response)
spf.register_plugin(snakecase_request)
spf.register_plugin(spotify_client)
spf.register_plugin(asyncdb)
spf.register_plugin(cache_control)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()

    worker = Worker(loop=loop)
    loop.create_task(worker.run())

    server = app.create_server(host="0.0.0.0", port=9000)
    loop.add_signal_handler(signal.SIGINT, loop.stop)
    loop.create_task(server)
    loop.run_forever()
