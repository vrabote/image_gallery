"""Тесты логики окна: блокноты → план, входные данные, проверка и запуск."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_tk import install  # noqa: E402

from social_publisher.gui import plan_builder as pb  # noqa: E402
from social_publisher.gui import tasks  # noqa: E402
from social_publisher.gui.tasks import AppContext, check_setup, load_setup, save_setup_and_secrets  # noqa: E402


# ---------------------------------------------------------------------------
# блокнот → план
# ---------------------------------------------------------------------------


def test_parse_pad_text_splits_posts_and_takes_title():
    text = (
        "Первый заголовок\n"
        "Текст первого поста,\n"
        "в две строки.\n"
        "---\n"
        "\n"
        "Второй заголовок\n"
        "Текст второго.\n"
    )
    posts = pb.parse_pad_text(text)
    assert len(posts) == 2
    assert posts[0]["title"] == "Первый заголовок"
    assert posts[0]["description"] == "Текст первого поста,\nв две строки."
    assert posts[1]["title"] == "Второй заголовок"


def test_parse_pad_text_no_title_mark():
    posts = pb.parse_pad_text(".\nТолько описание")
    assert posts == [{"title": "", "description": "Только описание", "raw": ".\nТолько описание"}]


def test_parse_pad_text_ignores_empty_tail():
    assert pb.parse_pad_text("Заголовок\n---\n\n") == [
        {"title": "Заголовок", "description": "", "raw": "Заголовок"}
    ]


def test_normalise_tags():
    assert pb.normalise_tags("клип, #тест  ещё") == ["#клип", "#тест", "#ещё"]
    assert pb.normalise_tags(["#a", "a", "b"]) == ["#a", "#b"]
    assert pb.normalise_tags("") == []


def test_build_plan_creates_post_per_service_and_pad_block(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 32)
    photo = tmp_path / "p.jpg"
    photo.write_bytes(b"\xff" * 32)
    document = {
        "services": {
            "youtube": {
                "header": {"title": "Клип", "tags": "клип, хрупкое", "category": "Клипы", "link": ""},
                "media": [str(video)],
                "posts": [],
                "text": "Хрупкое — не кантовать\nОписание клипа.",
            },
            "telegram": {
                "header": {"title": "", "tags": "тест", "category": "", "link": "https://example.com"},
                "media": [str(video)],
                "photo_sources": [{"file": str(photo), "caption": "Подпись к фото"}],
                "posts": [
                    {"title": "Клип в телеге", "description": "Текст"},
                    {"title": "Второй клип", "description": "Ещё текст"},
                ],
                "text": "",
            },
            "vk": {"header": {}, "media": [], "posts": [], "text": "   "},
        },
        "photo_sources": [{"file": str(photo), "caption": ""}],
    }
    plan = pb.build_plan(document)
    posts = plan["posts"]
    assert len(posts) == 3
    assert posts[0]["platforms"] == ["youtube"]
    assert posts[0]["title"] == "Хрупкое — не кантовать"
    assert posts[0]["tags"] == ["#клип", "#хрупкое"]
    assert posts[0]["category"] == "Клипы"
    assert posts[0]["media"] == [str(video)]
    # посты из блокнота: разные id, подпись к фото попала в описание
    telegram_posts = [p for p in posts if p["platforms"] == ["telegram"]]
    assert len(telegram_posts) == 2
    assert telegram_posts[0]["id"] != telegram_posts[1]["id"]
    assert "Подпись к фото" in telegram_posts[0]["description"]
    assert telegram_posts[0]["link"] == "https://example.com"
    # пустой блокнот сервиса не создаёт постов
    assert not [p for p in posts if p["platforms"] == ["vk"]]


def test_build_plan_uses_header_title_when_pad_has_no_title():
    document = {
        "services": {
            "rutube": {
                "header": {"title": "Заголовок из поля", "tags": ""},
                "media": ["C:/videos/a.mp4"],
                "posts": [],
                "text": ".\nОписание без заголовка",
            }
        }
    }
    plan = pb.build_plan(document)
    assert plan["posts"][0]["title"] == "Заголовок из поля"
    assert plan["posts"][0]["description"] == "Описание без заголовка"


# ---------------------------------------------------------------------------
# TOML: запись и обратное чтение
# ---------------------------------------------------------------------------


def test_plan_roundtrip_through_toml(tmp_path):
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"0")
    plan = {
        "posts": [
            {
                "id": "youtube-01-test",
                "title": 'Клип "кавычки" и перенос\nстроки',
                "description": "Текст с обратной \\ и юникодом — ё",
                "tags": ["#клип"],
                "platforms": ["youtube"],
                "media": [str(media)],
            }
        ],
        "defaults": {"tags": []},
    }
    path = pb.write_plan(plan, tmp_path / "plan.toml")
    loaded = pb.load_plan(path)
    assert loaded["posts"][0]["title"] == plan["posts"][0]["title"]
    assert loaded["posts"][0]["description"] == plan["posts"][0]["description"]
    assert loaded["posts"][0]["media"] == [str(media)]


def test_document_from_plan_restores_pads():
    plan = {
        "posts": [
            {
                "id": "a",
                "title": "Первый",
                "description": "Текст",
                "tags": ["#клип"],
                "platforms": ["youtube", "telegram"],
                "media": ["/tmp/clip.mp4"],
            },
            {
                "id": "b",
                "title": "Второй",
                "description": "Текст 2",
                "tags": [],
                "platforms": ["telegram"],
                "media": ["/tmp/photo.jpg"],
            },
        ]
    }
    document = pb.document_from_plan(plan, ["youtube", "telegram", "vk"])
    services = document["services"]
    assert len(services["youtube"]["posts"]) == 1
    assert len(services["telegram"]["posts"]) == 2
    assert "vk" not in services
    assert services["telegram"]["header"]["tags"] == "клип"


# ---------------------------------------------------------------------------
# входные данные
# ---------------------------------------------------------------------------


def test_check_setup_validates_telegram():
    good = {"bot_token": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw", "chat_id": "@mychannel"}
    assert [i for i in check_setup("telegram", good, ".") if i.level == "error"] == []

    bad_token = check_setup("telegram", {"bot_token": "abc", "chat_id": "@mychannel"}, ".")
    assert any("Токен бота" in i.text for i in bad_token)

    bad_chat = check_setup("telegram", {"bot_token": good["bot_token"], "chat_id": "мой канал"}, ".")
    assert any("@канал" in i.text for i in bad_chat)


def test_check_setup_validates_vk_and_youtube(tmp_path):
    assert any("Пустой ключ" in i.text for i in check_setup("vk", {}, tmp_path))
    assert any("цифры" in i.text for i in check_setup("vk", {"access_token": "x" * 30, "group_id": "-abc"}, tmp_path))
    youtube = check_setup("youtube", {}, tmp_path)
    assert any("client_secret.json" in i.text for i in youtube)
    assert any("Войти в Google" in i.text for i in youtube)


def test_save_setup_and_secrets_writes_both_files(tmp_path):
    ctx = AppContext.open(tmp_path)
    values = {
        "telegram": {"bot_token": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw", "chat_id": "@chan"},
        "youtube": {"channel_name": "Мой канал", "client_secret_file": "client_secret.json"},
    }
    paths = save_setup_and_secrets(ctx, values)
    assert len(paths) == 2
    secrets_text = (tmp_path / "secrets.toml").read_text(encoding="utf-8")
    assert "bot_token" in secrets_text and "123456789:AA" in secrets_text
    # необязательные поля не уходят в секреты
    assert "channel_name" not in secrets_text
    saved = load_setup(tmp_path)
    assert saved["youtube"]["channel_name"] == "Мой канал"
    # после сохранения секреты доступны контексту
    assert ctx.reload_secrets().get("telegram", "bot_token").startswith("123456789")


# ---------------------------------------------------------------------------
# проверка плана и публикация (локальный HTTP-сервер вместо Telegram)
# ---------------------------------------------------------------------------


class MiniTelegram:
    """Крошечный сервер, притворяющийся Bot API."""

    def __init__(self):
        from http.server import BaseHTTPRequestHandler, HTTPServer
        import threading

        self.requests: list[str] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                outer.requests.append(self.path)
                body = json.dumps({"ok": True, "result": {"message_id": 7}}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def base(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_exc):
        self.server.shutdown()
        self.server.server_close()


def prepare_ctx(tmp_path: Path, base: str) -> AppContext:
    (tmp_path / "config.toml").write_text(
        f'[telegram]\napi_base = "{base}"\n\n[app]\nstate_dir = "state"\n', encoding="utf-8"
    )
    ctx = AppContext.open(tmp_path)
    save_setup_and_secrets(
        ctx,
        {"telegram": {"bot_token": "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw", "chat_id": "@chan"}},
    )
    return AppContext.open(tmp_path)


def test_check_plan_file_reports_ready_and_missing(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 1024)
    plan = {
        "posts": [
            {"id": "good", "title": "Есть файл", "platforms": ["telegram"], "media": [str(video)]},
            {"id": "bad", "title": "Нет файла", "platforms": ["telegram"], "media": [str(tmp_path / "нет.mp4")]},
        ]
    }
    path = pb.write_plan(plan, tmp_path / "plan.toml")
    with MiniTelegram() as server:
        ctx = prepare_ctx(tmp_path, server.base)
        rows = tasks.check_plan_file(path, ctx)
    by_post: dict[str, list] = {}
    for row in rows:
        by_post.setdefault(row.post_id, []).append(row)
    assert all(row.status == "ok" or "Готово" in row.message for row in by_post["good"])
    assert any(row.status == "error" for row in by_post["bad"])


def test_publish_plan_dry_run_and_real(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 1024)
    plan = {
        "posts": [
            {
                "id": "tg-1",
                "title": "Заголовок",
                "description": "Текст поста",
                "platforms": ["telegram"],
                "media": [str(video)],
            }
        ]
    }
    path = pb.write_plan(plan, tmp_path / "plan.toml")
    with MiniTelegram() as server:
        ctx = prepare_ctx(tmp_path, server.base)
        dry = tasks.publish_plan(path, ctx, dry_run=True)
        assert dry.ok == 0 and not server.requests, "тестовый прогон не должен обращаться к сети"
        real = tasks.publish_plan(path, ctx, mode="api", dry_run=False)
        assert real.ok == 1, [r.message for r in real.results]
        assert any("/sendVideo" in request for request in server.requests)
        # повторный запуск без force — пропуск
        again = tasks.publish_plan(path, ctx, mode="api")
        assert again.skipped == 1


def test_message_queue_and_threads():
    queue = tasks.MessageQueue()
    result = {}

    def work():
        queue.put("log", "шаг 1")
        result["done"] = True
        return 42

    thread = tasks.run_in_thread(work, queue)
    thread.join(timeout=5)
    assert result["done"]
    items = queue.drain()
    assert ("log", "шаг 1") in items and ("done", 42) in items
    assert len(queue) == 0


# ---------------------------------------------------------------------------
# окно целиком (на заглушке tkinter)
# ---------------------------------------------------------------------------


@pytest.fixture()
def tk_env(tmp_path):
    module, messagebox, filedialog = install()
    yield module, messagebox, filedialog, tmp_path
    from social_publisher.gui import main_window

    main_window.App = main_window.App  # модуль остаётся, состояние не общее


def _make_app(tmp_path):
    import importlib

    from social_publisher.gui import main_window

    importlib.reload(main_window)
    app = main_window.App(tmp_path)
    return app


def test_main_window_lists_services(tk_env):
    _module, _mb, _fd, tmp_path = tk_env
    app = _make_app(tmp_path)
    rows = app.tree.get_children()
    assert len(rows) == 7
    assert "youtube" in rows and "tiktok" in rows
    states = {iid: app.tree.rows[iid]["values"][4] for iid in rows}
    assert states["youtube"] == "не заполнен"


def test_main_window_collects_pad_into_plan(tk_env):
    _module, _mb, _fd, tmp_path = tk_env
    app = _make_app(tmp_path)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 512)

    app.open_pad("youtube")
    pad = app.pads["youtube"]
    pad.media = [str(video)]
    pad._refresh_media()
    pad.text.delete("1.0", "end")
    pad.text.insert("1.0", "Хрупкое — не кантовать\nОписание.")
    pad.header_vars["tags"].set("клип, тест")
    app._on_pad_change("youtube")

    path = app.build_and_check()
    assert path is not None and path.exists()
    loaded = pb.load_plan(path)
    assert len(loaded["posts"]) == 1
    post = loaded["posts"][0]
    assert post["title"] == "Хрупкое — не кантовать"
    assert post["platforms"] == ["youtube"]
    assert post["tags"] == ["#клип", "#тест"]
    assert post["media"] == [str(video)]
    # план появился в таблице проверки
    assert app.checks.get_children()


def test_main_window_pad_accepts_only_matching_files(tk_env):
    _module, messagebox, filedialog, tmp_path = tk_env
    app = _make_app(tmp_path)
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"\xff")
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0")
    app.open_pad("youtube")
    pad = app.pads["youtube"]
    filedialog.next_files = (str(image), str(video))
    pad.add_files()
    assert pad.media == [str(video)], "YouTube принимает только видео"
    assert any("только видео" in text.lower() or "принимает видео" in text.lower() for _kind, text in messagebox.answers)


def messagebox_answers(app):
    import sys

    return sys.modules["tkinter.messagebox"].answers


def test_main_window_dry_run_does_not_publish(tk_env):
    _module, _mb, _fd, tmp_path = tk_env
    app = _make_app(tmp_path)
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"0" * 256)
    app.open_pad("telegram")
    pad = app.pads["telegram"]
    pad.media = [str(video)]
    pad._refresh_media()
    pad.text.delete("1.0", "end")
    pad.text.insert("1.0", "Пост в телеграм\nТекст")
    app._on_pad_change("telegram")
    app.build_and_check()
    app.dry_var.set(True)
    app.run_publish()
    # публикации нет, пока не заполнены входные данные — об этом должно быть сообщение
    assert not app.ctx.journal.entries
    assert any("Входные данные" in text or "данные" in text for _kind, text in messagebox_answers(app))


def test_setup_window_saves_values(tk_env):
    from social_publisher.gui import setup_window

    _module, _messagebox, filedialog, tmp_path = tk_env
    app = _make_app(tmp_path)
    window = setup_window.SetupWindow(app, app.ctx, on_saved=lambda: None)
    window.vars["telegram"]["bot_token"].set("123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
    window.vars["telegram"]["chat_id"].set("@mychannel")
    window.vars["vk"]["access_token"].set("vk1.a." + "x" * 40)
    window.vars["vk"]["group_id"].set("1234567")
    window.save()
    secrets = (tmp_path / "secrets.toml").read_text(encoding="utf-8")
    assert "@mychannel" in secrets and "1234567" in secrets
    setup = json.loads((tmp_path / "setup.json").read_text(encoding="utf-8"))
    assert setup["telegram"]["chat_id"] == "@mychannel"
    # проверка показывает готовность
    window.check_all(show_boxes=False)
    texts = [str(call[2].get("text", "")) for call in window.summary.calls if call[0] == "configure"]
    assert any("ошибок" in text for text in texts)


def test_setup_window_reports_bad_telegram_token(tk_env):
    from social_publisher.gui import setup_window

    _module, _messagebox, _fd, tmp_path = tk_env
    app = _make_app(tmp_path)
    window = setup_window.SetupWindow(app, app.ctx, on_saved=None)
    window.vars["telegram"]["bot_token"].set("плохой токен")
    window.vars["telegram"]["chat_id"].set("@chan")
    issues = window.check_all(show_boxes=False)
    assert any("Токен бота" in i.text for i in issues)


def test_all_pads_open_and_keep_separate_content(tk_env):
    _module, _mb, _fd, tmp_path = tk_env
    app = _make_app(tmp_path)
    app.open_all_pads()
    assert len(app.pads) == 7
    for name, pad in app.pads.items():
        pad.text.delete("1.0", "end")
        pad.text.insert("1.0", f"Заголовок {name}\nТекст {name}")
    app.collect_documents()
    for name, data in app.documents.items():
        assert f"Текст {name}" in data["text"]
        assert f"Текст {name}" not in "".join(
            other["text"] for other_name, other in app.documents.items() if other_name != name
        )


def test_journal_window_shows_entries(tk_env):
    _module, _mb, _fd, tmp_path = tk_env
    from social_publisher.core.journal import PublishResult

    app = _make_app(tmp_path)
    app.ctx.journal.append(
        PublishResult(platform="telegram", post_id="p1", status="ok", url="https://t.me/c/1")
    )
    app.show_journal()
    windows = [w for w in app.winfo_children() if hasattr(w, "title")]
    assert windows
