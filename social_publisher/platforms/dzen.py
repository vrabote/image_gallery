"""Дзен: у платформы нет публичного API для автопостинга.

Работает так:
  * браузерный режим (по умолчанию) — Playwright заходит в вашу залогиненную
    студию и заполняет публикацию;
  * режим RSS — можно сгенерировать фид статей (команда ``rss dzen``), Дзен
    подхватит его сам, если канал привязан к RSS;
  * иначе пост помечается как «сделать вручную», и в журнал пишется, что
    именно осталось сделать.
"""

from __future__ import annotations

from ..core.journal import STATUS_MANUAL
from ..core.models import Limits, Post
from .base import Platform, PlatformInfo, PublishContext


class Dzen(Platform):
    info = PlatformInfo(
        name="dzen",
        title="Дзен (статьи и видео)",
        supports_api=False,
        supports_browser=True,
        limits=Limits(
            max_video_seconds=None,
            max_video_mb=2000,
            max_image_mb=10,
            max_images=20,
            max_caption_chars=100_000,
            max_title_chars=100,
            supports_video=True,
            supports_images=True,
            supports_carousel=True,
        ),
        notes="Публичного API нет: браузерный режим или RSS-фид.",
        docs="https://dzen.ru/help/ru/channel/cross-platform",
        requires=("браузерный режим (playwright)",),
    )
    mode = "manual"

    def check_env(self):
        # ручной режим доступен всегда: файлы и подпись подготовим локально
        return []

    def publish(self, post: Post):
        return self.manual(
            post,
            "Дзен без API: откройте Дзен.Студию и опубликуйте вручную "
            "(или включите браузерный режим) — "
            f"файлы: {', '.join(m.name for m in post.media)}",
        )


def create(ctx: PublishContext) -> Dzen:
    return Dzen(ctx)
