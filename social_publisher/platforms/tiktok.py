"""TikTok: публичного API для загрузки нет (Content Posting API — только
после одобрения приложения). Основной путь — браузерный режим; ручной режим
готовит файлы и подпись в state/manual/tiktok/.
"""

from __future__ import annotations

import shutil

from ..core.models import Limits, Post
from .base import Platform, PlatformInfo, PublishContext


class TikTok(Platform):
    info = PlatformInfo(
        name="tiktok",
        title="TikTok (клипы)",
        supports_api=False,
        supports_browser=True,
        limits=Limits(
            max_video_seconds=600,
            max_video_mb=4000,
            max_image_mb=20,
            max_images=35,
            max_caption_chars=2200,
            max_tags=20,
            supports_video=True,
            supports_images=True,
        ),
        notes="Публичный API только после одобрения; надёжнее браузерный режим.",
        docs="https://developers.tiktok.com/doc/content-posting-api-get-started",
        requires=("браузерный режим (playwright)",),
    )
    mode = "manual"

    def check_env(self):
        # ручной режим доступен всегда: файлы и подпись подготовим локально
        return []

    def publish(self, post: Post):
        target = self.ctx.settings.state_dir() / "manual" / "tiktok" / post.id
        target.mkdir(parents=True, exist_ok=True)
        for media in post.media:
            if media.path.exists():
                shutil.copy2(media.path, target / media.path.name)
        (target / "caption.txt").write_text(post.full_text(), encoding="utf-8")
        return self.manual(post, f"TikTok: файлы и подпись подготовлены в {target}")


def create(ctx: PublishContext) -> TikTok:
    return TikTok(ctx)
