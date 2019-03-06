from .deep_focus import DeepFocus
from .evening_commute import EveningCommute
from .immersive_reading import ImmersiveReading
from .mellow_dinner import MellowDinner
from .morning_stroll import MorningStroll
from .peaceful_sleep import PeacefulSleep
from .random import Random
from .romantic_night import RomanticNight
from .workout_hype import WorkoutHype

BLEND_MAPPING = {
    "workoutHype": WorkoutHype,
    "deepFocus": DeepFocus,
    "eveningCommute": EveningCommute,
    "immersiveReading": ImmersiveReading,
    "mellowDinner": MellowDinner,
    "morningStroll": MorningStroll,
    "peacefulSleep": PeacefulSleep,
    "romanticNight": RomanticNight,
    "random": Random,
}
