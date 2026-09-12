from __future__ import annotations

import logging
from dataclasses import dataclass

from configurations.runtime_models import SchedulerConfig
from core.models.context import ContextManager
from core.models.playlist import Playlists
from core.models.trace import ScheduleTrace
from core.policies import POLICY_REGISTRY, Policy
from core.runtime.act_plan import plan_actuation
from core.runtime.actuator import Actuator
from core.runtime.controller import Controller
from core.runtime.executor import WEExecutor
from core.runtime.matcher import Matcher
from core.runtime.we_config import WEConfigProber
from core.sensors import SENSOR_REGISTRY
from ui.i18n import set_language

logger = logging.getLogger("WEScheduler.Runtime")


@dataclass(frozen=True)
class EngineReplacement:
    executor: WEExecutor
    context_manager: ContextManager
    matcher: Matcher
    actuator: Actuator
    controller: Controller
    config: SchedulerConfig
    we_config_prober: WEConfigProber


class Engine:
    """Config-bound runtime for sensing, matching, probing, and acting."""

    def __init__(self, replacement: EngineReplacement) -> None:
        self.install_replacement(replacement)

    @classmethod
    def from_config(cls, config: SchedulerConfig) -> Engine:
        """Build and install a complete runtime from a verified config."""

        engine = cls(cls._build_components(config))
        logger.info("Built runtime with %d playlists.", len(config.playlists))
        return engine

    def prepare_replacement(self, config: SchedulerConfig) -> EngineReplacement:
        """Build a replacement and import state without changing this engine.

        Raises:
            RuntimeError: If a runtime component rejects the imported state.
        """

        matcher_state = self.matcher.export_state()
        controller_state = self.controller.export_state()
        prepared = self._build_components(config)
        prepared.matcher.import_state(matcher_state)
        prepared.controller.import_state(controller_state)
        return prepared

    def install_replacement(self, replacement: EngineReplacement) -> None:
        """Install a prepared replacement at the caller's safe boundary."""

        self.executor = replacement.executor
        self.context_manager = replacement.context_manager
        self.matcher = replacement.matcher
        self.actuator = replacement.actuator
        self.controller = replacement.controller
        self.we_config_prober = replacement.we_config_prober
        Playlists.configure(replacement.config.playlists)
        set_language(replacement.config.language)
        self.config = replacement.config

    def schedule(
        self,
        cached_playlists: Playlists,
        paused: bool,
        manual_requested: bool,
    ) -> ScheduleTrace:
        context = self.context_manager.sense()
        match = self.matcher.match(context)
        plan = plan_actuation(
            factual=self.we_config_prober.probe_playlist(),
            cached_playlists=cached_playlists,
            paused=paused,
            manual_requested=manual_requested,
        )
        decision = self.controller.decide_action(plan, context, match)
        action = self.actuator.act(decision)
        if action.executed:
            self.controller.notify_executed(decision)
        return ScheduleTrace(
            context=context,
            match=match,
            plan=plan,
            decision=decision,
            action=action,
        )

    def ensure_we_alive(self, paused: bool = False) -> None:
        if paused:
            return
        self.executor.keep_alive()

    @staticmethod
    def _build_components(config: SchedulerConfig) -> EngineReplacement:
        executor = WEExecutor(config.wallpaper_engine_path)

        context_manager = ContextManager()
        for sensor_cls in SENSOR_REGISTRY:
            context_manager.register_sensor(sensor_cls.create(config))

        policies: list[Policy] = [cls(getattr(config.policies, cls.config_key)) for cls in POLICY_REGISTRY]

        matcher = Matcher(config.playlists, policies, config.tags)
        controller = Controller(config.scheduling)
        actuator = Actuator(executor)

        return EngineReplacement(
            executor=executor,
            context_manager=context_manager,
            matcher=matcher,
            actuator=actuator,
            controller=controller,
            config=config,
            we_config_prober=WEConfigProber(config.wallpaper_engine_path),
        )
