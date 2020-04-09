import asyncio

from arq import concurrent
from fuzzywuzzy import fuzz

from .. import logger
from ..helpers import fuzzysearch, get_tuneable_attributes, user_disliked_artists
from .actor import Actor
from .spotify import SpotifyActor


class Radio(SpotifyActor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def filter_tracks(self, spotify, tracks, filter_explicit=False):
        tracks = [
            t
            for t in tracks
            if t.is_playable is True or not isinstance(t.is_playable, bool)
        ]
        logger.debug("Playable: %d tracks", len(tracks))

        disliked_artists = set(await user_disliked_artists(spotify, conn=self.dbpool))
        tracks = [
            t for t in tracks if not set(a.id for a in t.artists) & disliked_artists
        ]
        logger.debug("Dislike Filter: %d tracks", len(tracks))

        if filter_explicit:
            tracks = [t for t in tracks if not t.explicit]
            logger.debug("Explicit Filter: %d tracks", len(tracks))

        return [t.id for t in tracks]

    @staticmethod
    def match_artist(tracks, artist):
        return max(
            tracks, key=lambda t: max(fuzz.ratio(artist, a.name) for a in t.artists)
        )

    def get_tracks(self, tracks_by_artist, track_responses):
        matched_tracks = []
        for r, t in zip(track_responses, tracks_by_artist):
            tracks = r.tracks["items"]
            if not tracks:
                continue

            if len(t) > 1:
                artist = t[1]
            else:
                artist = None

            if len(tracks) == 1 or not artist:
                matched_tracks.append(tracks[0])
            else:
                matched_tracks.append(self.match_artist(tracks, artist))
        return matched_tracks

    # pylint: disable=too-many-locals
    @concurrent(Actor.HIGH_QUEUE, unique=True, expire_seconds=20)
    async def play_radio(
        self,
        user_id,
        username,
        artist_names=None,
        genre_names=None,
        track_names=None,
        limit=100,
        attributes=None,
        device=None,
        volume=None,
    ):
        spotify = await self.spotify(user_id, username)
        tuneable_attributes = get_tuneable_attributes(attributes)
        tracks_by_artist = [
            track_name.rsplit(" by ", maxsplit=1) for track_name in (track_names or [])
        ]

        artist_requests = [
            spotify.search_artist(a, limit=1) for a in (artist_names or [])
        ]
        track_requests = [
            spotify.search_track(t[0], limit=(1 if len(t) == 1 else 10))
            for t in tracks_by_artist
        ]
        genre_requests = []
        if genre_names:
            genre_requests = [spotify.recommendation_genre_seeds()]

        responses = await asyncio.gather(
            *[*artist_requests, *track_requests, *genre_requests]
        )
        if genre_names:
            *artist_and_track_responses, genres_response = responses
        else:
            artist_and_track_responses = responses

        artist_responses = artist_and_track_responses[: len(artist_requests)]
        track_responses = artist_and_track_responses[len(artist_requests) :]

        artists = [
            r.artists["items"][0] for r in artist_responses if r.artists.total > 0
        ]
        tracks = self.get_tracks(tracks_by_artist, track_responses)
        genres = []
        if genre_names:
            genre_set = set(genres_response.genres)
            genres = list({fuzzysearch(name, genre_set) for name in genre_names})

        artist_names = list({a.name for a in artists})
        track_names = list(
            {f"{t.name} - {' & '.join(a.name for a in t.artists)}" for t in tracks}
        )

        artists = list({a.id for a in artists})
        tracks = list({t.id for t in tracks})

        recommended_tracks = await spotify.recommendations(
            seed_artists=artists,
            seed_genres=genres,
            seed_tracks=tracks,
            limit=limit,
            **tuneable_attributes,
        )
        recommended_tracks = await self.filter_tracks(spotify, recommended_tracks)

        if volume is not None:
            await spotify.volume(volume, device=device)

        await spotify.transfer_playback(device)
        await spotify.shuffle(False, device=device)
        await spotify.start_playback(
            device=device, tracks=tracks + recommended_tracks, retries=0
        )

        return {
            "artists": [
                {"id": a_id, "name": a_name}
                for a_id, a_name in zip(artists, artist_names)
            ],
            "tracks": [
                {"id": t_id, "name": t_name}
                for t_id, t_name in zip(tracks, track_names)
            ],
            "genres": genres,
        }
