from __future__ import annotations

import sys

from core.models.trace import TickTrace
from ui.i18n import scene_name


class CliStatusReporter:
    def __init__(self, *, print_status: bool = True):
        self.print_status = print_status
        self.last_status_line = ""

    def on_tick(self, trace: TickTrace) -> None:
        process_name = trace.context.window.process or "N/A"
        idle_time = trace.context.idle
        best_scenes = trace.match.best_scenes
        tags = trace.match.raw_context_vector
        sorted_tags = sorted(tags.items(), key=lambda x: x[1], reverse=True)[:3]

        if best_scenes:
            primary = scene_name(best_scenes[0])
            label = f"{primary}(+{len(best_scenes) - 1})" if len(best_scenes) > 1 else primary
        else:
            label = None

        tag_parts = []
        for tag, weight in sorted_tags:
            bar_len = int(min(weight, 1.5) * 5)
            bar = "■" * bar_len
            tag_parts.append(f"{tag} {weight:.2f} {bar}")

        tag_str = " | ".join(tag_parts)
        gap_str = f" gap={trace.match.similarity_gap:.2f}" if trace.match.scene_matches else ""
        prefix = "PAUSED " if trace.paused else ""
        self.last_status_line = f"{prefix}[{label or 'WAITING'}] {process_name}({idle_time:.0f}s) >> {tag_str}{gap_str}"
        if self.print_status and not getattr(sys, "frozen", False):
            print(f"\r{self.last_status_line:<110}", end="", flush=True)
