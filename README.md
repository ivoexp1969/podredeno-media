# podredeno-media

Медия за @podredeno.bg, публикувана през GitHub Pages:
`https://ivoexp1969.github.io/podredeno-media/<път>`. Всичко тук е публично.

## Как се планира публикация

1. Качи файловете в `media/YYYY-MM-DD/` (JPEG за снимки, MP4/MOV за reels).
2. Създай `queue/YYYY-MM-DD.json`:

```json
{
  "type": "carousel",
  "files": ["media/2026-11-17/01.jpg", "media/2026-11-17/02.jpg"],
  "caption": "Текст на публикацията #подредено"
}
```

`type` е `image` (1 файл), `carousel` (2–10 JPEG) или `reel` (1 видео; по желание
`"share_to_feed": false` и `"thumb_offset": 1500` в милисекунди).

Story: отделен файл `queue/YYYY-MM-DD-story.json` с `{"type": "story", "files": ["media/.../s.jpg"]}`
(1 JPEG 1080×1920 или 1 видео 3–60 сек). Без надпис; стикери „Линк“ и анкети не се
поддържат от API — текстът трябва да е в самата картинка. Публикува се в същото
пускане като поста за деня.

Видео материал за Reels: `media/source/` (записи на екрана без лични данни);
`media/source/USED.md` пази кой запис в коя дата е използван.

Workflow „Publish to Instagram“ се пуска всеки ден и публикува файла за деня след
18:00 часа София (GitHub Actions може да закъснее). След успех записът отива в
`published/YYYY-MM-DD.json` с `media_id`, `permalink` и `published_at`.

## Ограничения, които скриптът проверява

- Снимки: само JPEG, до 8 MB, пропорции от 4:5 до 1.91:1.
- Карусел: Instagram изрязва всички снимки по пропорцията на първата.
- Надпис: до 2200 знака, до 30 хаштага, до 20 @споменавания.
- Файл в GitHub: до 100 MB (важи за reels).

## Ръчно пускане и dry-run

Actions → Publish to Instagram → Run workflow. `Dry run` е включен по подразбиране:
проверява файловете, публичните линкове и токена, създава медийните контейнери
в Instagram, но не публикува.

## Secrets (Settings → Secrets and variables → Actions)

- `IG_ACCESS_TOKEN`: system-user токен (Unified login) от бизнес портфолиото
  „Подредено“ → System users → podredeno-bot → Generate token, приложение
  podredeno-publisher, разрешения `instagram_basic` и `instagram_content_publish`,
  срок **Never** — не се подновява.
- По желание, в Variables: `IG_USER_ID` (по подразбиране 17841471323988630 =
  @podredeno.bg) и `GRAPH_VERSION` (по подразбиране `v24.0`).
- Публикуването минава през `graph.facebook.com`.

## Тестове

```bash
python3 -m unittest discover -s tests -v
```
