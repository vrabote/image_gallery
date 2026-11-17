"""Площадки: адаптеры API и браузерные адаптеры.

Модуль намеренно не импортирует конкретные площадки на старте, чтобы запуск
не падал, если нет необязательных зависимостей (например, Playwright).
"""

from .base import Platform, PlatformInfo, PublishContext, Registry, build_registry

__all__ = ["Platform", "PlatformInfo", "PublishContext", "Registry", "build_registry"]
