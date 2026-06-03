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


def get_policy_fixed_output_tags() -> dict[str, tuple[str, ...]]:
    return {policy_cls.config_key: policy_cls.fixed_output_tags for policy_cls in POLICY_REGISTRY if policy_cls.fixed_output_tags is not None}


KNOWN_TAGS: list[str] = sorted(
    {
        "focus",
        "chill",
        *(tag for tags in get_policy_fixed_output_tags().values() for tag in tags),
    }
)

__all__ = [
    "Policy",
    "ActivityPolicy",
    "TimePolicy",
    "SeasonPolicy",
    "WeatherPolicy",
    "POLICY_REGISTRY",
    "get_policy_fixed_output_tags",
    "KNOWN_TAGS",
]
