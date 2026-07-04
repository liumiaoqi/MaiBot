"""插件迁移协调模块。"""

from .coordinator import MigrationCoordinator, MigrationPhase, PluginMigrationState

__all__ = [
    "MigrationCoordinator",
    "MigrationPhase",
    "PluginMigrationState",
]