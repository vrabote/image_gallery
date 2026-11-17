"""Модель данных: пост, медиа-файл, площадка, результат публикации.

Здесь же — проверка файлов под лимиты конкретной площадки (длительность
видео, размер, формат, число изображений в галерее). Проверки «мягкие»:
предупреждение не мешает публикации, но блокирующая ошибка — мешает.
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi", ".ylt"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".tif", ".tiff"}


def _first(d: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in d and d[name] not in (None, ""):
            return d[name]
    return default


# ---------------------------------------------------------------------------
# медиа
# ---------------------------------------------------------------------------


@dataclass
class Media:
    """Один файл: картинка или видео."""

    path: Path
    kind: str  # "video" | "image"
    caption: str = ""
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    size_bytes: int = 0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def aspect(self) -> float:
        if self.width and self.height:
            return self.width / self.height
        return 0.0

    @property
    def is_vertical(self) -> bool:
        return bool(self.aspect and self.aspect < 0.95)

    @property
    def is_square(self) -> bool:
        return bool(self.aspect and 0.95 <= self.aspect <= 1.05)

    def summary(self) -> dict[str, Any]:
        data: dict[str, Any] = {"file": str(self.path), "kind": self.kind, "size_mb": round(self.size_bytes / 1e6, 2)}
        if self.duration:
            data["duration_s"] = round(self.duration, 1)
        if self.width and self.height:
            data["resolution"] = f"{self.width}x{self.height}"
        return data

    @classmethod
    def load(cls, value: str | Path | dict[str, Any], base: Path) -> "Media":
        caption = ""
        if isinstance(value, dict):
            caption = str(_first(value, "caption", "description", default="") or "")
            value = _first(value, "file", "path")
            if not value:
                raise ValueError("В медиа-элементе плана нет поля file/path")
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = base / path
        path = Path(path)
        ext = path.suffix.lower()
        if ext in VIDEO_EXT:
            kind = "video"
        elif ext in IMAGE_EXT:
            kind = "image"
        else:
            guess = mimetypes.guess_type(path.name)[0] or ""
            kind = "video" if guess.startswith("video/") else "image"
        media = cls(path=path, kind=kind, caption=caption)
        if path.exists():
            media.size_bytes = path.stat().st_size
            probe = probe_media(path)
            media.duration = probe.get("duration")
            media.width = probe.get("width")
            media.height = probe.get("height")
        return media


def probe_media(path: Path) -> dict[str, Any]:
    """Узнать длительность и размеры.

    Сначала пробуем ffprobe (если установлен), потом — чистый Python для MP4
    (парсим mvhd/tkhd). Без ffprobe MP4 длительность обычно всё равно
    известна, а вот разрешение — не всегда.
    """
    path = Path(path)
    data = _probe_ffprobe(path)
    if data:
        return data
    if path.suffix.lower() in {".mp4", ".mov", ".m4v"}:
        return _probe_mp4(path)
    return {}


def _probe_ffprobe(path: Path) -> dict[str, Any]:
    exe = shutil.which("ffprobe")
    if not exe:
        return {}
    try:
        out = subprocess.run(
            [exe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True,
            timeout=60,
            check=True,
        ).stdout
        payload = json.loads(out.decode("utf-8", "replace"))
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError):
        return {}
    result: dict[str, Any] = {}
    duration = payload.get("format", {}).get("duration")
    if duration:
        try:
            result["duration"] = float(duration)
        except ValueError:
            pass
    for stream in payload.get("streams", []):
        if stream.get("codec_type") == "video":
            if stream.get("width"):
                result["width"] = int(stream["width"])
            if stream.get("height"):
                result["height"] = int(stream["height"])
            if "duration" in result or not stream.get("duration"):
                continue
            try:
                result["duration"] = float(stream["duration"])
            except ValueError:
                pass
            break
    return result


def _probe_mp4(path: Path) -> dict[str, Any]:
    """Прочитать длительность/разрешение из структуры MP4 без внешних программ."""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            result: dict[str, Any] = {}
            visited: set[int] = set()
            offset = 0
            while offset < size:
                fh.seek(offset)
                header = fh.read(16)
                if len(header) < 8:
                    break
                box_size, box_type = struct.unpack(">I4s", header[:8])
                if box_size == 1:
                    big = fh.read(8)
                    if len(big) < 8:
                        break
                    box_size = struct.unpack(">Q", big)[0]
                if box_size < 8:
                    break
                if box_type == b"moov":
                    # moov бывает и после большого mdat — читаем его по месту, из файла
                    result.update(_parse_moov_stream(fh, offset, box_size, visited, size))
                    break
                offset += box_size
            if not result:
                result.update(_scan_for_moov(fh, size))
            result = {k: v for k, v in result.items() if v}
            return result
    except OSError:
        return {}


def _scan_for_moov(fh, file_size: int) -> dict[str, Any]:
    """Запасной путь: ищем маркер moov по файлу (бывает нестандартная раскладка)."""
    chunk_size = 4 * 1024 * 1024
    overlap = 16
    position = 0
    while position < file_size:
        fh.seek(position)
        chunk = fh.read(chunk_size + overlap)
        if not chunk:
            break
        index = chunk.find(b"moov")
        while index != -1:
            box_start = position + index - 4
            if box_start >= 0:
                fh.seek(box_start)
                header = fh.read(8)
                if len(header) == 8:
                    box_size = struct.unpack(">I", header[:4])[0]
                    if 16 <= box_size <= file_size - box_start:
                        found = _parse_moov_stream(fh, box_start, box_size, set(), file_size)
                        if found:
                            return found
            index = chunk.find(b"moov", index + 4)
        position += chunk_size
    return {}


def _parse_moov_stream(fh, start: int, box_size: int, visited: set[int], file_size: int) -> dict[str, Any]:
    """Пройти контейнер moov (и вложенные), не читая файл целиком."""
    result: dict[str, Any] = {}
    pos = start + 8
    end = min(start + box_size, file_size)
    while pos + 8 <= end:
        if pos in visited:
            break
        visited.add(pos)
        fh.seek(pos)
        header = fh.read(16)
        if len(header) < 8:
            break
        child_size, child_type = struct.unpack(">I4s", header[:8])
        header_len = 8
        if child_size == 1:
            big = header[8:16]
            if len(big) < 8:
                break
            child_size = struct.unpack(">Q", big)[0]
            header_len = 16
        if child_size < header_len:
            break
        body_start = pos + header_len
        body_len = min(child_size - header_len, end - body_start)
        if child_type == b"mvhd" and body_len >= 20:
            fh.seek(body_start)
            body = fh.read(min(body_len, 120))
            result.update(_parse_mvhd(body))
        elif child_type == b"trak":
            inner = _parse_moov_stream(fh, pos, child_size, visited, file_size)
            if inner.get("width") and not result.get("width"):
                result.update(inner)
        elif child_type == b"tkhd" and body_len >= 76:
            fh.seek(body_start)
            body = fh.read(min(body_len, 100))
            width, height = _parse_tkhd(body)
            if width and height:
                result.setdefault("width", width)
                result.setdefault("height", height)
        pos += child_size
    return result


def _parse_mvhd(body: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        version = body[0]
        if version == 1 and len(body) >= 32:
            timescale, duration = struct.unpack(">IQ", body[20:32])
        else:
            timescale, duration = struct.unpack(">II", body[12:20])
        if timescale:
            result["duration"] = duration / timescale
    except (struct.error, IndexError):
        pass
    return result


def _parse_tkhd(body: bytes) -> tuple[int | None, int | None]:
    try:
        version = body[0]
        # размеры всегда в последних 8 байтах бокса (matrix занимает 36 байт перед ними)
        if len(body) < 16:
            return None, None
        width, height = struct.unpack(">II", body[-8:])
        width, height = width >> 16, height >> 16
        if 0 < width < 20000 and 0 < height < 20000:
            return width, height
    except (struct.error, IndexError):
        pass
    return None, None


def _parse_moov_stream(fh, start: int, box_size: int, visited: set[int], file_size: int) -> dict[str, Any]:
    """Пройти контейнер moov (и вложенные), не читая файл целиком."""
    result: dict[str, Any] = {}
    pos = start + 8
    end = min(start + box_size, file_size)
    while pos + 8 <= end:
        if pos in visited:
            break
        visited.add(pos)
        fh.seek(pos)
        header = fh.read(16)
        if len(header) < 8:
            break
        child_size, child_type = struct.unpack(">I4s", header[:8])
        header_len = 8
        if child_size == 1:
            big = header[8:16]
            if len(big) < 8:
                break
            child_size = struct.unpack(">Q", big)[0]
            header_len = 16
        if child_size < header_len:
            break
        body_start = pos + header_len
        body_len = min(child_size - header_len, end - body_start)
        if child_type == b"mvhd" and body_len >= 20:
            fh.seek(body_start)
            body = fh.read(min(body_len, 120))
            result.update(_parse_mvhd(body))
        elif child_type == b"trak":
            inner = _parse_moov_stream(fh, pos, child_size, visited, file_size)
            if inner.get("width") and not result.get("width"):
                result.update(inner)
        elif child_type == b"tkhd" and body_len >= 76:
            fh.seek(body_start)
            body = fh.read(min(body_len, 100))
            width, height = _parse_tkhd(body)
            if width and height:
                result.setdefault("width", width)
                result.setdefault("height", height)
        pos += child_size
    return result


def _parse_mvhd(body: bytes) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        version = body[0]
        if version == 1 and len(body) >= 32:
            timescale, duration = struct.unpack(">IQ", body[20:32])
        else:
            timescale, duration = struct.unpack(">II", body[12:20])
        if timescale:
            result["duration"] = duration / timescale
    except (struct.error, IndexError):
        pass
    return result


def _parse_tkhd(body: bytes) -> tuple[int | None, int | None]:
    try:
        version = body[0]
        # размеры всегда в последних 8 байтах бокса (matrix занимает 36 байт перед ними)
        if len(body) < 16:
            return None, None
        width, height = struct.unpack(">II", body[-8:])
        width, height = width >> 16, height >> 16
        if 0 < width < 20000 and 0 < height < 20000:
            return width, height
    except (struct.error, IndexError):
        pass
    return None, None


# ---------------------------------------------------------------------------
# площадки и их лимиты
# ---------------------------------------------------------------------------


@dataclass
class Limits:
    """Ограничения площадки. None = ограничения нет."""

    max_video_seconds: float | None = None
    max_video_mb: float | None = None
    max_image_mb: float | None = None
    max_images: int | None = None
    max_caption_chars: int | None = None
    max_title_chars: int | None = None
    max_tags: int | None = None
    supports_video: bool = True
    supports_images: bool = True
    supports_carousel: bool = False


@dataclass
class Issue:
    level: str  # "error" | "warning"
    text: str

    def __str__(self) -> str:
        mark = "ОШИБКА" if self.level == "error" else "внимание"
        return f"[{mark}] {self.text}"


@dataclass
class Post:
    """Один пост из плана."""

    id: str
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    media: list[Media] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    category: str = ""
    link: str = ""
    extra: dict[str, Any] = field(default_factory=dict)
    source_file: Path | None = None

    # -- удобные свойства ---------------------------------------------------
    @property
    def videos(self) -> list[Media]:
        return [m for m in self.media if m.kind == "video"]

    @property
    def images(self) -> list[Media]:
        return [m for m in self.media if m.kind == "image"]

    @property
    def main_video(self) -> Media | None:
        return self.videos[0] if self.videos else None

    @property
    def hashtags(self) -> str:
        return " ".join(self.tags)

    def full_text(self, with_tags: bool = True) -> str:
        parts = [self.description.strip()]
        if with_tags and self.tags:
            parts.append(self.hashtags)
        return "\n\n".join(part for part in parts if part)

    def title_or_first_line(self) -> str:
        if self.title.strip():
            return self.title.strip()
        for line in self.description.splitlines():
            if line.strip():
                return line.strip()[:100]
        return self.id

    # -- проверки -----------------------------------------------------------
    def check(self, limits: Limits) -> list[Issue]:
        issues: list[Issue] = []
        for media in self.media:
            if not media.path.exists():
                # про такой файл дальше говорить нечего: сначала пусть появится
                issues.append(Issue("error", f"Файл не найден: {media.path}"))
                continue
            if media.size_bytes == 0:
                issues.append(Issue("error", f"Файл пустой: {media.path}"))
            if media.kind == "video":
                if not limits.supports_video:
                    issues.append(Issue("error", f"Площадка не принимает видео ({media.name})"))
                if limits.max_video_mb and media.size_bytes > limits.max_video_mb * 1_000_000:
                    mb = media.size_bytes / 1e6
                    issues.append(
                        Issue(
                            "warning",
                            f"{media.name}: {mb:.0f} МБ больше лимита {limits.max_video_mb:.0f} МБ — "
                            "загрузимся через докачку, но площадка может отказать",
                        )
                    )
                if limits.max_video_seconds and media.duration and media.duration > limits.max_video_seconds:
                    issues.append(
                        Issue(
                            "warning",
                            f"{media.name}: {media.duration:.0f} с длиннее лимита "
                            f"{limits.max_video_seconds:.0f} с",
                        )
                    )
            else:
                if not limits.supports_images:
                    issues.append(Issue("error", f"Площадка не принимает изображения ({media.name})"))
                if limits.max_image_mb and media.size_bytes > limits.max_image_mb * 1_000_000:
                    issues.append(
                        Issue(
                            "warning",
                            f"{media.name}: {media.size_bytes / 1e6:.1f} МБ больше лимита "
                            f"{limits.max_image_mb:.0f} МБ",
                        )
                    )
        if limits.max_images and len(self.media) > limits.max_images:
            issues.append(
                Issue(
                    "warning",
                    f"Файлов {len(self.media)}, площадка примет не больше {limits.max_images}",
                )
            )
        if limits.max_caption_chars and len(self.full_text()) > limits.max_caption_chars:
            issues.append(
                Issue(
                    "warning",
                    f"Текст {len(self.full_text())} симв., лимит {limits.max_caption_chars} — обрежем",
                )
            )
        if limits.max_title_chars and len(self.title) > limits.max_title_chars:
            issues.append(
                Issue("warning", f"Заголовок длиннее {limits.max_title_chars} символов — обрежем")
            )
        if limits.max_tags and len(self.tags) > limits.max_tags:
            issues.append(Issue("warning", f"Тегов {len(self.tags)}, лимит {limits.max_tags}"))
        return issues


# ---------------------------------------------------------------------------
# план
# ---------------------------------------------------------------------------


@dataclass
class Plan:
    posts: list[Post]
    path: Path
    defaults: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path, base: Path | None = None) -> "Plan":
        from .config import load_structured

        path = Path(path).expanduser()
        data = load_structured(path)
        base = Path(base) if base else path.parent
        raw_posts = data.get("posts") or data.get("посты") or []
        defaults = data.get("defaults") or {}
        if not isinstance(raw_posts, list):
            raise ValueError("В плане ожидался список posts")
        posts: list[Post] = []
        for index, raw in enumerate(raw_posts, start=1):
            if not isinstance(raw, dict):
                raise ValueError(f"Пост #{index}: ожидался объект")
            post = _post_from_dict(raw, base, defaults, index)
            post.source_file = path
            posts.append(post)
        plan = cls(posts=posts, path=path, defaults=defaults)
        plan.apply_default_write_back()
        return plan

    def apply_default_write_back(self) -> None:
        """Дописать в посты значения из defaults (платформы, теги)."""
        default_platforms = self.defaults.get("platforms")
        default_tags = self.defaults.get("tags")
        for post in self.posts:
            if not post.platforms and default_platforms:
                post.platforms = list(default_platforms)
            if not post.tags and default_tags:
                post.tags = [t if str(t).startswith("#") else f"#{t}" for t in default_tags]

    def for_platform(self, platform: str) -> list[Post]:
        return [post for post in self.posts if not post.platforms or platform in post.platforms]

    def summary(self) -> list[dict[str, Any]]:
        return [
            {
                "id": post.id,
                "title": post.title_or_first_line(),
                "platforms": post.platforms,
                "media": [m.summary() for m in post.media],
            }
            for post in self.posts
        ]


def _post_from_dict(raw: dict[str, Any], base: Path, defaults: dict[str, Any], index: int) -> Post:
    tags = _first(raw, "tags", "hashtags", default=[]) or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]
    tags = [t if t.startswith("#") else f"#{t}" for t in tags if t != "#"]

    platforms = _first(raw, "platforms", "targets", "площадки", default=[]) or []
    if isinstance(platforms, str):
        platforms = [p.strip() for p in platforms.replace(",", " ").split() if p.strip()]

    media_raw = _first(raw, "media", "files", default=[])
    if isinstance(media_raw, (str, Path)):
        media_raw = [media_raw]
    media = [Media.load(item, base) for item in media_raw]

    post = Post(
        id=str(_first(raw, "id", default=f"post-{index:02d}")),
        title=str(_first(raw, "title", "заголовок", default="") or ""),
        description=str(_first(raw, "description", "text", "caption", "описание", default="") or ""),
        tags=tags,
        media=media,
        platforms=[str(p) for p in platforms],
        category=str(_first(raw, "category", "playlist", "категория", default="") or ""),
        link=str(_first(raw, "link", "purchase_url", default="") or ""),
        extra={
            k: v
            for k, v in raw.items()
            if k
            not in {
                "id",
                "title",
                "заголовок",
                "description",
                "text",
                "caption",
                "описание",
                "tags",
                "hashtags",
                "platforms",
                "targets",
                "площадки",
                "media",
                "files",
                "category",
                "playlist",
                "категория",
                "link",
            }
        },
    )
    # тексты картинок: если у изображения есть caption, добавим в описание
    image_captions = [m.caption for m in post.images if m.caption]
    if image_captions:
        post.extra.setdefault("image_captions", image_captions)
        if defaults.get("append_image_captions", True):
            extra_text = "\n".join(f"• {c}" for c in image_captions)
            if extra_text not in post.description:
                post.description = (post.description + "\n\n" + extra_text).strip()
    return post
