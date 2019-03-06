from .blend import Blend


class EveningCommute(Blend):
    ATTRIBUTES = {"target_danceability": 0.6, "target_tempo": 100}
    GENRES = ["chill"]
