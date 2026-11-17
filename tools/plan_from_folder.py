"""Собрать черновик плана публикаций из папки с файлами.

Пример:
    python tools/plan_from_folder.py video_prep uploads --out plan.toml
    python tools/plan_from_folder.py ~/clips --platforms youtube,vk,telegram

Каждый видеофайл становится отдельным постом, все картинки — одним постом-
галереей (или отдельными постами с --images-single). Описания и теги потом
правится руками — это именно черновик.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from social_publisher.core.models import IMAGE_EXT, VIDEO_EXT, probe_media  # noqa: E402


def collect(folders: list[Path], recursive: bool) -> tuple[list[Path], list[Path]]:
    videos: list[Path] = []
    images: list[Path] = []
    for folder in folders:
        folder = folder.expanduser().resolve()
        if folder.is_file():
            candidates = [folder]
        elif recursive:
            candidates = [p for p in folder.rglob("*") if p.is_file()]
        else:
            candidates = [p for p in folder.iterdir() if p.is_file()]
        for path in sorted(candidates):
            suffix = path.suffix.lower()
            if suffix in VIDEO_EXT:
                videos.append(path)
            elif suffix in IMAGE_EXT:
                images.append(path)
    return videos, images


def toml_path(path: Path, base: Path) -> str:
    try:
        relative = path.relative_to(base)
        return str(relative).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def quote(value: str) -> str:
    return '"' + value.replace("\\", '"').replace('"', '\\"') + '"'


def build(
    videos: list[Path],
    images: list[Path],
    base: Path,
    platforms: list[str],
    single_images: bool,
    image_platforms: list[str],
) -> str:
    lines = [
        "# Черновик плана. Проверьте заголовки, описания и теги.",
        "",
        "[defaults]",
        f"platforms = [{', '.join(quote(p) for p in platforms)}]",
        'tags = ["клип"]',
        "",
    ]
    for index, video in enumerate(videos, start=1):
        probe = probe_media(video)
        bits = []
        if probe.get("duration"):
            bits.append(f"{probe['duration']:.0f} с")
        if probe.get("width") and probe.get("height"):
            bits.append(f"{probe['width']}x{probe['height']}")
        hint = f"  # {' · '.join(bits)}" if bits else ""
        lines += [
            "[[posts]]",
            f"id = {quote(f'video-{index:02d}-{video.stem[:24]}')}",
            f"title = {quote(video.stem)}",
            f"description = {quote('Описание клипа — отредактируйте меня.')}",
            f"media = [{quote(toml_path(video, base))}]{hint}",
            "",
        ]
    if images:
        image_list = ", ".join(quote(p) for p in image_platforms)
        if single_images:
            for index, image in enumerate(images, start=1):
                lines += [
                    "[[posts]]",
                    f"id = {quote(f'photo-{index:02d}-{image.stem[:24]}')}",
                    f"title = {quote(image.stem)}",
                    f"description = {quote('Описание кадра — отредактируйте меня.')}",
                    f"media = [{quote(toml_path(image, base))}]",
                    f"platforms = [{image_list}]",
                    "",
                ]
        else:
            lines += [
                "[[posts]]",
                'id = "gallery-01"',
                'title = "Подборка фотографий"',
                'description = "Описание подборки."',
                "media = [",
            ]
            for image in images:
                lines.append(f"  {quote(toml_path(image, base))},")
            lines += ["]", f"platforms = [{image_list}]", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Черновик plan.toml из папки с файлами")
    parser.add_argument("folders", nargs="+", help="папки (или отдельные файлы) с клипами и фото")
    parser.add_argument("--out", default="plan.toml", help="куда записать план")
    parser.add_argument("--platforms", default="youtube,vk,telegram", help="площадки через запятую")
    parser.add_argument("--recursive", "-r", action="store_true", help="заходить в подпапки")
    parser.add_argument("--images-single", action="store_true", help="каждая картинка — отдельный пост")
    parser.add_argument(
        "--image-platforms",
        default="vk,telegram",
        help="площадки для фото-постов (по умолчанию vk,telegram: YouTube фото не принимает)",
    )
    args = parser.parse_args()

    folders = [Path(f) for f in args.folders]
    videos, images = collect(folders, args.recursive)
    if not videos and not images:
        print("Ничего не нашёл: проверьте пути и расширения.")
        return 1

    base = Path(args.out).expanduser().resolve().parent
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    image_platforms = [p.strip() for p in args.image_platforms.split(",") if p.strip()]
    text = build(videos, images, base, platforms, args.images_single, image_platforms)
    out = Path(args.out).expanduser()
    out.write_text(text, encoding="utf-8")
    print(f"Готово: {out} · клипов {len(videos)} · фото {len(images)}")
    print("Проверьте файл, затем: python -m social_publisher plan " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
