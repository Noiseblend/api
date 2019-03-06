from .blend import Blend


class ImmersiveReading(Blend):
    ATTRIBUTES = {"min_instrumentalness": 0.6, "target_acousticness": 0.7}
    GENRES = ["piano", "soundtrack"]
