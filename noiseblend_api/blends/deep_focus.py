from .blend import Blend


class DeepFocus(Blend):
    ATTRIBUTES = {
        "target_energy": 0.1,
        "max_speechiness": 0.13,
        "target_danceability": 0.1,
        "min_instrumentalness": 0.55,
    }
    GENRES = ["study"]
    GENRE_TO_ARTIST_RATIO = 0.7
