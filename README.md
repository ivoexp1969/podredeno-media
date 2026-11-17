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

- `IG_ACCESS_TOKEN`: дълготраен Instagram токен. Подновява се автоматично всеки
  понеделник от workflow „Refresh Instagram token“.
- `GH_PAT_SECRETS`: fine-grained PAT само за това хранилище с право
  „Secrets: Read and write“. Нужен е, за да може подновеният токен да се запише.
- По желание, в Variables: `GRAPH_VERSION` (по подразбиране `v24.0`).

## Тестове

```bash
python3 -m unittest discover -s tests -v
```
