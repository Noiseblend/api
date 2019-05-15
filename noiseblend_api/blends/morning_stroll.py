from .blend import Blend


class MorningStroll(Blend):
    ATTRIBUTES = {"target_valence": 0.75, "target_danceability": 0.65}
    TRACK_LIMIT = 100
    TOP_TRACKS_COUNT = 10
    TOP_TRACKS_ATTRIBUTES = {"valence": 0.7}
    GENRES = ["summer"]
