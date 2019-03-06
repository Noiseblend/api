import asyncio
import random

from spfy import TimeRange

from .. import logger
from .blend import Blend


class Random(Blend):
    # pylint: disable=too-many-locals,arguments-differ,unused-argument
    async def generate_tracks(
        self, *args, attributes=None, order=None, filter_explicit=False, **kwargs
    ):
        time_range = random.choice(list(TimeRange))
        top_tracks_count = random.randint(1, 20)
        seed_count = random.randint(1, 5)
        seed_artists_count = random.randint(1, seed_count)

        remaining_seeds = seed_count - seed_artists_count
        if remaining_seeds > 0:
            seed_tracks_count = random.randint(1, remaining_seeds)
        else:
            seed_tracks_count = 0

        remaining_seeds = remaining_seeds - seed_tracks_count
        if remaining_seeds > 0:
            seed_genres_count = random.randint(1, remaining_seeds)
        else:
            seed_genres_count = 0

        logger.debug(
            """
            Seed count: %d
            Seed Artists count: %d
            Seed Tracks count: %d
            Seed Genres count: %d
            """,
            seed_count,
            seed_artists_count,
            seed_tracks_count,
            seed_genres_count,
        )

        if attributes:
            attributes = {k: str(v) for k, v in attributes.items()}
        else:
            attributes = self.attributes

        requests = {}
        if seed_artists_count:
            requests["seed_artists"] = self.get_top_artists(
                seed_artists_count, time_range=time_range, related=False
            )

        if seed_genres_count:
            requests["seed_genres"] = self.spotify.recommendation_genre_seeds()

        if seed_tracks_count:
            requests["seed_tracks"] = self.spotify.current_user_top_tracks(
                time_range=time_range, limit=50
            )

        top_tracks = []
        responses = await asyncio.gather(*requests.values())
        params = {
            seed_type: response
            for seed_type, response in zip(requests.keys(), responses)
        }
        if "seed_genres" in params:
            genres = params["seed_genres"].genres
            params["seed_genres"] = random.sample(
                genres, min(seed_genres_count, len(genres))
            )
        if "seed_tracks" in params:
            tracks = params["seed_tracks"]["items"]
            top_tracks = random.sample(tracks, min(top_tracks_count, len(tracks)))
            top_tracks = [t.id for t in top_tracks]
            params["seed_tracks"] = random.sample(
                tracks, min(seed_tracks_count, len(tracks))
            )

        tracks = (
            await self.spotify.recommendations(limit=100, **params, **attributes)
        ).tracks
        tracks = await self.filter_tracks(tracks, filter_explicit)
        tracks = (
            random.sample(tracks, min(100 - len(top_tracks), len(tracks))) + top_tracks
        )
        random.shuffle(tracks)

        if order:
            tracks = await self.spotify.order_by(order, tracks)

        return tracks
