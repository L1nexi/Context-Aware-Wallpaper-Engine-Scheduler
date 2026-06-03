from __future__ import annotations

import logging
from dataclasses import dataclass

from configurations.errors import ConfigLoadError
from configurations.loader import ConfigLoader
from configurations.runtime_models import PlaylistConfig, SchedulerConfig
from core.models.context import Context, ContextManager
from core.models.playlist import Playlists
from core.models.trace import ActionResult, Match
from core.policies import POLICY_REGISTRY, Policy
from core.runtime.act_plan import ActPlan
from core.runtime.actuator import Actuator
from core.runtime.controller import SchedulingController
from core.runtime.executor import WEExecutor
from core.runtime.matcher import Matcher
from core.runtime.we_config import FactualPlaylistState, WEConfigProber
from core.sensors import SENSOR_REGISTRY

logger = logging.getLogger("WEScheduler.Runtime")


@dataclass(frozen=True)
class _BuiltEngine:
    executor: WEExecutor
    context_manager: ContextManager
    matcher: Matcher
    actuator: Actuator
    playlist_configs: dict[str, PlaylistConfig]
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

    def sense(self) -> Context:
        return self.context_manager.sense()

    def think(self, context: Context) -> Match:
        return self.matcher.match(context)

    def probe_playlist(self) -> FactualPlaylistState:
        return self.we_config_prober.probe_playlist()

    def act(self, plan: ActPlan, match: Match, context: Context) -> ActionResult:
        return self.actuator.act(plan.mode, match, plan.active_playlists, context)

    def _build_components(self, config: SchedulerConfig) -> _BuiltEngine:
        executor = WEExecutor(config.wallpaper_engine_path)

        context_manager = ContextManager()
        for sensor_cls in SENSOR_REGISTRY:
            context_manager.register_sensor(sensor_cls.create(config))

        policies: list[Policy] = [cls(getattr(config.policies, cls.config_key)) for cls in POLICY_REGISTRY]

        matcher = Matcher(config.playlists, policies, config.tags)
        actuator = Actuator(
            executor,
            SchedulingController(config.scheduling),
        )

        return _BuiltEngine(
            executor=executor,
            context_manager=context_manager,
            matcher=matcher,
            actuator=actuator,
            playlist_configs=config.playlists,
            we_config_prober=WEConfigProber(config.wallpaper_engine_path),
        )

    def _install_components(self, runtime: _BuiltEngine) -> None:
        self.executor = runtime.executor
        self.context_manager = runtime.context_manager
        self.matcher = runtime.matcher
        self.actuator = runtime.actuator
        self.we_config_prober = runtime.we_config_prober
        Playlists.configure(runtime.playlist_configs)

    def _hot_reload(self, fingerprint: tuple[tuple[str, bool, int], ...]) -> None:
        previous_config = self.config_loader.config
        try:
            matcher_state = self.matcher.export_state()
            actuator_state = self.actuator.export_state()

            config = self.config_loader.load_verified_config()
            logger.info("Hot reload: config changed, rebuilding components.")

            next_runtime = self._build_components(config)

            next_runtime.matcher.import_state(matcher_state)
            next_runtime.actuator.import_state(actuator_state)
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
