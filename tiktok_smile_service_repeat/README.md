# BARH — «SMILE SERVICE REPEAT» (46 × 130 см, TikTok 9:16)

Два спокойных, резких вертикальных ролика (`1080×1920`, `30 fps`) с показом картины `46 × 130 см` в реальном масштабе в интерьере (без боковых полей) и фирменным рукописным логотипом `BARH` белым на чёрном в финале.

## Файлы

| Файл | Назначение |
| --- | --- |
| `SMILE_SERVICE_REPEAT_BARH_contrast.mp4` | Сценарий Б «Контраст» (`22.11 с`, `76 BPM`): портрет → `EXIT →` → крылышки/шампанское → тележка `SMILE SERVICE REPEAT` → показ `46×130 см` в тёмном лофте → лого `BARH`. |
| `SMILE_SERVICE_REPEAT_BARH_contrast_silent.mp4` | То же видео без звука под тренд в TikTok. |
| `SMILE_SERVICE_REPEAT_BARH_arttok.mp4` | Сценарий В «Чистый ArtTok» (`20.00 с`, `72 BPM`): без фраз поверх живописи — портрет → тележка → два макро мазков → показ `46×130 см` в светлой галерее → лого `BARH`. |
| `SMILE_SERVICE_REPEAT_BARH_arttok_silent.mp4` | То же видео без звука под тренд в TikTok. |
| `storyboard_contrast.jpg` / `storyboard_arttok.jpg` | Контакт-листы по 8 ключевых кадров. |
| `cover.png` | Чистая портретная обложка (`1080×1920`). |
| `barh_logo_white.png` | Фирменный рукописный логотип `BARH` белым. |
| `caption.txt` / `STRATEGY.md` | Подписи и тренд-анализ. |

## Пересборка

```bash
cd /home/user/image_gallery
python3 -m venv .venv
.venv/bin/pip install -r tiktok_smile_service_repeat/requirements.txt
cd tiktok_smile_service_repeat
../.venv/bin/python make_audio.py
../.venv/bin/python build_video.py
```
