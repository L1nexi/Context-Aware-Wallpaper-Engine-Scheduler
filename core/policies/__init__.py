from core.policies.activity import ActivityPolicy
from core.policies.base import Policy
from core.policies.season import SeasonPolicy
from core.policies.time import TimePolicy
from core.policies.weather import WeatherPolicy

POLICY_REGISTRY: list[type[Policy]] = [
    ActivityPolicy,
    TimePolicy,
    SeasonPolicy,
    WeatherPolicy,
]

__all__ = [
    "Policy",
    "ActivityPolicy",
    "TimePolicy",
    "SeasonPolicy",
    "WeatherPolicy",
    "POLICY_REGISTRY",
]
