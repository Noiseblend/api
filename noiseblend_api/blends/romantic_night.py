from .blend import Blend


class RomanticNight(Blend):
    ATTRIBUTES = {"target_danceability": 0.6, "target_energy": 0.35}
    GENRES = ["romance"]
    GENRE_TO_ARTIST_RATIO = 0.65
