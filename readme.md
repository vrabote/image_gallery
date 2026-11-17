# Простой скрипт галереи изображений на PHP



## Публикатор клипов и фото в соцсети

В репозитории есть отдельный инструмент `social_publisher/` — он берёт готовые
клипы и фотографии и размещает их в YouTube, VK, Telegram, Rutube, Дзен,
Instagram и TikTok (по токенам или через браузер, с подтверждением перед
публикацией).

```bash
python -m social_publisher doctor                 # проверить готовность
python -m social_publisher plan plan.toml         # что и куда уйдёт
python -m social_publisher run plan.toml --dry-run
python -m social_publisher run plan.toml          # публикация с подтверждением
```

Подробности и настройка площадок: [social_publisher/README.md](social_publisher/README.md).
