"""Instagram: официальный Graph API требует бизнес-аккаунт и хостинг картинок.

Чтобы не усложнять старт, основной путь — браузерный режим (создание поста в
уже залогиненном браузере). Ручной режим — запасной: пост попадает в журнал как
«опубликовать вручную», а файлы копируются в папку state/manual/instagram/,
чтобы их было удобно перетащить в форму.
"""

from __future__ import annotations

import shutil

from ..core.models import Limits, Post
from .base import Platform, PlatformInfo, PublishContext


class Instagram(Platform):
    info = PlatformInfo(
        name="instagram",
        title="Instagram (посты/Reels)",
        supports_api=False,
        supports_browser=True,
        limits=Limits(
            max_video_seconds=900,
            max_video_mb=1000,
            max_image_mb=8,
            max_images=10,
            max_caption_chars=2200,
            max_tags=30,
            supports_carousel=True,
        ),
        notes="API только для бизнес-аккаунтов и с публичным URL файла; надёжнее — браузерный режим.",
        docs="https://developers.facebook.com/docs/instagram-platform",
        requires=("браузерный режим (playwright)",),
    )
    mode = "manual"

    def check_env(self):
        # ручной режим доступен всегда: файлы и подпись подготовим локально
        return []

    def publish(self, post: Post):
        target = self.ctx.settings.state_dir() / "manual" / "instagram" / post.id
        target.mkdir(parents=True, exist_ok=True)
        copied = []
        for media in post.media:
            if media.path.exists():
                destination = target / media.path.name
                shutil.copy2(media.path, destination)
                copied.append(str(destination))
        caption_file = target / "caption.txt"
        caption_file.write_text(post.full_text(), encoding="utf-8")
        return self.manual(
            post,
            f"Instagram: файлы и подпись подготовлены в {target}",
        )


def create(ctx: PublishContext) -> Instagram:
    return Instagram(ctx)
