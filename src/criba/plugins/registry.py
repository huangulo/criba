import importlib
import logging
import pkgutil
from pathlib import Path

from criba.models.plugin_base import SourcePlugin

logger = logging.getLogger(__name__)

_registry: dict[str, SourcePlugin] = {}
_discovered: bool = False


def register_plugin(plugin: SourcePlugin) -> None:
    """Register a source plugin."""
    name = plugin.get_name()
    if name in _registry:
        logger.warning("Plugin %s already registered, overwriting", name)
    _registry[name] = plugin
    logger.debug("Registered plugin: %s", name)


def get_plugin(name: str) -> SourcePlugin | None:
    """Get a registered plugin by name. Discovers plugins if not yet done."""
    if not _discovered:
        discover_plugins()
    return _registry.get(name)


def list_plugins() -> list[str]:
    """List all registered plugin names. Discovers plugins if not yet done."""
    if not _discovered:
        discover_plugins()
    return sorted(_registry.keys())


def discover_plugins() -> None:
    """Auto-discover plugins in the criba.plugins package."""
    global _discovered
    if _discovered:
        return

    plugins_dir = Path(__file__).parent
    logger.info("Discovering plugins in %s", plugins_dir)

    for item in plugins_dir.iterdir():
        if item.is_dir() and not item.name.startswith("_") and (item / "__init__.py").exists():
            module_name = f"criba.plugins.{item.name}"
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "plugin"):
                    plugin_instance = module.plugin
                    if isinstance(plugin_instance, SourcePlugin):
                        register_plugin(plugin_instance)
                    else:
                        logger.warning("Plugin %s 'plugin' attribute is not a SourcePlugin", item.name)
                else:
                    logger.debug("Module %s has no 'plugin' attribute, skipping", module_name)
            except Exception:
                logger.exception("Failed to load plugin module: %s", module_name)

    _discovered = True
    logger.info("Discovered %d plugins: %s", len(_registry), list(_registry.keys()))
