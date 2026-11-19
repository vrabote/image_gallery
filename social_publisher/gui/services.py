"""Описание сервисов для окна «Блокнот»: порядок, подписи, подсказки.

Здесь нет tkinter и сети — только данные, чтобы это можно было тестировать и
переиспользовать в консольном режиме.
"""

from __future__ import annotations

from dataclasses import dataclass, field

VIDEO = "video"
IMAGES = "images"
ANY = "any"


@dataclass
class ServiceSpec:
    name: str
    title: str
    accepts: str = ANY
    placeholder: str = ""
    notes: list[str] = field(default_factory=list)
    #: есть ли официальный API (иначе только браузер/вручную)
    has_api: bool = True
    #: что нужно один раз заполнить в «Входах»
    setup_hint: str = ""
    default_limits: dict[str, int | None] = field(default_factory=dict)


SERVICES: list[ServiceSpec] = [
    ServiceSpec(
        name="youtube",
        title="YouTube",
        accepts=VIDEO,
        has_api=True,
        setup_hint="client_secret.json + кнопка «Войти в Google»",
        default_limits={"title": 100, "text": 5000, "tags": 15, "media": 1},
        placeholder=(
            "Например:\n"
            "Хрупкое — не кантовать\n"
            "Короткий клип о том, как важно беречь хрупкие вещи.\n"
            "\n"
            "---\n"
            "\n"
            "Второй клип — заголовок и текст отделяются тремя минусами\n"
            "Описание второго клипа…"
        ),
        notes=[
            "Вертикальный ролик до 3 минут YouTube сам покажет в Shorts.",
            "Первая строка поста становится заголовком, остальное — описанием.",
            "Несколько постов в одном блокноте разделяйте строкой «---».",
        ],
    ),
    ServiceSpec(
        name="vk",
        title="ВКонтакте",
        accepts=ANY,
        has_api=True,
        setup_hint="ключ доступа + id сообщества",
        default_limits={"title": None, "text": 16000, "tags": 20, "media": 10},
        placeholder=(
            "Текст записи для стены. Первая строка — заголовок (используется в плане),\n"
            "дальше — сам текст.\n"
            "\n"
            "Можно прикрепить несколько фото — они уйдут одной записью."
        ),
        notes=[
            "Фото: до 10 в одной записи.",
            "Видео лучше отправлять через API (токен), это надёжнее браузера.",
        ],
    ),
    ServiceSpec(
        name="telegram",
        title="Telegram",
        accepts=ANY,
        has_api=True,
        setup_hint="токен бота + @канал",
        default_limits={"title": None, "text": 1024, "tags": 20, "media": 10},
        placeholder=(
            "Подпись к посту (до 1024 символов).\n"
            "Ссылка, если указана в «Ссылке», станет кнопкой под сообщением."
        ),
        notes=[
            "Бот должен быть администратором канала.",
            "Фото уходят альбомом (до 10), видео — отдельным сообщением.",
        ],
    ),
    ServiceSpec(
        name="dzen",
        title="Дзен",
        accepts=ANY,
        has_api=False,
        setup_hint="вход в браузере (кнопка «Войти в браузере»)",
        default_limits={"title": 100, "text": 100000, "tags": 20, "media": 20},
        placeholder=(
            "Заголовок первым делом.\n"
            "Затем текст статьи: Дзен любит длинные тексты и картинки.\n"
            "\n"
            "Абзацы разделяйте пустой строкой."
        ),
        notes=["Публичного API нет: используется браузерный режим."],
    ),
    ServiceSpec(
        name="rutube",
        title="Rutube",
        accepts=VIDEO,
        has_api=True,
        setup_hint="X-AUTH-TOKEN (по запросу в Rutube) или вход в браузере",
        default_limits={"title": 128, "text": 5000, "tags": 20, "media": 1},
        placeholder="Название ролика первой строкой, затем описание.",
        notes=[
            "API Rutube выдаётся по запросу — без него работает браузерный режим.",
            "Обработка видео после загрузки занимает время.",
        ],
    ),
    ServiceSpec(
        name="instagram",
        title="Instagram",
        accepts=ANY,
        has_api=False,
        setup_hint="вход в браузере",
        default_limits={"title": None, "text": 2200, "tags": 30, "media": 10},
        placeholder="Подпись к посту (до 2200 символов). Хештеги — в поле «Теги».",
        notes=[
            "Публичного API нет: браузерный режим.",
            "Не публикуйте пачками — Instagram не любит автоматизацию.",
        ],
    ),
    ServiceSpec(
        name="tiktok",
        title="TikTok",
        accepts=VIDEO,
        has_api=False,
        setup_hint="вход в браузере",
        default_limits={"title": None, "text": 2200, "tags": 20, "media": 1},
        placeholder="Подпись к клипу (до 2200 символов).",
        notes=["Публичного API нет: браузерный режим.", "Вертикальные видео до 10 минут."],
    ),
]

SERVICE_ORDER = [spec.name for spec in SERVICES]
BY_NAME = {spec.name: spec for spec in SERVICES}


def spec(name: str) -> ServiceSpec:
    return BY_NAME.get(name) or ServiceSpec(name=name, title=name.capitalize())


def limits_line(name: str) -> str:
    """Строка-подсказка с лимитами для окна блокнота."""
    service = spec(name)
    limits = service.default_limits
    parts = []
    if limits.get("title"):
        parts.append(f"заголовок ≤ {limits['title']}")
    if limits.get("text"):
        parts.append(f"текст ≤ {limits['text']}")
    if limits.get("media"):
        parts.append(f"файлов ≤ {limits['media']}")
    parts.append("посты разделяются строкой «---»")
    return " · ".join(parts)
