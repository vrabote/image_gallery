"""Telegram: канал или чат через Bot API.

Самый простой канал для старта:
  1. В Telegram: @BotFather → /newbot → получить токен.
  2. Добавить бота в свой канал администратором (права: публикация сообщений).
  3. В secrets.toml: [telegram] bot_token = "123:AAA...", chat_id = "@my_channel"
     (или числовой id вида -1001234567890).

Публикует:
  * видео — с подписью (caption) и обложкой поста;
  * галерею картинок — альбомом (до 10 штук за сообщение);
  * текст с кнопкой-ссылкой, если в посте есть link.
"""

from __future__ import annotations

from ..core.http import HTTPError
from ..core.journal import STATUS_OK
from ..core.models import Limits, Post
from .base import Platform, PlatformInfo, PublishContext

API = "{base}/bot{token}/{method}"
DEFAULT_API_BASE = "https://api.telegram.org"
CAPTION_LIMIT = 1024
ALBUM_LIMIT = 10


class Telegram(Platform):
    info = PlatformInfo(
        name="telegram",
        title="Telegram (канал/чат)",
        supports_api=True,
        supports_browser=False,
        limits=Limits(
            max_video_seconds=3600,
            max_video_mb=2000,
            max_image_mb=10,
            max_images=ALBUM_LIMIT,
            max_caption_chars=CAPTION_LIMIT,
            supports_carousel=True,
        ),
        notes="Бот должен быть администратором канала. Альбом — до 10 файлов за пост.",
        docs="https://core.telegram.org/bots/api",
        requires=("telegram.bot_token", "telegram.chat_id"),
    )

    def __init__(self, ctx: PublishContext):
        super().__init__(ctx)
        self.required_secrets = (("telegram", "bot_token"),)

    def check_env(self):
        from ..core.models import Issue

        issues = list(super().check_env())
        if not self.secrets.get("telegram", "chat_id"):
            issues.append(
                Issue(
                    "error",
                    "Telegram: не задан chat_id (@канал или -100…). "
                    "Впишите [telegram] chat_id в secrets.toml",
                )
            )
        return issues

    # -- вызовы API ---------------------------------------------------------
    def _call(self, method: str, *, params: dict | None = None, files: list | None = None):
        token = self.secrets.require("telegram", "bot_token", "токен от @BotFather")
        base = str(self.settings.get("telegram.api_base", DEFAULT_API_BASE)).rstrip("/")
        url = API.format(base=base, token=token, method=method)
        response = self.http.post(url, data=params or {}, files=files, timeout=600)
        data = self.http.expect_json(response, f"Telegram {method}")
        if not data.get("ok"):
            raise HTTPError(
                f"Telegram {method}: {data.get('description', data)}",
                status=response.status,
                body=response.text,
            )
        return data["result"]

    def _chat_id(self, post: Post):
        return (
            post.extra.get("telegram_chat_id")
            or self.secrets.get("telegram", "chat_id")
            or self.settings.get("telegram.chat_id")
        )

    # -- публикация ---------------------------------------------------------
    def publish(self, post: Post):
        if self.ctx.dry_run:
            return self.dry(post, "Telegram: тестовая публикация, сообщение не отправлено")
        try:
            chat_id = self._chat_id(post)
            if not chat_id:
                return self.fail(post, "Telegram: не задан chat_id")
            caption, keyboard = self._caption(post)
            videos = post.videos
            images = post.images
            if videos:
                return self._publish_video(post, chat_id, videos[0], caption, keyboard)
            if images:
                if len(images) == 1:
                    result = self._call(
                        "sendPhoto",
                        params={
                            "chat_id": chat_id,
                            "caption": caption,
                            "parse_mode": "HTML",
                            "reply_markup": keyboard,
                        },
                        files=[("photo", images[0].path)],
                    )
                    return self._done(post, chat_id, result, "фото")
                return self._publish_album(post, chat_id, images, caption, keyboard)
            result = self._call(
                "sendMessage",
                params={
                    "chat_id": chat_id,
                    "text": caption or post.title_or_first_line(),
                    "parse_mode": "HTML",
                    "reply_markup": keyboard,
                    "disable_web_page_preview": "false",
                },
            )
            return self._done(post, chat_id, result, "текст")
        except HTTPError as exc:
            return self.fail(post, f"Telegram: {exc}", http_status=exc.status)
        except Exception as exc:  # pragma: no cover
            return self.fail(post, f"Telegram: {type(exc).__name__}: {exc}")

    def _publish_video(self, post: Post, chat_id, video, caption: str, keyboard: str):
        params = {
            "chat_id": chat_id,
            "caption": caption,
            "parse_mode": "HTML",
            "supports_streaming": "true",
            "reply_markup": keyboard,
        }
        if video.width and video.height:
            params["width"] = video.width
            params["height"] = video.height
        if video.duration:
            params["duration"] = int(video.duration)
        result = self._call("sendVideo", params=params, files=[("video", video.path)])
        return self._done(post, chat_id, result, "видео")

    def _publish_album(self, post: Post, chat_id, images, caption: str, keyboard: str):
        media = []
        files = []
        for index, image in enumerate(images[:ALBUM_LIMIT]):
            entry = {"type": "photo", "media": f"attach://photo{index}"}
            if index == 0 and caption:
                entry["caption"] = caption
                entry["parse_mode"] = "HTML"
            media.append(entry)
            files.append((f"photo{index}", image.path))
        import json as jsonlib

        params = {"chat_id": chat_id, "media": jsonlib.dumps(media, ensure_ascii=False)}
        results = self._call("sendMediaGroup", params=params, files=files)
        first = results[0] if isinstance(results, list) and results else {}
        if keyboard:
            # кнопку в альбом не вставить — шлём коротким сообщением-дополнением
            try:
                self._call(
                    "sendMessage",
                    params={
                        "chat_id": chat_id,
                        "text": post.link or post.title_or_first_line(),
                        "reply_markup": keyboard,
                        "disable_web_page_preview": "true",
                    },
                )
            except HTTPError:
                pass
        return self._done(post, chat_id, first, f"альбом из {len(media)} фото")

    def _done(self, post: Post, chat_id, result: dict, what: str):
        message_id = result.get("message_id", "")
        chat = str(chat_id).lstrip("@")
        url = ""
        if chat.startswith("-100"):
            url = f"https://t.me/c/{chat[4:]}/{message_id}"
        elif chat and not chat.startswith("-"):
            url = f"https://t.me/{chat}/{message_id}"
        return self.result(
            post,
            STATUS_OK,
            url=url,
            message=f"Отправлено в Telegram ({what})",
            post_key=str(message_id),
            chat_id=str(chat_id),
            message_id=message_id,
        )

    # -- текст --------------------------------------------------------------
    def _caption(self, post: Post) -> tuple[str, str]:
        import html
        import json as jsonlib

        text = post.full_text()
        if post.link:
            text = f"{text}\n\n{post.link}" if text else post.link
        escaped = html.escape(text, quote=False)
        if len(escaped) > CAPTION_LIMIT:
            escaped = escaped[: CAPTION_LIMIT - 1].rsplit(" ", 1)[0] + "…"
        keyboard = ""
        if post.link:
            keyboard = jsonlib.dumps(
                {"inline_keyboard": [[{"text": self.settings.get("telegram.button_text", "Открыть"), "url": post.link}]]},
                ensure_ascii=False,
            )
        return escaped, keyboard


def create(ctx: PublishContext) -> Telegram:
    return Telegram(ctx)
