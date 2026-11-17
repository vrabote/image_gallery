"""YouTube через официальный YouTube Data API v3.

Что нужно один раз сделать руками (5–10 минут):
  1. https://console.cloud.google.com — создать проект, включить
     «YouTube Data API v3».
  2. Экран согласия OAuth: тип «Внешний», добавить себя в тестовые
     пользователи, scope https://www.googleapis.com/auth/youtube.upload.
  3. Учётные данные → «OAuth client ID» → тип «Desktop app» → скачать JSON.
  4. Положить client_secret.json рядом с config.toml и запустить
     ``python -m social_publisher auth youtube`` (откроется браузер).

Загрузка идёт «возобновляемым» протоколом: файл читается с диска кусками,
при обрыве связи загрузка продолжается с того же байта, а не с нуля.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
from pathlib import Path
from typing import Any

from ..core.http import HTTPError
from ..core.journal import STATUS_ERROR, STATUS_OK
from ..core.models import Limits, Post
from .base import Platform, PlatformInfo, PublishContext

DEFAULT_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
DEFAULT_TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_API_BASE = "https://www.googleapis.com"
SCOPE = "https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly"
TOKEN_KEY = "oauth_google"

# Категории YouTube (русские подписи → id)
CATEGORIES = {
    "авто": "2",
    "автомобили": "2",
    "музыка": "10",
    "животные": "15",
    "питомцы": "15",
    "спорт": "17",
    "путешествия": "19",
    "игры": "20",
    "люди": "22",
    "блог": "22",
    "юмор": "23",
    "развлечения": "24",
    "новости": "25",
    "политика": "25",
    "как сделать": "26",
    "инструкции": "26",
    "образование": "27",
    "наука": "28",
    "стиль": "26",
}


class YouTube(Platform):
    info = PlatformInfo(
        name="youtube",
        title="YouTube (клипы и видео)",
        supports_api=True,
        supports_browser=True,
        limits=Limits(
            max_video_seconds=12 * 3600,
            max_video_mb=256_000,
            max_caption_chars=5000,
            max_title_chars=100,
            max_tags=500,
            supports_images=False,
            supports_video=True,
        ),
        notes="Shorts публикуются как обычное видео: вертикальный ролик до 3 минут YouTube сам покажет в Shorts.",
        docs="https://developers.google.com/youtube/v3/guides/using_resumable_upload_protocol",
        requires=("youtube.client_secret", "auth youtube"),
    )
    required_secrets: tuple[tuple[str, str], ...] = ()

    def __init__(self, ctx: PublishContext):
        super().__init__(ctx)
        self._token: dict[str, Any] | None = None
        self._channel: dict[str, Any] | None = None

    # -- авторизация --------------------------------------------------------
    def _client(self) -> dict[str, Any]:
        client_id = self.secrets.get("youtube", "client_id")
        client_secret = self.secrets.get("youtube", "client_secret")
        if client_id and client_secret:
            return {"client_id": client_id, "client_secret": client_secret}
        candidates = [
            self.secrets.get("youtube", "client_secret_file"),
            str(self.settings.home / "client_secret.json"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = self.settings.resolve(candidate)
            if path.exists():
                data = json.loads(path.read_text("utf-8-sig"))
                block = data.get("installed") or data.get("web") or data
                return {
                    "client_id": block.get("client_id", ""),
                    "client_secret": block.get("client_secret", ""),
                    "file": str(path),
                }
        return {}

    def check_env(self):
        from ..core.models import Issue

        client = self._client()
        if not client.get("client_id"):
            return [
                Issue(
                    "error",
                    "YouTube: нет client_id/client_secret. Скачайте OAuth client (Desktop) "
                    "в Google Cloud, положите client_secret.json рядом с config.toml "
                    "или впишите [youtube] client_id/client_secret в secrets.toml",
                )
            ]
        if not self.saved_token(TOKEN_KEY).get("refresh_token"):
            return [
                Issue(
                    "error",
                    "YouTube: нужен вход в аккаунт. Выполните: python -m social_publisher auth youtube",
                )
            ]
        return []

    def auth(self, open_browser: bool = True) -> dict[str, Any]:
        """Пройти OAuth «для десктопа»: localhost-редирект + code exchange."""
        import http.server
        import socket
        import threading
        import webbrowser

        client = self._client()
        if not client.get("client_id"):
            raise RuntimeError("Нет client_id/client_secret для YouTube")

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        redirect_uri = f"http://127.0.0.1:{port}/"
        result: dict[str, str] = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                result.update({k: v[0] for k, v in query.items()})
                body = "Можно закрыть эту вкладку и вернуться в терминал.".encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):  # тишина в консоли
                return

        server = http.server.HTTPServer(("127.0.0.1", port), Handler)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        params = {
            "client_id": client["client_id"],
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            "prompt": "consent",
        }
        auth_url = self.settings.get("youtube.auth_url", DEFAULT_AUTH_URL)
        url = f"{auth_url}?{urllib.parse.urlencode(params)}"
        print("Откройте ссылку и разрешите доступ:\n")
        print(url)
        if open_browser:
            try:
                webbrowser.open(url)
            except Exception:  # pragma: no cover
                pass
        thread.join(timeout=600)
        server.server_close()
        if "code" not in result:
            raise RuntimeError(f"Код авторизации не получен: {result}")
        return self._exchange(
            {
                "code": result["code"],
                "client_id": client["client_id"],
                "client_secret": client["client_secret"],
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
        )

    def _exchange(self, payload: dict[str, str]) -> dict[str, Any]:
        token_url = self.settings.get("youtube.token_url", DEFAULT_TOKEN_URL)
        response = self.http.post(token_url, data=payload)
        if not response.ok:
            raise HTTPError(
                f"Токен не получен: HTTP {response.status} {response.text[:300]}",
                status=response.status,
                body=response.text,
            )
        token = response.json()
        token["obtained_at"] = int(time.time())
        if "refresh_token" not in token:
            previous = self.saved_token(TOKEN_KEY).get("refresh_token")
            if previous:
                token["refresh_token"] = previous
        self.save_token(TOKEN_KEY, token)
        self._token = token
        return token

    def access_token(self, force_refresh: bool = False) -> str:
        token = self._token or self.saved_token(TOKEN_KEY)
        if not token:
            raise HTTPError("YouTube: нет токена, выполните auth youtube")
        expires_at = int(token.get("obtained_at", 0)) + int(token.get("expires_in", 3600)) - 120
        if force_refresh or int(time.time()) >= expires_at:
            client = self._client()
            token = self._exchange(
                {
                    "client_id": client["client_id"],
                    "client_secret": client["client_secret"],
                    "refresh_token": token.get("refresh_token", ""),
                    "grant_type": "refresh_token",
                }
            )
        self._token = token
        return token["access_token"]

    def channel(self) -> dict[str, Any]:
        if self._channel is not None:
            return self._channel
        response = self.http.get(
            f"{self._api_base()}/youtube/v3/channels",
            params={"part": "snippet,contentDetails", "mine": "true"},
            headers={"Authorization": f"Bearer {self.access_token()}"},
        )
        if response.status == 401:
            self.access_token(force_refresh=True)
            return self.channel()
        data = self.http.expect_json(response, "YouTube: не удалось получить канал")
        items = data.get("items") or []
        if not items:
            raise HTTPError("YouTube: у аккаунта нет канала")
        self._channel = items[0]
        return self._channel

    # -- публикация ---------------------------------------------------------
    def publish(self, post: Post):
        if self.ctx.dry_run:
            return self.dry(post, "YouTube: тестовая публикация, видео не отправлено")
        video = post.main_video
        if video is None:
            return self.skip(post, "YouTube: в посте нет видео")
        if not video.path.exists():
            return self.fail(post, f"Файл не найден: {video.path}")
        try:
            body = {
                "snippet": {
                    "title": self._title(post),
                    "description": self._description(post),
                    "tags": [t.lstrip("#") for t in post.tags][:50],
                    "categoryId": self._category(post),
                    "defaultLanguage": self.settings.get("youtube.language", "ru"),
                },
                "status": {
                    "privacyStatus": self._privacy(post),
                    "selfDeclaredMadeForKids": bool(self.settings.get("youtube.made_for_kids", False)),
                    "embeddable": True,
                },
            }
            playlist = self._playlist_id(post)
            if playlist:
                body["snippet"]["playlistId"] = playlist
            video_id = self._upload(video.path, body)
            url = f"https://youtu.be/{video_id}"
            message = "Опубликовано на YouTube"
            if self._privacy(post) == "private":
                message = "Загружено на YouTube как «доступ по ссылке/приватное» — проверьте в Студии"
            return self.result(
                post,
                STATUS_OK,
                url=url,
                message=message,
                post_key=video_id,
                video_id=video_id,
                title=body["snippet"]["title"],
            )
        except HTTPError as exc:
            return self.fail(post, f"YouTube: {exc}", http_status=exc.status, body=exc.body[:1200])
        except Exception as exc:  # pragma: no cover - защита от неожиданного
            return self.fail(post, f"YouTube: {type(exc).__name__}: {exc}")

    def _upload(self, path: Path, body: dict[str, Any]) -> str:
        size = path.stat().st_size
        token = self.access_token()
        upload_url = f"{self._api_base()}/upload/youtube/v3/videos"
        init_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Length": str(size),
            "X-Upload-Content-Type": "video/*",
        }
        response = self.http.post(
            upload_url,
            params={"part": "snippet,status", "uploadType": "resumable"},
            headers=init_headers,
            json=body,
            timeout=120,
        )
        if response.status == 401:
            token = self.access_token(force_refresh=True)
            init_headers["Authorization"] = f"Bearer {token}"
            response = self.http.post(
                upload_url,
                params={"part": "snippet,status", "uploadType": "resumable"},
                headers=init_headers,
                json=body,
                timeout=120,
            )
        if not response.ok:
            raise HTTPError(
                f"сессия загрузки не создана (HTTP {response.status}): {response.text[:400]}",
                status=response.status,
                body=response.text,
            )
        session_url = response.header("location")
        if not session_url:
            raise HTTPError("YouTube не вернул адрес сессии загрузки")

        offset = 0
        stalls = 0
        while offset < size:
            # отправляем максимум 32 МБ за раз — так проще докачивать
            chunk = min(32 * 1024 * 1024, size - offset)
            put = self.http.put_stream(
                session_url,
                path,
                offset=offset,
                length=chunk,
                headers={
                    "Content-Range": f"bytes {offset}-{offset + chunk - 1}/{size}",
                    "Content-Type": "video/*",
                },
                timeout=900,
            )
            if put.status in (200, 201):
                data = put.json()
                video_id = data.get("id", "")
                if not video_id:
                    raise HTTPError(f"YouTube: в ответе нет id видео: {put.text[:300]}")
                return video_id
            if put.status == 308:  # продолжаем
                range_header = put.header("range")
                if range_header and "-" in range_header:
                    offset = int(range_header.split("-")[-1]) + 1
                else:
                    offset += chunk
                stalls = 0
                continue
            if put.status in (500, 502, 503, 504) or put.status == 429:
                stalls += 1
                if stalls > 6:
                    raise HTTPError(f"загрузка не идёт: HTTP {put.status}")
                self.http.sleep(min(30, 2 ** stalls))
                # узнаём, сколько сервер уже принял
                status = self.http.put_stream(session_url, path, offset=0, length=1, headers={"Content-Range": f"bytes */{size}"})
                range_header = status.header("range")
                if range_header and "-" in range_header:
                    offset = int(range_header.split("-")[-1]) + 1
                continue
            raise HTTPError(
                f"ошибка загрузки HTTP {put.status}: {put.text[:400]}",
                status=put.status,
                body=put.text,
            )
        raise HTTPError("загрузка завершилась без идентификатора видео")

    # -- поля ---------------------------------------------------------------
    def _api_base(self) -> str:
        return str(self.settings.get("youtube.api_base", DEFAULT_API_BASE)).rstrip("/")

    def _title(self, post: Post) -> str:
        title = post.title.strip() or post.title_or_first_line()
        title = " ".join(title.split())
        return title[:100] or post.id

    def _description(self, post: Post) -> str:
        text = post.full_text()
        limit = 4900
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def _privacy(self, post: Post) -> str:
        value = post.extra.get("privacy") or self.settings.get("youtube.privacy", "public")
        value = str(value).lower()
        return value if value in {"public", "unlisted", "private"} else "public"

    def _category(self, post: Post) -> str:
        raw = post.extra.get("youtube_category") or self.settings.get("youtube.category", "22")
        raw_str = str(raw).strip()
        if raw_str.isdigit():
            return raw_str
        return CATEGORIES.get(raw_str.lower(), "22")

    def _playlist_id(self, post: Post) -> str:
        name = post.category.strip()
        if not name:
            return ""
        playlists = self.settings.get("youtube.playlists", {}) or {}
        return str(playlists.get(name, ""))


def create(ctx: PublishContext) -> YouTube:
    return YouTube(ctx)
