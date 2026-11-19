# Публикатор клипов и фото в соцсети

Программа берёт папку с готовыми клипами и фото, читает план публикаций
(`plan.toml`) и размещает всё по площадкам: **YouTube, VK, Telegram, Rutube,
Дзен, Instagram, TikTok**. Перед каждой публикацией спрашивает подтверждение и
запоминает результат в журнале, чтобы не выложить одно и то же дважды.

Два способа публикации:

| Способ | Как работает | Когда использовать |
|---|---|---|
| **API** (по токенам) | Официальные API площадок. Надёжно, не ломается при редизайне. | YouTube, VK, Telegram, Rutube |
| **Браузер** | Playwright открывает страницу загрузки в вашем залогиненном браузере, прикрепляет файл, вписывает текст и нажимает «Опубликовать». | Дзен, Instagram, TikTok и как запасной путь для остальных |
| **Вручную** | Файлы и подпись складываются в `state/manual/<площадка>/<пост>/`, пост попадает в журнал как «сделать вручную». | Если автоматизация не нужна/невозможна |

Режим `--mode auto` (по умолчанию) сам выбирает: есть токен → API, нет →
браузер, нет и браузера → подготовка для ручной публикации.

---

## 0. Оконный интерфейс (для тех, кто не любит консоль)

Двойной клик по **`Запустить публикатор.bat`** в корне проекта:

1. **«Входные данные…»** — один раз заполнить токены/входы;
2. **двойной клик по сервису** — отдельное окно-блокнот (посты, файлы, теги);
3. **«Проверить»** — таблица: файл, сервис, лимиты, готовность;
4. **«Запустить»** — публикация с подтверждением по каждому посту.

Подробнее: [gui/README.md](gui/README.md). Всё, что делает окно, доступно и
командами ниже — план, собранный в окне (`plan.toml`), понимает `run`.

---

## 1. Установка (Windows)

Нужен **Python 3.11+** (при установке отметьте «Add Python to PATH»).

```bat
cd путь\к\image_gallery
python -m pip install playwright
python -m playwright install chromium
```

Chromium можно не скачивать, если хотите использовать уже установленный
Chrome/Edge — тогда в `social_publisher/config.toml` раскомментируйте:

```toml
[browser]
channel = "msedge"   # или "chrome"
```

Проверка окружения и готовности площадок:

```bat
python -m social_publisher doctor
```

---

## 2. Быстрый старт за пять шагов

1. **Секреты.** Скопируйте `social_publisher/secrets.example.toml` в
   `social_publisher/secrets.toml` и заполните те площадки, которые нужны
   (Telegram — самый простой, 2 минуты).
2. **План.** Скопируйте `plan.example.toml` в свою папку и опишите посты.
   Пути к файлам считаются от папки плана.
3. **Проверка:** `python -m social_publisher plan plan.toml --check`
4. **Репетиция:** `python -m social_publisher run plan.toml --dry-run`
5. **Публикация с подтверждением:** `python -m social_publisher run plan.toml`

Полезные флаги:

```bat
python -m social_publisher run plan.toml --platform telegram      :: только Telegram
python -m social_publisher run plan.toml --skip tiktok            :: без TikTok
python -m social_publisher run plan.toml --limit 3                :: первые 3 публикации
python -m social_publisher run plan.toml --yes                    :: без вопросов (осторожно)
python -m social_publisher run plan.toml --force                  :: даже если уже публиковали
python -m social_publisher run plan.toml --mode browser           :: только браузер
python -m social_publisher journal                                :: что уже выложено
```

---

## 3. Настройка площадок

### Telegram (проще всего)

1. В Telegram: `@BotFather` → `/newbot` → токен вида `123456:AA...`
2. Добавьте бота **администратором** в свой канал (право «Публикация сообщений»).
3. В `secrets.toml`:

```toml
[telegram]
bot_token = "123456:AA..."
chat_id = "@my_channel"     # или числовой id: -1001234567890
```

Поддерживается: видео с подписью, альбом фото (до 10), текст с кнопкой-ссылкой.

### YouTube

1. <https://console.cloud.google.com> → новый проект → включить **YouTube Data API v3**.
2. Экран согласия OAuth: тип «Внешний», добавьте себя в тестовые пользователи.
3. Учётные данные → **OAuth client ID** → тип **Desktop app** → скачать JSON.
4. Положите файл как `social_publisher/client_secret.json`.
5. Выполните один раз:

```bat
python -m social_publisher auth youtube
```

Откроется браузер, вы разрешаете доступ — токен сохранится в `state/cache/tokens/`.

Загрузка идёт возобновляемым протоколом: если интернет оборвётся на 500-м
мегабайте, загрузка продолжится, а не начнётся заново. Вертикальный ролик до
3 минут YouTube сам покажет в Shorts.

### VK

1. <https://dev.vk.com> → «Разработчикам» → создайте приложение типа **Standalone**.
2. В настройках приложения возьмите **ключ доступа** с правами
   `wall, photos, video, offline` (для сообщества удобнее токен сообщества:
   Управление → Работа с API → Ключи доступа).
3. В `secrets.toml`:

```toml
[vk]
access_token = "vk1.a...."
group_id = "1234567"   # id сообщества БЕЗ минуса; пусто = личная страница
```

Поддерживается: видео с описанием, до 10 фото в записи, текст.

### Rutube

API Rutube выдаётся по запросу (поддержка/менеджер). Если доступ есть:

```toml
[rutube]
token = "X-AUTH-TOKEN из кабинета"
channel_id = "..."    # опционально
```

Если доступа нет — используйте браузерный режим (`--mode browser`).

### Дзен, Instagram, TikTok

Публичного API для автопостинга у них нет. Работает браузерный режим:
сначала один раз войдите в аккаунт (профиль браузера сохраняется):

```bat
python -m social_publisher login dzen
python -m social_publisher login instagram
python -m social_publisher login tiktok
```

Затем обычный запуск с `--mode browser` (или `--mode auto`).

---

## 4. Формат плана

```toml
[defaults]
platforms = ["youtube", "vk", "telegram"]   # для постов без своих platforms
tags = ["клип", "видео"]                    # общие теги

[[posts]]
id = "clip-01"                              # уникальный id (нужен для журнала)
title = "Как упаковать хрупкое"
description = """
Текст описания. Можно в несколько строк — они уйдут как есть.
"""
tags = ["клип", "хрупкое"]
platforms = ["youtube", "vk", "telegram"]
category = "Клипы"                          # для плейлиста YouTube
link = "https://example.com"                # кнопка/ссылка, если нужно
media = ["../video_prep/final_video.mp4"]

[[posts]]
id = "gallery-01"
title = "Подборка: фактуры и свет"
description = "Три кадра из одной прогулки."
platforms = ["vk", "telegram"]
media = [
  { file = "../uploads/test.jpg", caption = "Кадр 1 — мягкий свет" },
  "../video_prep/00_clean_base.jpg",
]
```

Также можно писать план в JSON (`plan.json`) с теми же ключами. Подписи
(`caption`) у изображений добавляются в описание списком.

Скрипт `tools/plan_from_folder.py` соберёт черновик плана из папки с файлами:

```bat
python tools/plan_from_folder.py video_prep uploads --out plan.toml
```

---

## 5. Браузерный режим: как это работает и как чинить

* Программа использует **постоянный профиль браузера** в
  `state/browser-profile` — вход в аккаунты сохраняется между запусками.
* Все шаги описаны в `social_publisher/selectors.json`: адрес страницы, поле
  файла, поля заголовка/описания, кнопка «Опубликовать», признак успеха.
* Если сайт поменял вёрстку, селекторы правятся **без изменения кода**:
  создайте рядом с `config.toml` файл `selectors.local.json` с нужным профилем —
  он переопределит встроенный.
* Подсказка по реальным селекторам на текущей странице:

```bat
python -m social_publisher learn youtube
```

Команда покажет все `input[type=file]`, текстовые поля и кнопки с их атрибутами.

Что важно понимать:

* Это автоматизация интерфейса, а не API. Сайты могут менять разметку, просить
  капчу, ограничивать частоту. Не публикуйте десятками постов в час.
* Не входите в один и тот же аккаунт из двух мест одновременно.
* Перед нажатием «Опубликовать» программа спрашивает подтверждение (если не
  указан `--yes`), а при ошибке делает скриншот в `state/screenshots/`.

---

## 6. Что происходит с уже опубликованным

Каждая попытка пишется в `social_publisher/state/journal.jsonl`:

* повторный запуск **пропустит** пару «пост → площадка», если она уже успешно
  опубликована (`--force` отменяет проверку);
* ошибки тоже попадают в журнал — видно, что и почему не ушло:

```bat
python -m social_publisher journal
python -m social_publisher journal --failed
```

---

## 7. Устройство кода

```
social_publisher/
  cli.py                 команды: doctor, plan, run, auth, login, learn, journal, init
  config.toml            настройки (без секретов)
  secrets.example.toml   образец секретов → скопировать в secrets.toml
  selectors.json         профили браузерного режима для каждой площадки
  plan.example.toml      пример плана
  core/
    models.py            пост, медиа, лимиты, проверки; чтение MP4 без ffmpeg
    http.py              HTTP-клиент с повторами, multipart и потоковой докачкой
    config.py            чтение config/secrets, переменные окружения SP_*
    journal.py           результаты публикаций и журнал JSONL
    runner.py            прогон плана, подтверждения, идемпотентность
  platforms/
    base.py              базовый адаптер, реестр, выбор режима (auto/api/browser)
    youtube.py           Data API v3, resumable upload, OAuth
    vk.py                wall.post, photos.*, video.save
    telegram.py          Bot API: sendVideo / sendPhoto / sendMediaGroup
    rutube.py            /api/video/upload/ + ожидание обработки
    dzen.py, instagram.py, tiktok.py   ручной режим (файлы + подпись)
    browser.py           универсальный браузерный адаптер + login/learn
  gui/                   окно: главное, блокноты сервисов, входные данные
  tests/                 39 тестов: локальный HTTP-сервер, заглушка tkinter
```

Добавить новую площадку: создать `platforms/новая.py` с классом-наследником
`Platform` (паспорт `info`, `check_env`, `publish`) и зарегистрировать его в
`build_registry`. Для сайта без API достаточно добавить профиль в
`selectors.json` — код писать не нужно.

---

## 8. Тесты

```bat
python -m pip install pytest
python -m pytest -q social_publisher/tests
```

Тесты не ходят в интернет: вместо площадок поднимается локальный HTTP-сервер,
который проверяет, что уходят правильные запросы (multipart-файлы, альбомы,
`wall.post`, возобновляемая загрузка YouTube), а браузерный режим проверяется
на фейковой странице.

---

## 9. Ограничения и здравый смысл

* Соблюдайте правила площадок: автоматизация интерфейса разрешена не везде.
* Не храните `secrets.toml` в репозитории (он уже в `.gitignore`).
* Токены дают доступ к аккаунту — держите файл секретов на своём компьютере.
* Лимиты (длительность, размер, число фото) проверяются заранее и показываются
  в `plan --check`; предупреждения не блокируют публикацию, ошибки — блокируют.
* Расписание по времени пока не встроено: запускайте вручную или поставьте
  `run` в Планировщик задач Windows. Это следующий логичный шаг, если нужно.
