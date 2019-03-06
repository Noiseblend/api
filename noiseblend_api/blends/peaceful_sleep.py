from .blend import Blend


class PeacefulSleep(Blend):
    ATTRIBUTES = {
        "target_energy": 0.1,
        "target_acousticness": 0.6,
        "min_instrumentalness": 0.55,
    }
    GENRES = {"sleep", "soundtrack"}
    GENRE_TO_ARTIST_RATIO = 0.65
