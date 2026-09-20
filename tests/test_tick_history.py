from __future__ import annotations

import json
from datetime import UTC, datetime

from core.models.context import Context
from core.models.scene import Scenes
from core.models.trace import Action, ActionResult, ActPlan, Decision, DecisionMode, Match, ScheduleTrace, TickTrace
from core.state.tick_history import TickHistoryStore, TickHistoryWindow
from ui.tick_history_export import (
    TickHistoryJsonFormatter,
    export_tick_history,
    redact_tick_history_payload,
)


def test_tick_history_json_formatter_uses_tick_window_contract():
    content = TickHistoryJsonFormatter.format(TickHistoryWindow(live_tick_id=None, traces=()))

    assert json.loads(content) == {"liveTickId": None, "ticks": []}
    assert content.endswith("\n")


def test_tick_history_export_redacts_only_credentials_and_location():
    payload = {
        "apiKey": "secret",
        "location": {"name": "上海", "latitude": 31.2, "longitude": 121.5},
        "window": {"process": "code.exe", "title": "Private project"},
        "playlist": {"name": "Night"},
    }

    assert redact_tick_history_payload(payload) == {
        "apiKey": "[REDACTED]",
        "location": "[REDACTED]",
        "window": {"process": "code.exe", "title": "Private project"},
        "playlist": {"name": "Night"},
    }


def test_export_tick_history_writes_timestamped_json(tmp_path):
    store = TickHistoryStore()
    store.update(
        TickTrace(
            tick_id=7,
            ts=1.0,
            paused=False,
            pause_until=0.0,
            schedule=ScheduleTrace(
                context=Context(),
                match=Match(best_scenes=Scenes()),
                plan=ActPlan(mode=DecisionMode.NORMAL, active_scenes=Scenes()),
                decision=Decision(action=Action.HOLD, target=Scenes()),
                action=ActionResult(),
            ),
        )
    )

    path = export_tick_history(
        store,
        str(tmp_path),
        now=datetime(2026, 9, 5, 1, 2, 3, 456789, tzinfo=UTC),
    )

    assert path == str(tmp_path / "tick-history-20260905T010203.456789Z.json")
    payload = json.loads((tmp_path / "tick-history-20260905T010203.456789Z.json").read_text(encoding="utf-8"))
    assert payload["liveTickId"] == 7
    assert payload["ticks"][0]["summary"]["tickId"] == 7
