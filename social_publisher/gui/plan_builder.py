"""Сборка плана публикаций из блокнотов и запись/чтение plan.toml.

Чистые функции без tkinter и сети: их проверяют тесты, а окно только
передаёт данные.

Модель «документ» (то, что набрано в окнах-блокнотах):

    {
      "services": {
        "youtube": {
          "header": {"title": "...", "tags": "клип, тест", "category": "Клипы", "link": ""},
          "media": ["C:/clips/a.mp4", "C:/clips/b.mp4"],
          "photo_sources": [{"file": "C:/photos/1.jpg", "caption": "подпись"}],
          "posts": [{"title": "...", "description": "..."}],
        },
        ...
      }
    }
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SEPARATOR_RE = re.compile(r"^\s*(?:-{3,}|—{3,}|={3,})\s*$")


# ---------------------------------------------------------------------------
# разбор текста блокнота
# ---------------------------------------------------------------------------


def split_posts(text: str) -> list[str]:
    """Разделить текст блокнота на посты по строкам «---»."""
    blocks: list[list[str]] = [[]]
    for line in (text or "").splitlines():
        if SEPARATOR_RE.match(line):
            blocks.append([])
        else:
            blocks[-1].append(line)
    return ["\n".join(block).strip() for block in blocks]


#: первая строка «.» означает «у поста нет заголовка, бери из общего поля»
NO_TITLE_MARK = "."


def parse_post(block: str) -> dict[str, str]:
    """Первую непустую строку считаем заголовком, остальное — описанием.

    Если первая непустая строка — просто «.», заголовка нет (берётся из
    общего поля «Заголовок»).
    """
    lines = [line for line in (block or "").splitlines()]
    title = ""
    description_lines: list[str] = []
    seen_title = False
    for line in lines:
        stripped = line.strip()
        if not seen_title:
            if not stripped:
                continue
            candidate = stripped.lstrip("#").strip()
            seen_title = True
            if candidate == NO_TITLE_MARK:
                continue
            title = candidate
            continue
        description_lines.append(line)
    description = "\n".join(description_lines).strip()
    return {"title": title, "description": description, "raw": (block or "").strip()}


def parse_pad_text(text: str) -> list[dict[str, str]]:
    """Разобрать текст блокнота на список постов (пустые куски пропускаются)."""
    posts = []
    for block in split_posts(text):
        if not block.strip():
            continue
        parsed = parse_post(block)
        if parsed["title"] or parsed["description"]:
            posts.append(parsed)
    return posts


# ---------------------------------------------------------------------------
# вспомогательное
# ---------------------------------------------------------------------------


def normalise_tags(raw: Any) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        items = re.split(r"[,\s]+", raw)
    else:
        items = [str(item) for item in raw]
    tags = []
    for item in items:
        item = item.strip().lstrip("#")
        if item and f"#{item}" not in tags:
            tags.append(f"#{item}")
    return tags


def slug(text: str, limit: int = 24) -> str:
    base = re.sub(r"[^0-9A-Za-zА-Яа-яЁё]+", "-", text or "").strip("-").lower()
    if not base:
        base = "post"
    return base[:limit].strip("-") or "post"


def short_hash(value: str, length: int = 4) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def photo_captions(*sources: list) -> dict[str, str]:
    """Путь файла → подпись (для вставки в описание).

    Источники могут быть списками словарей {file, caption} и списками строк
    (пути по порядку) — строки дают подпись без адреса, они привязываются к
    фото по порядку.
    """
    captions: dict[str, str] = {}
    for photos in sources:
        for photo in photos or []:
            if isinstance(photo, str):
                if photo.strip():
                    captions.setdefault(photo.strip(), "")
                continue
            path = str(photo.get("file") or photo.get("path") or "")
            caption = str(photo.get("caption") or "").strip()
            if not path:
                # подпись «без пути»: дальше привяжется по порядку к фото сервиса
                if caption:
                    captions.setdefault(f"\x00byorder:{len(captions)}", caption)
                continue
            if caption:
                captions[path] = caption
    return captions


def caption_for(path: str, captions: dict[str, str], position: int) -> str:
    """Подпись конкретного файла: сначала по пути, потом по порядку."""
    if path in captions and captions[path]:
        return captions[path]
    by_order = f"\x00byorder:{position}"
    return captions.get(by_order, "")


# ---------------------------------------------------------------------------
# документ → план
# ---------------------------------------------------------------------------


def build_plan(document: dict[str, Any], *, with_defaults: bool = True) -> dict[str, Any]:
    """Собрать план (dict, как в plan.toml) из блокнотов."""
    services = document.get("services") or {}
    captions = photo_captions(
        document.get("photo_sources") or [],
        *[data.get("photo_sources") or [] for data in services.values()],
    )
    posts: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for service_name, data in services.items():
        header = data.get("header") or {}
        header_title = str(header.get("title") or "").strip()
        raw_posts = data.get("posts") or []
        pad_text = str(data.get("text") or "")
        if raw_posts:
            parsed_posts = [p for p in raw_posts if (p.get("title") or p.get("description"))]
        else:
            parsed_posts = parse_pad_text(pad_text)

        if not parsed_posts and not header_title:
            # в блокноте пусто — сервис пропускаем
            continue

        media = [str(m) for m in (data.get("media") or []) if str(m).strip()]
        photo_sources = []
        for item in data.get("photo_sources") or []:
            if isinstance(item, str):
                photo_sources.append(item.strip())
            else:
                path = item.get("file") or item.get("path")
                if path:
                    photo_sources.append(str(path))
        # фото, добавленные через панель подписей, тоже идут в публикацию
        for path in photo_sources:
            if path not in media:
                media.append(path)

        for index, parsed in enumerate(parsed_posts or [{"title": "", "description": ""}], start=1):
            title = (parsed.get("title") or "").strip() or header_title
            description = (parsed.get("description") or "").strip()
            if not title and not description:
                continue

            # подписи к фото — в конец описания
            caption_lines = []
            for position, path in enumerate(media):
                caption = caption_for(path, captions, position)
                if caption and caption not in description:
                    caption_lines.append(f"• {caption}")
            if caption_lines:
                description = "\n".join([description, *caption_lines]).strip()

            fallback = Path(media[0]).stem if media else "post"
            post_id = f"{service_name}-{index:02d}-{slug(title or fallback)}"
            if post_id in used_ids:
                post_id = f"{post_id}-{short_hash(str(index))}"
            used_ids.add(post_id)

            entry: dict[str, Any] = {
                "id": post_id,
                "title": title,
                "description": description,
                "tags": normalise_tags(header.get("tags")),
                "platforms": [service_name],
                "media": media,
            }
            if header.get("category"):
                entry["category"] = str(header["category"])
            if header.get("link"):
                entry["link"] = str(header["link"])
            posts.append(entry)

    plan: dict[str, Any] = {"posts": posts}
    if with_defaults:
        # площадки уже указаны у каждого поста, defaults нужен только для тегов
        plan["defaults"] = {"tags": []}
    return plan


# ---------------------------------------------------------------------------
# TOML: запись и чтение
# ---------------------------------------------------------------------------


def toml_string(value: str) -> str:
    """Строка в TOML-виде: JSON-экранирование совместимо с TOML basic string."""
    return json.dumps(str(value), ensure_ascii=False)


def toml_array(values: list[str]) -> str:
    return "[" + ", ".join(toml_string(v) for v in values) + "]"


def plan_to_toml(plan: dict[str, Any]) -> str:
    lines = [
        "# План публикаций. Создан программой «Публикатор» — можно править и руками.",
        "# Каждый [[posts]] — один пост. platforms — куда его отправить.",
        "",
    ]
    defaults = plan.get("defaults") or {}
    tags = defaults.get("tags") or []
    if tags:
        lines += ["[defaults]", f"tags = {toml_array(list(tags))}", ""]
    for post in plan.get("posts", []):
        lines.append("[[posts]]")
        lines.append(f"id = {toml_string(post['id'])}")
        if post.get("title"):
            lines.append(f"title = {toml_string(post['title'])}")
        if post.get("description"):
            lines.append(f"description = {toml_string(post['description'])}")
        post_tags = list(post.get("tags") or [])
        if post_tags:
            lines.append(f"tags = {toml_array(post_tags)}")
        lines.append(f"platforms = {toml_array(list(post.get('platforms') or []))}")
        if post.get("category"):
            lines.append(f"category = {toml_string(post['category'])}")
        if post.get("link"):
            lines.append(f"link = {toml_string(post['link'])}")
        media = list(post.get("media") or [])
        if media:
            lines.append(f"media = {toml_array(media)}")
        lines.append("")
    return "\n".join(lines)


def write_plan(plan: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(plan_to_toml(plan), encoding="utf-8")
    return path


def load_plan(path: str | Path) -> dict[str, Any]:
    import tomllib

    data = tomllib.loads(Path(path).read_text(encoding="utf-8-sig"))
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# план → документ (чтобы открыть окна с уже сохранённым содержимым)
# ---------------------------------------------------------------------------


def document_from_plan(plan: dict[str, Any], service_order: list[str]) -> dict[str, Any]:
    """Разложить сохранённый план обратно по блокнотам сервисов."""
    document: dict[str, Any] = {"services": {}, "photo_sources": []}
    services = {name: {"header": {}, "media": [], "posts": [], "photo_sources": []} for name in service_order}
    shared_photos: dict[str, str] = {}

    for post in plan.get("posts") or []:
        platforms = [str(p) for p in (post.get("platforms") or [])]
        if not platforms:
            continue
        entry = {
            "title": str(post.get("title") or ""),
            "description": str(post.get("description") or ""),
        }
        media = [str(m) for m in (post.get("media") or [])]
        tags = list(post.get("tags") or [])
        for name in platforms:
            if name not in services:
                services[name] = {"header": {}, "media": [], "posts": [], "photo_sources": []}
            bucket = services[name]
            bucket["posts"].append(entry)
            for path in media:
                if path not in bucket["media"]:
                    bucket["media"].append(path)
                if Path(path).suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
                    shared_photos.setdefault(path, "")
            header = bucket["header"]
            if not header.get("title") and post.get("title"):
                header["title"] = str(post.get("title"))
            if not header.get("tags") and tags:
                header["tags"] = " ".join(t.lstrip("#") for t in tags)
            if post.get("category") and not header.get("category"):
                header["category"] = str(post["category"])
            if post.get("link") and not header.get("link"):
                header["link"] = str(post["link"])

    for name, bucket in services.items():
        if bucket["posts"] or bucket["media"] or bucket["header"].get("title"):
            document["services"][name] = bucket
    document["photo_sources"] = [{"file": path, "caption": caption} for path, caption in shared_photos.items()]
    return document
