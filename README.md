# gag-koeln-watch

Моніторинг нових оголошень оренди квартир на
https://www.gag-koeln.de/immobiliensuche/wohnung-mieten

Без фільтрів — відстежуються всі оголошення. При появі нових надсилається
сповіщення українською в Telegram-групу, з групуванням за кількістю кімнат і
повними деталями для 5-кімнатних квартир.

## Файли

- `check.py` — завантажує сторінку з оголошеннями.
  - `python3 check.py` — друкує JSON поточних оголошень
    (`object_id → title/address/rent/area/rooms/facilities/url`).
  - `python3 check.py --state seen.json` — порівнює з `seen.json`, перезаписує
    його поточними оголошеннями і друкує готовий український текст звіту для
    Telegram (порожній вивід — нових оголошень немає). Нічого не комітить.
- `run.sh` — повний цикл одного запуску (саме його викликає рутина):
  підтягує гілку `claude/state` в тимчасовий worktree → `check.py --state` →
  якщо є нові, надсилає звіт у Telegram → комітить і пушить `seen.json` у
  `claude/state` (тільки якщо стан змінився). Токен і chat id приходять через
  змінні оточення `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`.

## Архітектура

Керується хмарною рутиною Claude (Routines, `/schedule`):

- **Repository**: цей репозиторій підключено до рутини **з правом запису**
  (не read-only). Агент лише запускає `./run.sh` — вся логіка (порівняння,
  текст звіту, timestamp) детермінована і живе в коді, а не в промпті.
- **Стан** ("вже побачені" оголошення): файл `seen.json` в окремій гілці
  **`claude/state`** (orphan-гілка, не має спільної історії з `main`, тож
  автоматичні коміти не засмічують `main`). Кожна зміна стану — окремий коміт,
  тож історія доступна через `git log -p origin/claude/state`. Коміт робиться
  тільки коли список оголошень змінився.

  Гілка має саме префікс `claude/`, бо git-проксі хмарного середовища
  рутини за замовчуванням дозволяє пушити лише в гілки з цим префіксом.
  Це ж пояснює старі невдачі: пуш у `main` і запис через GitHub REST API
  (`PUT .../contents/...`) проксі відхиляє, а звичайний `git push` у
  `claude/*` — ні.

  **Порядок важливий:** стан пушиться тільки після успішного надсилання в
  Telegram. Якщо Telegram або сайт недоступні, `run.sh` завершується з
  помилкою до пушу, і наступний запуск повторить спробу — оголошення не
  загубляться.

  Історія: з 2026-07-23 по 2026-10-15 стан зберігався як окремі файли
  `gag-koeln-seen-<timestamp>.json` у папці "GAG" на Google Drive
  (`folderId: 1kQTxGvP5H8A9hjm-F-ZRkEallTa1roCF`). Усі 876 файлів перенесено в
  `claude/state` як коміти з оригінальними датами (324 коміти — лише ті
  знімки, де стан змінювався). Drive-конектор рутині більше не потрібен.
- **Сповіщення**: Telegram-бот, повідомлення надсилаються напряму через
  Telegram Bot API (`curl` у `run.sh`). Надсилається тільки якщо є нові
  оголошення.
- **Мережевий доступ середовища**: Custom allowlist, домени
  `www.gag-koeln.de` і `api.telegram.org` (`github.com` для git працює через
  вбудований проксі).
- **Розклад**: щодня (без винятків для вихідних), о 8:00, 10:00, 12:00, 15:00
  (Europe/Berlin). Поле "Cron expression" у налаштуваннях рутини
  інтерпретується **в UTC**, хоча підпис "Repeats" у інтерфейсі оманливо
  показує ці самі цифри так, ніби вони вже локальні (візуальний баг
  інтерфейсу — орієнтуватись на нього не можна, тільки на фактичні
  спрацювання в "Runs"). Поточне значення поля:

  ```
  0 6,8,10,13 * * *
  ```

  Це відповідає 8:00/10:00/12:00/15:00 за Berlin **у літній час (CEST,
  UTC+2)**. Коли Німеччина перейде на зимовий час (кінець жовтня, UTC+1),
  цей вираз почне давати 9:00/11:00/13:00/16:00 замість потрібних годин —
  тоді значення треба вручну поміняти на `0 7,9,11,14 * * *` (і навпаки
  наприкінці березня, коли повертається літній час).

## Відновлення рутини (якщо доведеться створювати заново)

- ID рутини: `trig_01R2F9hf5CE3GrMG33gvAcgQ`
- ID середовища: `env_01V6DDcKskE5E2o2kRoVpCcn`
- Репозиторій: `ikorytnyi/gag-koeln-watch`, **з правом запису** (Claude
  GitHub App з доступом Contents: write).
- Текст промпту (Instructions) — див. нижче. Значення `<TELEGRAM_BOT_TOKEN>`
  і `<TELEGRAM_CHAT_ID>` — **секрети, ніколи не комітяться в цей
  репозиторій** (зберігаються лише в полі Instructions самої рутини на
  claude.ai).

```
Repository: ikorytnyi/gag-koeln-watch (cloned with write access).

Run exactly this one command from the repository root via Bash and do nothing else:

TELEGRAM_BOT_TOKEN='<TELEGRAM_BOT_TOKEN>' TELEGRAM_CHAT_ID='<TELEGRAM_CHAT_ID>' ./run.sh

The script fetches listings, sends the Ukrainian Telegram report if there are
new ones, and pushes the updated state to the claude/state branch.
- Do NOT send any Telegram messages yourself, do NOT edit any files, do NOT
  commit or push anything yourself — run.sh does all of that.
- If the command exits non-zero, do NOT retry and do NOT try to fix anything;
  just report the full output. The next scheduled run will retry.
```

### Конектори рутини

- `Claude_Code_Remote` — стандартний, додається автоматично

Google Drive і Gmail не потрібні.
