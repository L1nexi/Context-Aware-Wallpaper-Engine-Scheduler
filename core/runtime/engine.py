from __future__ import annotations

import logging
from dataclasses import dataclass

from configurations.errors import ConfigLoadError
from configurations.loader import ConfigLoader
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
class _BuiltEngine:
    executor: WEExecutor
    context_manager: ContextManager
    matcher: Matcher
    actuator: Actuator
    controller: Controller
    config: SchedulerConfig
    we_config_prober: WEConfigProber


class Engine:
    """Config-bound runtime for sensing, matching, probing, and acting."""

    def __init__(self, config_dir: str) -> None:
        self.config_dir = config_dir
        self.config_loader = ConfigLoader(config_dir)
        self.executor: WEExecutor | None = None
        self.context_manager: ContextManager | None = None
        self.matcher: Matcher | None = None
        self.actuator: Actuator | None = None
        self.controller: Controller | None = None
        self.we_config_prober: WEConfigProber | None = None
        self.config_fingerprint: tuple[tuple[str, bool, int], ...] = ()

    @classmethod
    def load(cls, config_dir: str) -> Engine:
        """Load verified config and build the initial runtime.

        Raises:
            ConfigLoadError: If config files are invalid.
            OSError: If config files cannot be read by the config loader.
        """
        runtime = cls(config_dir)
        config = runtime.config_loader.load_verified_config()
        runtime.config_fingerprint = runtime.config_loader.fingerprint()
        logger.info("Loaded %d playlists.", len(config.playlists))
        runtime._install_components(runtime._build_components(config))
        return runtime

    def reload_if_changed(self) -> None:
        """Reload changed config while preserving runtime state.

        Raises:
            ConfigLoadError: If changed config files are invalid.
        """
        fingerprint = self.config_loader.fingerprint()
        if fingerprint == self.config_fingerprint:
            return
        self._hot_reload(fingerprint)

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

    def _build_components(self, config: SchedulerConfig) -> _BuiltEngine:
        executor = WEExecutor(config.wallpaper_engine_path)

        context_manager = ContextManager()
        for sensor_cls in SENSOR_REGISTRY:
            context_manager.register_sensor(sensor_cls.create(config))

        policies: list[Policy] = [cls(getattr(config.policies, cls.config_key)) for cls in POLICY_REGISTRY]

        matcher = Matcher(config.playlists, policies, config.tags)
        controller = Controller(config.scheduling)
        actuator = Actuator(executor)

        return _BuiltEngine(
            executor=executor,
            context_manager=context_manager,
            matcher=matcher,
            actuator=actuator,
            controller=controller,
            config=config,
            we_config_prober=WEConfigProber(config.wallpaper_engine_path),
        )

    def _install_components(self, runtime: _BuiltEngine) -> None:
        self.executor = runtime.executor
        self.context_manager = runtime.context_manager
        self.matcher = runtime.matcher
        self.actuator = runtime.actuator
        self.controller = runtime.controller
        self.we_config_prober = runtime.we_config_prober
        Playlists.configure(runtime.config.playlists)
        set_language(runtime.config.language)

    def _hot_reload(self, fingerprint: tuple[tuple[str, bool, int], ...]) -> None:
        previous_config = self.config_loader.config
        try:
            matcher_state = self.matcher.export_state()
            controller_state = self.controller.export_state()

            config = self.config_loader.load_verified_config()
            logger.info("Hot reload: config changed, rebuilding components.")

            next_runtime = self._build_components(config)

            next_runtime.matcher.import_state(matcher_state)
            next_runtime.controller.import_state(controller_state)
            self._install_components(next_runtime)

            logger.info("Hot reload complete. %d playlists loaded.", len(config.playlists))
        except ConfigLoadError as exc:
            self.config_loader.config = previous_config
            logger.warning("Hot reload rejected. Keeping previous runtime.\n%s", exc)
            raise
        except Exception:
            self.config_loader.config = previous_config
            logger.exception("Hot reload failed unexpectedly, keeping previous runtime")
        finally:
            # In all cases, update fingerprint to avoid repeated reloads.
            self.config_fingerprint = fingerprint
