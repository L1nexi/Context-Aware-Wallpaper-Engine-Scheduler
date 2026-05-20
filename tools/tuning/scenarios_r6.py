from __future__ import annotations

from tools.tuning.models import MatchProfile, Scenario, activity_signal, chill, focus, weather

PROFILES = [
    MatchProfile("current"),
    MatchProfile("r6-gp1.25-gc1.20", gamma_playlist=1.25, gamma_context=1.20),
]

SCENARIOS = [
    Scenario(
        "day focus clear",
        hour=14,
        day_of_year=95,
        weather=weather("clear"),
        activity=focus(),
        expected="BRIGHT_FLOW",
    ),
    Scenario(
        "day chill clear",
        hour=14,
        day_of_year=95,
        weather=weather("clear"),
        activity=chill(),
        expected="CASUAL_ANIME",
    ),
    Scenario(
        "night focus clear",
        hour=23,
        day_of_year=95,
        weather=weather("clear"),
        activity=focus(),
        expected="NIGHT_FOCUS",
    ),
    Scenario(
        "night chill clear",
        hour=23,
        day_of_year=95,
        weather=weather("clear"),
        activity=chill(),
        expected="NIGHT_CHILL",
    ),
    Scenario(
        "sunset idle clear",
        hour=20,
        day_of_year=95,
        weather=weather("clear"),
        expected="SUNSET_GLOW",
    ),
    Scenario(
        "day idle moderate rain",
        hour=14,
        day_of_year=95,
        weather=weather("mod_rain"),
        expected="RAINY_MOOD",
    ),
    Scenario(
        "winter sunset snow",
        hour=20,
        day_of_year=355,
        weather=weather("light_snow"),
        expected="WINTER_VIBES",
    ),
    Scenario(
        "late summer light rain rising focus",
        hour=17,
        day_of_year=235,
        weather=weather("light_rain"),
        activity=activity_signal({"focus": 0.7, "chill": 0.3}, intensity=0.45),
        note="subtle observed boundary",
    ),
]
