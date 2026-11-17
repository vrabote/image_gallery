"""Тесты публикатора: локальный HTTP-сервер вместо настоящих площадок.

Запуск:  python -m pytest -q social_publisher/tests     (или python -m unittest)
"""

from __future__ import annotations

import io
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from social_publisher.core.config import Secrets, Settings
from social_publisher.core.http import HTTPClient, encode_multipart
from social_publisher.core.journal import Journal
from social_publisher.core.models import Limits, Media, Plan, Post, probe_media
from social_publisher.core.runner import RunOptions, Runner
from social_publisher.platforms.base import PublishContext, build_registry
from social_publisher.platforms.telegram import Telegram
from social_publisher.platforms.vk import VK
from social_publisher.platforms.youtube import YouTube


# ---------------------------------------------------------------------------
# мини-сервер, который притворяется Telegram / VK / YouTube
# ---------------------------------------------------------------------------


class FakeAPI:
    def __init__(self):
        self.requests: list[dict] = []
        self.vk_upload_photo = False
        self.telegram_message_id = 42
        self.server = HTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    # -- обработчик ---------------------------------------------------------
    def _handler(self):
        api = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def _read(self) -> bytes:
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    return self.rfile.read(length)
                if self.headers.get("Transfer-Encoding") == "chunked":
                    data = b""
                    while True:
                        line = self.rfile.readline().strip()
                        size = int(line, 16)
                        if size == 0:
                            self.rfile.readline()
                            break
                        data += self.rfile.read(size)
                        self.rfile.readline()
                    return data
                return b""

            def _send(self, status: int, payload: dict, headers: dict | None = None):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                api.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
                if "/youtube/v3/channels" in self.path:
                    return self._send(200, {"items": [{"id": "UC123", "snippet": {"title": "Канал"}}]})
                return self._send(200, {"ok": True})

            def do_PUT(self):  # noqa: N802
                body = self._read()
                parsed = urlparse(self.path)
                entry = {
                    "method": "PUT",
                    "path": parsed.path,
                    "query": parse_qs(parsed.query),
                    "headers": dict(self.headers),
                    "body": body,
                    "range": self.headers.get("Content-Range"),
                }
                api.requests.append(entry)
                if parsed.path == "/resumable/abc":
                    return self._send(200, {"id": "VIDEO123"})
                return self._send(404, {"error": "no route"})

            def do_POST(self):  # noqa: N802
                body = self._read()
                parsed = urlparse(self.path)
                entry = {
                    "method": "POST",
                    "path": parsed.path,
                    "query": parse_qs(parsed.query),
                    "headers": dict(self.headers),
                    "body": body,
                }
                api.requests.append(entry)

                if parsed.path.endswith("/oauth2/token") or parsed.path.endswith("/token"):
                    return self._send(200, {"access_token": "ya29.fake", "expires_in": 3600, "refresh_token": "r1"})
                if parsed.path.endswith("/upload/youtube/v3/videos"):
                    return self._send(200, {}, {"Location": f"{api.base}/resumable/abc"})
                if parsed.path == "/resumable/abc":
                    entry["range"] = self.headers.get("Content-Range")
                    return self._send(200, {"id": "VIDEO123"})
                if "/bot" in parsed.path:
                    method = parsed.path.rsplit("/", 1)[-1]
                    if method == "sendMediaGroup":
                        return self._send(
                            200,
                            {"ok": True, "result": [{"message_id": api.telegram_message_id}]},
                        )
                    if method in ("sendVideo", "sendPhoto", "sendMessage"):
                        return self._send(200, {"ok": True, "result": {"message_id": api.telegram_message_id}})
                    return self._send(404, {"ok": False, "description": "unknown"})
                if parsed.path.endswith("/method/wall.post"):
                    return self._send(200, {"response": {"post_id": 777}})
                if parsed.path.endswith("/method/photos.getWallUploadServer"):
                    return self._send(200, {"response": {"upload_url": f"{api.base}/vk-upload"}})
                if parsed.path == "/vk-upload":
                    return self._send(200, {"server": 1, "photo": '[{"id":1}]', "hash": "h"})
                if parsed.path.endswith("/method/photos.saveWallPhoto"):
                    return self._send(200, {"response": [{"owner_id": -1, "id": 55}]})
                if parsed.path.endswith("/method/video.save"):
                    return self._send(
                        200,
                        {"response": {"upload_url": f"{api.base}/vk-video", "video_id": 99, "owner_id": -1}},
                    )
                if parsed.path == "/vk-video":
                    return self._send(200, {"size": 1024, "video_id": 99})
                if parsed.path.endswith("/method/users.get"):
                    return self._send(200, {"response": [{"id": 1}]})
                return self._send(404, {"error": {"error_code": 404, "error_msg": "no route"}})

        return Handler


@pytest.fixture()
def fake_api():
    server = FakeAPI().start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture()
def workspace(tmp_path: Path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"\x00" * 2048)
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"\xff" * 1024)
    return {"dir": tmp_path, "video": video, "image": image}


def make_settings(base: str, tmp_path: Path, **extra) -> Settings:
    data = {
        "app": {"state_dir": str(tmp_path / "state")},
        "telegram": {"api_base": base},
        "vk": {"api_base": base},
        "youtube": {"api_base": base, "token_url": f"{base}/token"},
        "browser": {"enabled": False},
    }
    for key, value in extra.items():
        data[key] = value
    settings = Settings(data, path=tmp_path / "config.toml")
    (tmp_path / "config.toml").write_text("", encoding="utf-8")
    return settings


def make_ctx(settings: Settings, tmp_path: Path, secrets: dict, dry_run: bool = False) -> PublishContext:
    journal = Journal(tmp_path / "state" / "journal.jsonl")
    http = HTTPClient(retries=0, sleep=lambda _s: None)
    return PublishContext(settings=settings, secrets=Secrets(secrets), http=http, journal=journal, dry_run=dry_run)


def make_post(tmp_path: Path, video: Path, image: Path | None = None, **kwargs) -> Post:
    media = [Media.load(str(video), tmp_path)]
    if image:
        media.append(Media.load(str(image), tmp_path))
    return Post(
        id=kwargs.get("id", "p1"),
        title=kwargs.get("title", "Тестовый клип"),
        description=kwargs.get("description", "Описание поста"),
        tags=kwargs.get("tags", ["клип", "тест"]),
        media=media,
        platforms=kwargs.get("platforms", []),
        link=kwargs.get("link", ""),
    )


# ---------------------------------------------------------------------------
# unit: multipart, MP4, лимиты
# ---------------------------------------------------------------------------


def test_encode_multipart_has_fields_and_file(tmp_path: Path):
    path = tmp_path / "a.txt"
    path.write_text("hello", encoding="utf-8")
    content_type, body = encode_multipart({"caption": "привет"}, [("file", path)], boundary="B")
    assert content_type == "multipart/form-data; boundary=B"
    assert b'name="caption"' in body and "привет".encode() in body
    assert b'filename="a.txt"' in body and b"hello" in body
    assert body.rstrip().endswith(b"--B--")


def test_probe_mp4_reads_duration_and_size(tmp_path: Path):
    import struct

    def box(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload) + 8) + kind + payload

    # v0: version/flags(4) + создан(4) + изменён(4) + timescale(4) + duration(4) + …
    mvhd_body = b"\x00" * 12 + struct.pack(">II", 1000, 5000) + b"\x00" * 120
    mvhd = box(b"mvhd", mvhd_body)
    tkhd_body = b"\x00" + b"\x00" * 3 + b"\x00" * 68 + struct.pack(">II", 1080 << 16, 1920 << 16)
    tkhd = box(b"tkhd", tkhd_body)
    trak = box(b"trak", tkhd)
    moov = box(b"moov", mvhd + trak)
    ftyp = box(b"ftyp", b"isom\x00\x00\x02\x00")
    path = tmp_path / "video.mp4"
    path.write_bytes(ftyp + moov)
    probe = probe_media(path)
    assert round(probe["duration"]) == 5
    assert (probe["width"], probe["height"]) == (1080, 1920)


def test_post_check_flags_missing_file_and_limits(tmp_path: Path):
    post = Post(
        id="x",
        title="t",
        media=[
            Media(path=tmp_path / "нет.mp4", kind="video", duration=100, size_bytes=5),
            Media(path=tmp_path / "есть.mp4", kind="video", duration=100, size_bytes=7),
        ],
    )
    (tmp_path / "есть.mp4").write_bytes(b"0" * 7)
    issues = post.check(Limits(max_video_seconds=60, max_images=1, max_caption_chars=10))
    text = " ".join(str(i) for i in issues)
    assert "Файл не найден" in text
    assert "длиннее лимита" in text


def test_plan_defaults_and_tags(tmp_path: Path):
    plan_file = tmp_path / "plan.json"
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"0" * 16)
    plan_file.write_text(
        json.dumps(
            {
                "defaults": {"platforms": ["telegram"], "tags": ["общий"]},
                "posts": [{"id": "a", "title": "Заголовок", "media": ["clip.mp4"]}],
            }
        ),
        encoding="utf-8",
    )
    plan = Plan.load(plan_file)
    post = plan.posts[0]
    assert post.platforms == ["telegram"]
    assert post.tags == ["#общий"]
    assert post.media[0].path == media
    assert plan.for_platform("telegram") == [post]


# ---------------------------------------------------------------------------
# интеграция: Telegram
# ---------------------------------------------------------------------------


def test_telegram_sends_video_and_returns_link(tmp_path, fake_api, workspace):
    settings = make_settings(fake_api.base, tmp_path)
    ctx = make_ctx(settings, tmp_path, {"telegram": {"bot_token": "123:abc", "chat_id": "@mychannel"}})
    platform = Telegram(ctx)
    post = make_post(tmp_path, workspace["video"], platforms=["telegram"])
    result = platform.publish(post)
    assert result.status == "ok", result.message
    assert result.url == "https://t.me/mychannel/42"
    sent = [r for r in fake_api.requests if r["path"].endswith("/sendVideo")]
    assert sent, fake_api.requests
    assert b"clip.mp4" in sent[0]["body"]
    assert sent[0]["headers"]["Content-Type"].startswith("multipart/form-data")


def test_telegram_album_for_images(tmp_path, fake_api, workspace):
    extra = tmp_path / "second.jpg"
    extra.write_bytes(b"\xff" * 512)
    settings = make_settings(fake_api.base, tmp_path)
    ctx = make_ctx(settings, tmp_path, {"telegram": {"bot_token": "1:a", "chat_id": "-100123"}})
    platform = Telegram(ctx)
    post = Post(
        id="album",
        title="Альбом",
        description="Три кадра",
        media=[Media.load(str(workspace["image"]), tmp_path), Media.load(str(extra), tmp_path)],
    )
    result = platform.publish(post)
    assert result.status == "ok", result.message
    assert result.url == "https://t.me/c/123/42"
    album = [r for r in fake_api.requests if r["path"].endswith("/sendMediaGroup")]
    assert album
    assert b"attach://photo0" in album[0]["body"]


def test_dry_run_sends_nothing(tmp_path, fake_api, workspace):
    settings = make_settings(fake_api.base, tmp_path)
    ctx = make_ctx(settings, tmp_path, {"telegram": {"bot_token": "1:a", "chat_id": "@c"}}, dry_run=True)
    post = make_post(tmp_path, workspace["video"])
    result = Telegram(ctx).publish(post)
    assert result.status == "dry-run"
    assert fake_api.requests == []


# ---------------------------------------------------------------------------
# интеграция: VK
# ---------------------------------------------------------------------------


def test_vk_photo_post(tmp_path, fake_api, workspace):
    settings = make_settings(fake_api.base, tmp_path)
    ctx = make_ctx(settings, tmp_path, {"vk": {"access_token": "vk-token", "group_id": "555"}})
    platform = VK(ctx)
    post = make_post(tmp_path, workspace["image"], image=workspace["image"])
    post.media = [Media.load(str(workspace["image"]), tmp_path)]
    result = platform.publish(post)
    assert result.status == "ok", result.message
    assert result.url == "https://vk.com/wall-555_777"
    wall = [r for r in fake_api.requests if r["path"].endswith("/wall.post")][0]
    assert "photo-1_55" in wall["body"].decode("utf-8", "replace")


def test_vk_video_attachment(tmp_path, fake_api, workspace):
    settings = make_settings(fake_api.base, tmp_path)
    ctx = make_ctx(settings, tmp_path, {"vk": {"access_token": "t", "group_id": "1"}})
    post = make_post(tmp_path, workspace["video"])
    result = VK(ctx).publish(post)
    assert result.status == "ok", result.message
    wall = [r for r in fake_api.requests if r["path"].endswith("/wall.post")][0]
    assert "video-1_99" in wall["body"].decode("utf-8", "replace")


# ---------------------------------------------------------------------------
# интеграция: YouTube (resumable)
# ---------------------------------------------------------------------------


def test_youtube_resumable_upload(tmp_path, fake_api, workspace):
    settings = make_settings(fake_api.base, tmp_path)
    settings.data["youtube"].update({"client_id": "cid", "client_secret": "sec"})
    ctx = make_ctx(settings, tmp_path, {"youtube": {}})
    platform = YouTube(ctx)
    platform.save_token("oauth_google", {"access_token": "ya29.x", "expires_in": 3600, "obtained_at": 4102444800, "refresh_token": "r"})
    post = make_post(tmp_path, workspace["video"], title="Клип про хрупкое", tags=["клип"])
    post.category = "Клипы"
    result = platform.publish(post)
    assert result.status == "ok", result.message
    assert result.url == "https://youtu.be/VIDEO123"
    init = [r for r in fake_api.requests if r["path"].endswith("/upload/youtube/v3/videos")][0]
    assert init["query"]["uploadType"] == ["resumable"]
    payload = json.loads(init["body"])["snippet"]
    assert payload["title"] == "Клип про хрупкое"
    piece = [r for r in fake_api.requests if r["path"] == "/resumable/abc"][0]
    assert piece["range"] == "bytes 0-2047/2048"
    assert piece["body"] == b"\x00" * 2048


def test_youtube_missing_credentials_reported(tmp_path):
    settings = Settings({"app": {"state_dir": str(tmp_path / "state")}, "browser": {"enabled": False}}, path=tmp_path / "c.toml")
    ctx = make_ctx(settings, tmp_path, {})
    issues = str(YouTube(ctx).check_env())
    assert "client_id" in issues


# ---------------------------------------------------------------------------
# runner: подтверждение, журнал, повторный запуск
# ---------------------------------------------------------------------------


def test_runner_confirm_and_idempotency(tmp_path, fake_api, workspace):
    settings = make_settings(fake_api.base, tmp_path)
    ctx = make_ctx(settings, tmp_path, {"telegram": {"bot_token": "1:a", "chat_id": "@c"}})
    registry = build_registry(ctx)
    post = make_post(tmp_path, workspace["video"], platforms=["telegram"])
    plan = Plan(posts=[post], path=tmp_path / "plan.json")

    asked: list[str] = []
    runner = Runner(registry, ctx.journal, echo=lambda _m: None, confirm=lambda q: asked.append(q) or True)
    report = runner.run(plan, RunOptions(mode="api", assume_yes=False))
    assert report.ok == 1 and asked, "должен быть задан вопрос подтверждения"

    # второй запуск без --force не публикует повторно
    report2 = runner.run(plan, RunOptions(mode="api", assume_yes=True))
    assert report2.ok == 0 and report2.skipped == 1
    assert ctx.journal.published("telegram", "p1") is not None

    # с --force публикует снова
    report3 = runner.run(plan, RunOptions(mode="api", assume_yes=True, force=True))
    assert report3.ok == 1


def test_runner_declined_confirmation_is_manual(tmp_path):
    settings = Settings({"app": {"state_dir": str(tmp_path / "state")}, "browser": {"enabled": False}}, path=tmp_path / "c.toml")
    ctx = make_ctx(settings, tmp_path, {"telegram": {"bot_token": "1:a", "chat_id": "@c"}})
    registry = build_registry(ctx)
    post = Post(id="x", title="t", description="d")
    plan = Plan(posts=[post], path=tmp_path / "p.json")
    runner = Runner(registry, ctx.journal, echo=lambda _m: None, confirm=lambda _q: False)
    report = runner.run(plan, RunOptions(mode="api"))
    assert report.manual == 1
    assert ctx.journal.entries[0].status == "manual"


def test_runner_reports_error_for_unconfigured_platform(tmp_path, workspace):
    settings = Settings({"app": {"state_dir": str(tmp_path / "state")}, "browser": {"enabled": False}}, path=tmp_path / "c.toml")
    ctx = make_ctx(settings, tmp_path, {})
    registry = build_registry(ctx)
    post = make_post(tmp_path, workspace["video"], platforms=["vk"])
    plan = Plan(posts=[post], path=tmp_path / "p.json")
    report = Runner(registry, ctx.journal, echo=lambda _m: None).run(plan, RunOptions(mode="api"))
    assert report.errors == 1
    assert "не настроено" in ctx.journal.entries[0].message


# ---------------------------------------------------------------------------
# браузерный режим: фейковая страница вместо настоящего браузера
# ---------------------------------------------------------------------------


class FakeLocator:
    def __init__(self, page: "FakePage", selector: str):
        self.page = page
        self.selector = selector
        self.first = self

    def wait_for(self, state: str = "visible", timeout: int = 0):
        if self.selector not in self.page.dom:
            raise RuntimeError(f"нет элемента {self.selector}")
        self.page.log.append(("wait", self.selector))

    def click(self, timeout: int = 0, force: bool = False):
        self.page.log.append(("click", self.selector))

    def fill(self, value: str):
        self.page.dom[self.selector] = value
        self.page.log.append(("fill", self.selector, value))

    def set_input_files(self, files):
        self.page.files.append([str(f) for f in files])
        self.page.log.append(("files", self.selector, [Path(f).name for f in files]))


class FakeKeyboard:
    def __init__(self, page):
        self.page = page

    def press(self, key):
        self.page.log.append(("press", key))

    def type(self, text):
        self.page.log.append(("type", text))


class FakePage:
    def __init__(self, dom: dict, url: str = "https://example.test/"):
        self.dom = dom
        self.url = url
        self.log: list[tuple] = []
        self.files: list[list[str]] = []
        self.keyboard = FakeKeyboard(self)

    def goto(self, url, wait_until=None):
        self.url = url
        self.log.append(("goto", url))

    def locator(self, selector):
        return FakeLocator(self, selector)

    def wait_for_timeout(self, ms):
        return None

    def set_default_timeout(self, ms):
        return None

    def screenshot(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"png")

    def evaluate(self, script):
        return {}


class FakeSession:
    def __init__(self, page):
        self.page_obj = page
        self.closed = False

    def page(self):
        return self.page_obj

    def screenshot(self, page, name):
        return page.screenshot("/tmp/x.png")

    def close(self):
        self.closed = True


def test_browser_mode_fills_and_publishes(tmp_path, workspace):
    from social_publisher.platforms import browser as browser_mod

    settings = Settings(
        {
            "app": {"state_dir": str(tmp_path / "state")},
            "browser": {"enabled": True, "timeout_ms": 1000, "result_timeout_ms": 1000},
        },
        path=tmp_path / "config.toml",
    )
    page = FakePage(
        dom={
            "input[type=file]": "",
            "input[name='title']": "",
            "textarea[name='description']": "",
            "button:has-text('Опубликовать')": "",
        }
    )
    session = FakeSession(page)
    ctx = make_ctx(settings, tmp_path, {"rutube": {"token": "t"}})
    platform = browser_mod.BrowserPlatform(ctx, "rutube", session)
    plan_profile = {
        "title": "Rutube",
        "url": "https://studio.example/upload",
        "file_input": ["input[type=file]"],
        "file_kinds": ["video"],
        "file_limit": 1,
        "title_selector": ["input[name='title']"],
        "description": ["textarea[name='description']"],
        "publish_button": ["button:has-text('Опубликовать')"],
        "success": [],
        "limits": {"max_title_chars": 128},
    }
    platform.profile = plan_profile

    post = make_post(tmp_path, workspace["video"], title="Хрупкое", tags=["клип"])
    result = platform.publish(post)
    assert result.status == "ok", result.message
    assert ("goto", "https://studio.example/upload") == page.log[0]
    assert page.files and page.files[0][0].endswith("clip.mp4")
    fills = [entry for entry in page.log if entry[0] == "fill"]
    assert fills and fills[0][1] == "input[name='title']" and fills[0][2] == "Хрупкое"
    assert any(entry[0] == "click" and "Опубликовать" in entry[1] for entry in page.log)
    assert result.mode == "browser"


def test_browser_mode_dry_run_does_not_open_browser(tmp_path, workspace):
    from social_publisher.platforms import browser as browser_mod

    settings = Settings({"app": {"state_dir": str(tmp_path / "state")}}, path=tmp_path / "config.toml")
    page = FakePage(dom={})
    ctx = make_ctx(settings, tmp_path, {}, dry_run=True)
    platform = browser_mod.BrowserPlatform(ctx, "rutube", FakeSession(page))
    platform.profile = {"title": "Rutube", "url": "https://x.test"}
    result = platform.publish(make_post(tmp_path, workspace["video"]))
    assert result.status == "dry-run"
    assert page.log == []


def test_browser_mode_respects_declined_confirmation(tmp_path, workspace):
    from social_publisher.platforms import browser as browser_mod

    settings = Settings(
        {"app": {"state_dir": str(tmp_path / "state")}, "browser": {"timeout_ms": 1000}},
        path=tmp_path / "config.toml",
    )
    page = FakePage(
        dom={"input[type=file]": "", "textarea[name='description']": "", "button:has-text('Опубликовать')": ""}
    )
    ctx = make_ctx(settings, tmp_path, {})
    ctx.confirm = lambda _q: False
    platform = browser_mod.BrowserPlatform(ctx, "rutube", FakeSession(page))
    platform.profile = {
        "title": "Rutube",
        "url": "https://x.test",
        "file_input": ["input[type=file]"],
        "description": ["textarea[name='description']"],
        "publish_button": ["button:has-text('Опубликовать')"],
    }
    result = platform.publish(make_post(tmp_path, workspace["video"]))
    assert result.status == "manual"
    assert not any(entry[0] == "click" and "Опубликовать" in entry[1] for entry in page.log)
