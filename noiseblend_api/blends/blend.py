import random
from collections import defaultdict

from spfy.constants import TimeRange

from .. import logger
from ..helpers import user_disliked_artists


class Blend:
    ATTRIBUTES = {}
    ORDER = {}
    ARTIST_GENRES = set()
    GENRES = []
    TRACK_LIMIT = 100
    ARTIST_LIMIT = 4
    TOP_TRACKS_COUNT = 0
    GENRE_TO_ARTIST_RATIO = 0.4
    TOP_TRACKS_TIME_RANGE = TimeRange.MEDIUM_TERM
    TOP_TRACKS_ATTRIBUTES = {}
    TOP_TRACKS_TO_ARTIST_RATIO = 0.3

    def __init__(self, spotify, dbpool):
        self.spotify = spotify
        self.dbpool = dbpool
        self.attributes = {k: str(v) for k, v in self.ATTRIBUTES.items()}

    @staticmethod
    def track_matches_attributes(track, attributes):
        return all(
            abs(value - getattr(track, attribute)) <= 0.1
            for attribute, value in attributes.items()
        )

    async def recommend_by_top_tracks(
        self, track_limit, attributes, selection_attributes=None
    ):
        selection_attributes = selection_attributes or self.TOP_TRACKS_ATTRIBUTES
        track_limit = track_limit or self.TRACK_LIMIT
        track_limit = int(track_limit * self.TOP_TRACKS_TO_ARTIST_RATIO)

        top_tracks = await self.spotify.current_user_top_tracks(
            time_range=self.TOP_TRACKS_TIME_RANGE, limit=50
        )

        audio_features = await self.spotify.audio_features(tracks=top_tracks)
        if selection_attributes:
            matching_top_tracks = [
                audio_feature.id
                for audio_feature in audio_features
                if audio_feature
                and self.track_matches_attributes(audio_feature, selection_attributes)
            ]
        else:
            matching_top_tracks = [af.id for af in audio_features if af]

        matching_top_tracks = random.sample(
            matching_top_tracks, min(5, len(matching_top_tracks))
        )

        if not matching_top_tracks:
            return []

        tracks = (
            await self.spotify.recommendations(
                seed_tracks=matching_top_tracks, limit=track_limit, **attributes
            )
        ).tracks

        return tracks

    async def get_top_related_tracks(self, count, time_range=None):
        tracks = await self.spotify.current_user_top_tracks(
            time_range=time_range or self.TOP_TRACKS_TIME_RANGE, limit=50
        )

        track_list = list(tracks)
        return random.sample(track_list, int(min(len(track_list), count)))

    async def recommend_by_genres(self, track_limit, attributes, artists=None):
        track_limit = track_limit or self.TRACK_LIMIT
        track_limit = int(track_limit * self.GENRE_TO_ARTIST_RATIO)

        seed_artists = random.sample(artists, min(len(artists), 5 - len(self.GENRES)))
        tracks = (
            await self.spotify.recommendations(
                seed_artists=seed_artists,
                seed_genres=self.GENRES,
                limit=track_limit,
                **attributes
            )
        ).tracks

        return tracks

    @staticmethod
    def get_genre_artist_mapping(artists, min_artists=1):
        genre_artists = defaultdict(list)
        for artist in artists:
            for genre in artist.genres:
                genre_artists[genre].append(artist)
        return {g: a for g, a in genre_artists.items() if len(a) >= min_artists}

    async def get_top_artists(self, min_artists, time_range=None, related=True):
        artists = await self.spotify.top_artists_pg(time_range or TimeRange.LONG_TERM)

        if not related:
            return random.sample(artists, min(min_artists, len(artists)))

        for minimum in range(min_artists, 0, -1):
            genre_artists = self.get_genre_artist_mapping(artists, minimum)
            if genre_artists:
                if self.ARTIST_GENRES:
                    genre_artists = {
                        g: a
                        for g, a in genre_artists.items()
                        if set(g.split()) & self.ARTIST_GENRES
                    } or genre_artists

                choices = list(genre_artists.values())
                if len(choices) > 5:
                    return random.choice(choices)
        return random.sample(artists, min(min_artists, len(artists)))

    async def filter_tracks(self, tracks, filter_explicit):
        tracks = [
            t
            for t in tracks
            if t.is_playable is True or not isinstance(t.is_playable, bool)
        ]
        logger.debug("Playable: %d tracks", len(tracks))

        disliked_artists = set(
            await user_disliked_artists(self.spotify, conn=self.dbpool)
        )
        tracks = [
            t for t in tracks if not set(a.id for a in t.artists) & disliked_artists
        ]
        logger.debug("Dislike Filter: %d tracks", len(tracks))

        if filter_explicit:
            tracks = [t for t in tracks if not t.explicit]
            logger.debug("Explicit Filter: %d tracks", len(tracks))

        return [t.id for t in tracks]

    # pylint: disable=too-many-locals
    async def generate_tracks(
        self,
        attributes=None,
        order=None,
        artists=None,
        artist_limit=None,
        track_limit=None,
        filter_explicit=False,
        top_tracks_count=None,
        top_artists_related=True,
        time_range=None,
    ):
        track_limit = track_limit or self.TRACK_LIMIT
        artists = artists or await self.get_top_artists(
            artist_limit or self.ARTIST_LIMIT,
            time_range=time_range,
            related=top_artists_related,
        )
        artists = random.sample(artists, min(len(artists), 5))

        if attributes:
            attributes = {k: str(v) for k, v in attributes.items()}
        else:
            attributes = self.attributes

        tracks = []
        if artists:
            tracks = (
                await self.spotify.recommendations(
                    seed_artists=artists, limit=track_limit, **attributes
                )
            ).tracks
            logger.debug("Recommendations: %d tracks", len(tracks))

        top_tracks_count = top_tracks_count or self.TOP_TRACKS_COUNT
        top_tracks = []
        if top_tracks_count:
            top_tracks = await self.get_top_related_tracks(top_tracks_count)
            logger.debug("Top Tracks: %d tracks", len(top_tracks))

        if self.GENRES:
            genre_tracks = await self.recommend_by_genres(
                track_limit, attributes, artists=artists
            )
            tracks_count = int(len(tracks) * (1 - self.GENRE_TO_ARTIST_RATIO))
            tracks = random.sample(tracks, tracks_count) + genre_tracks

            logger.debug("Genres: %d tracks", len(genre_tracks))
            logger.debug("Random Sample (genres): %d tracks", len(tracks))

        if self.TOP_TRACKS_ATTRIBUTES:
            recommended_by_top_tracks = await self.recommend_by_top_tracks(
                track_limit, attributes
            )
            if recommended_by_top_tracks:
                tracks_count = int(len(tracks) * (1 - self.TOP_TRACKS_TO_ARTIST_RATIO))
                tracks = random.sample(tracks, tracks_count) + recommended_by_top_tracks

                logger.debug(
                    "Recommended by Top Tracks: %d tracks",
                    len(recommended_by_top_tracks),
                )
                logger.debug("Random Sample (recomm): %d tracks", len(tracks))

        tracks = random.sample(tracks, min(len(tracks), track_limit)) + top_tracks
        logger.debug("Random Sample: %d tracks", len(tracks))

        tracks = await self.filter_tracks(tracks, filter_explicit)
        logger.debug("Filter: %d tracks", len(tracks))
        if not tracks:
            return None

        order = order or self.ORDER
        if order:
            tracks = await self.spotify.order_by(order, tracks)

        return tracks
