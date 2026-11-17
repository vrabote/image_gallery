"""Rutube: загрузка видео через официальный API (нужен доступ издателя).

Rutube выдаёт API-доступ по запросу: напишите в поддержку / менеджеру, чтобы
получить ``X-AUTH-TOKEN`` (он же Authorization: Token …) и, если нужно,
id канала. После этого в secrets.toml:

    [rutube]
    token = "..."       # X-AUTH-TOKEN из личного кабинета
    channel_id = "..."  # опционально

Схема: POST /api/video/upload/ (multipart video_file) → upload_id →
GET /api/video/upload/status/<upload_id>/ пока не готово → публикуем запись.
Адрес API можно переопределить в конфиге ([rutube] api_base), потому что у
Rutube бывают разные контуры доступа (rutube.ru / studio.rutube.ru).
"""

from __future__ import annotations

import time

from ..core.http import HTTPError
from ..core.journal import STATUS_ERROR, STATUS_OK
from ..core.models import Limits, Post
from .base import Platform, PlatformInfo, PublishContext

DEFAULT_API = "https://rutube.ru/api"


class Rutube(Platform):
    info = PlatformInfo(
        name="rutube",
        title="Rutube",
        supports_api=True,
        supports_browser=True,
        limits=Limits(
            max_video_seconds=6 * 3600,
            max_video_mb=10_000,
            max_caption_chars=5000,
            max_title_chars=128,
            max_tags=20,
            supports_images=False,
            supports_video=True,
        ),
        notes="API-доступ Rutube выдаёт по запросу; без токена используйте браузерный режим.",
        docs="https://rutube.ru/info/api/",
        requires=("rutube.token",),
    )

    def __init__(self, ctx: PublishContext):
        super().__init__(ctx)
        self.required_secrets = (("rutube", "token"),)

    @property
    def api_base(self) -> str:
        return str(self.settings.get("rutube.api_base", DEFAULT_API)).rstrip("/")

    def _headers(self) -> dict[str, str]:
        token = self.secrets.require("rutube", "token", "X-AUTH-TOKEN из личного кабинета")
        return {"Authorization": f"Token {token}"}

    def publish(self, post: Post):
        if self.ctx.dry_run:
            return self.dry(post, "Rutube: тестовая публикация, видео не отправлено")
        video = post.main_video
        if video is None:
            return self.skip(post, "Rutube: в посте нет видео")
        try:
            payload = {
                "title": (post.title.strip() or post.title_or_first_line())[:128],
                "description": post.full_text()[:5000],
                "is_hidden": "false",
            }
            category = post.extra.get("rutube_category") or self.settings.get("rutube.category_id")
            if category:
                payload["category"] = str(category)
            channel = self.secrets.get("rutube", "channel_id") or self.settings.get("rutube.channel_id")
            if channel:
                payload["channel_id"] = str(channel)

            response = self.http.post(
                f"{self.api_base}/video/upload/",
                data=payload,
                files=[("video_file", video.path)],
                headers=self._headers(),
                timeout=3600,
            )
            data = self.http.expect_json(response, "Rutube: загрузка видео")
            upload_id = data.get("upload_id") or data.get("id")
            video_id = data.get("video_id") or data.get("id")
            if not upload_id:
                raise HTTPError(f"Rutube: в ответе нет upload_id: {response.text[:400]}")

            self._wait_ready(upload_id)
            url = f"https://rutube.ru/video/{video_id}/" if video_id else ""
            return self.result(
                post,
                STATUS_OK,
                url=url,
                message="Видео загружено на Rutube (модерация/обработка может занять время)",
                post_key=str(video_id or upload_id),
                upload_id=upload_id,
                video_id=video_id,
            )
        except HTTPError as exc:
            return self.fail(post, f"Rutube: {exc}", http_status=exc.status, body=exc.body[:800])
        except Exception as exc:  # pragma: no cover
            return self.fail(post, f"Rutube: {type(exc).__name__}: {exc}")

    def _wait_ready(self, upload_id: str, timeout: float = 1800) -> None:
        deadline = time.monotonic() + timeout
        delay = 5.0
        while time.monotonic() < deadline:
            response = self.http.get(
                f"{self.api_base}/video/upload/status/{upload_id}/",
                headers=self._headers(),
                timeout=60,
            )
            if not response.ok:
                raise HTTPError(
                    f"Rutube: статус загрузки HTTP {response.status}: {response.text[:300]}",
                    status=response.status,
                )
            data = response.json()
            status = str(data.get("status") or data.get("state") or "").lower()
            if status in {"success", "done", "finished", "ready", "processed"}:
                return
            if status in {"error", "failed", "canceled"} or data.get("error"):
                raise HTTPError(f"Rutube: обработка не удалась: {data}")
            if self.http.sleep is time.sleep:
                time.sleep(delay)
            else:
                self.http.sleep(delay)
            delay = min(30.0, delay * 1.5)
        raise HTTPError("Rutube: не дождались готовности видео (можно проверить в кабинете позже)")


def create(ctx: PublishContext) -> Rutube:
    return Rutube(ctx)
