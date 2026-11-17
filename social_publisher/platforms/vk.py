"""VK (ВКонтакте): стена сообщества или личной страницы через VK API.

Что нужно:
  1. Создать Standalone-приложение на https://dev.vk.com (тип «Standalone»).
  2. Получить ключ доступа с правами wall, photos, video, offline — проще всего
     кнопкой «Получить токен» в настройках приложения. Для сообщества удобно
     получить токен сообщества (Управление → Работа с API → Ключи доступа).
  3. В secrets.toml: [vk] access_token = "...", group_id = "1234567" (без минуса).
     Для личной страницы оставьте group_id пустым.

Публикует: видео с описанием, фото-альбом (до 10 фото) с текстом, только текст.
"""

from __future__ import annotations

import json

from ..core.http import HTTPError
from ..core.journal import STATUS_OK
from ..core.models import Limits, Post
from .base import Platform, PlatformInfo, PublishContext

API = "{base}/method/{method}"
DEFAULT_API_BASE = "https://api.vk.com"
VERSION = "5.199"
ALBUM_LIMIT = 10


class VK(Platform):
    info = PlatformInfo(
        name="vk",
        title="ВКонтакте (стена сообщества/страницы)",
        supports_api=True,
        supports_browser=False,
        limits=Limits(
            max_video_seconds=None,
            max_video_mb=None,
            max_image_mb=50,
            max_images=ALBUM_LIMIT,
            max_caption_chars=16000,
            supports_carousel=True,
        ),
        notes="Нужен токен с правами wall, photos, video. Для группы укажите group_id.",
        docs="https://dev.vk.com/method/wall.post",
        requires=("vk.access_token",),
    )

    def __init__(self, ctx: PublishContext):
        super().__init__(ctx)
        self.required_secrets = (("vk", "access_token"),)

    # -- вызовы -------------------------------------------------------------
    def _api(self, method: str, params: dict | None = None, *, files: list | None = None, token: str | None = None):
        data = dict(params or {})
        data["access_token"] = token or self.secrets.require("vk", "access_token", "токен VK API")
        data["v"] = VERSION
        base = str(self.settings.get("vk.api_base", DEFAULT_API_BASE)).rstrip("/")
        response = self.http.post(API.format(base=base, method=method), data=data, files=files, timeout=600)
        payload = response.json() if response.body else {}
        if isinstance(payload, dict) and payload.get("error"):
            error = payload["error"]
            raise HTTPError(
                f"VK {method}: {error.get('error_msg')} (код {error.get('error_code')})",
                status=response.status,
                body=response.text,
            )
        return self.http.expect_json(response, f"VK {method}")

    # -- публикация ---------------------------------------------------------
    def publish(self, post: Post):
        if self.ctx.dry_run:
            return self.dry(post, "VK: тестовая публикация, запись не создана")
        try:
            owner_id = self._owner_id()
            group_id = self.settings_or_secret("vk", "group_id")
            attachments: list[str] = []

            if post.main_video is not None and self.settings.get("vk.upload_video", True):
                url = self._upload_video(post.main_video.path, post)
                if url:
                    attachments.append(url)
            if post.images:
                attachments.extend(self._upload_photos(post, owner_id, group_id))

            message = self._message(post)
            params: dict = {"owner_id": owner_id, "message": message, "from_group": 1 if group_id else 0}
            if attachments:
                params["attachments"] = ",".join(attachments)
            if post.link:
                params["attachments"] = ",".join(attachments + [post.link]).strip(",")
            payload = self._api("wall.post", params)
            result = payload.get("response") if isinstance(payload.get("response"), dict) else payload
            post_id = result.get("post_id")
            url = f"https://vk.com/wall{owner_id}_{post_id}" if post_id else ""
            return self.result(
                post,
                STATUS_OK,
                url=url,
                message="Запись в VK создана",
                post_key=str(post_id or ""),
                owner_id=owner_id,
                post_id=post_id,
            )
        except HTTPError as exc:
            return self.fail(post, str(exc), http_status=exc.status)
        except Exception as exc:  # pragma: no cover
            return self.fail(post, f"VK: {type(exc).__name__}: {exc}")

    def _owner_id(self) -> int:
        group = self.settings_or_secret("vk", "group_id")
        if group:
            return -int(str(group).lstrip("-"))
        user_id = self.secrets.get("vk", "user_id") or self.settings.get("vk.user_id")
        if user_id:
            return int(user_id)
        # узнаём владельца токена
        data = self._api("users.get", {})
        items = data.get("response") or []
        if not items:
            raise HTTPError("VK: не удалось определить пользователя по токену")
        return int(items[0]["id"])

    def _message(self, post: Post) -> str:
        text = post.full_text(with_tags=False)
        if post.tags:
            text = f"{text}\n\n{post.hashtags}".strip()
        if post.link:
            text = f"{text}\n{post.link}".strip()
        return text[:16000]

    def _upload_photos(self, post: Post, owner_id: int, group_id: str | None) -> list[str]:
        attachments = []
        for image in post.images[:ALBUM_LIMIT]:
            server = self._api("photos.getWallUploadServer", {"group_id": group_id or None})
            upload_url = server["response"]["upload_url"]
            uploaded = self.http.post(upload_url, files=[("photo", image.path)])
            payload = uploaded.json()
            saved = self._api(
                "photos.saveWallPhoto",
                {
                    "group_id": group_id or None,
                    "server": payload.get("server"),
                    "photo": payload.get("photo"),
                    "hash": payload.get("hash"),
                },
            )
            for item in saved.get("response", []):
                attachments.append(f"photo{item['owner_id']}_{item['id']}")
        return attachments

    def _upload_video(self, path, post: Post) -> str:
        """Загрузить видео и вернуть attachment вида video-123_456."""
        group_id = self.settings_or_secret("vk", "group_id")
        save = self._api(
            "video.save",
            {
                "group_id": group_id or None,
                "name": post.title_or_first_line()[:128],
                "description": post.full_text()[:5000],
                "wallpost": 0,
                "is_private": 0,
            },
        )
        response = save.get("response") or {}
        upload_url = response.get("upload_url")
        video_id = response.get("video_id")
        owner = response.get("owner_id")
        if not upload_url or not video_id:
            raise HTTPError(f"VK video.save: неожиданный ответ {json.dumps(response)[:300]}")
        uploaded = self.http.post(upload_url, files=[("video_file", path)], timeout=1800)
        payload = uploaded.json()
        if payload.get("size") in (0, "0") and not payload.get("video_id"):
            raise HTTPError(f"VK: видео не загрузилось: {uploaded.text[:300]}")
        return f"video{owner}_{video_id}"

    def settings_or_secret(self, section: str, key: str):
        """Секрет главнее настройки; настройка нужна браузерному режиму."""
        return self.secrets.get(section, key) or self.settings.get(f"{section}.{key}")


def create(ctx: PublishContext) -> VK:
    return VK(ctx)
