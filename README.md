# gag-koeln-watch

Моніторинг нових оголошень оренди квартир на
https://www.gag-koeln.de/immobiliensuche/wohnung-mieten

Без фільтрів — відстежуються всі оголошення. При появі нових надсилається
сповіщення українською в Telegram-групу, з групуванням за кількістю кімнат і
повними деталями для 5-кімнатних квартир.

## Файли

- `check.py` — завантажує сторінку і повертає JSON з поточними оголошеннями
  (`object_id → title/address/rent/area/rooms/facilities/url`). Скрипт **не**
  зберігає стан і нічого нікуди не пише — лише читає сайт. Порівняння з
  попереднім станом виконує сама рутина (агент), а не скрипт.
- `seen.json` — стан: усі оголошення, побачені на попередньому запуску.
  Оновлюється напряму через GitHub REST API (не через `git push`, не через
  Google Drive — див. нижче чому).

## Архітектура

Керується хмарною рутиною Claude (Routines, `/schedule`):

- **Repository**: цей репозиторій підключено до рутини в режимі read-only —
  клонується, `check.py` запускається. GitHub-конектор Claude (той, що
  підключається через claude.ai/customize/connectors) підтримує лише
  читання — `git push` і виклик `push_files` через MCP повертають 403
  "Resource not accessible by integration" (поточне обмеження
  research-preview фічі).
- **Стан** ("вже побачені" оголошення): файл `seen.json` у **цьому ж
  репозиторії**, але оновлюється не через git-клон, а прямими HTTP-запитами
  до **GitHub REST API** (`GET`/`PUT /repos/{owner}/{repo}/contents/{path}`)
  за допомогою окремого **Personal Access Token** (fine-grained, права лише
  "Contents: Read and write", обмежений тільки цим репозиторієм). Цей
  токен — не той самий, що в GitHub-конектора Claude, тому обмеження вище
  на нього не діють. `PUT` з правильним `sha` поточної версії файлу оновлює
  файл на місці (справжній git-комміт, без дублікатів, з історією версій).

  Раніше для стану використовувався Google Drive — довелось відмовитись,
  бо тамтешній конектор Claude має лише 8 інструментів (Download file
  content, Get file metadata, Get file permissions, List recent files,
  Read file content, Search files, Copy file, Create file) — без
  update/overwrite/delete, тому кожен запуск створював новий файл замість
  оновлення, і вони накопичувались дублікатами.
- **Сповіщення**: Telegram-бот, повідомлення надсилаються напряму через
  Telegram Bot API (`curl` всередині сесії рутини), а не через Gmail —
  Gmail-конектор Claude вміє лише створювати чернетки (`create_draft`), не
  надсилати листи автономно (свідоме обмеження безпеки). Надсилається тільки
  якщо є нові оголошення.
- **Мережевий доступ середовища**: Custom allowlist, домени
  `www.gag-koeln.de`, `api.telegram.org`, `api.github.com`.
- **Розклад**: будні дні (пн–пт), о 8:00, 10:00, 12:00, 15:00 (Europe/Berlin).
  Поле "Cron expression" у налаштуваннях рутини інтерпретується **в UTC**,
  хоча підпис "Repeats" у інтерфейсі оманливо показує ці самі цифри так, ніби
  вони вже локальні (візуальний баг інтерфейсу — орієнтуватись на нього не
  можна, тільки на фактичні спрацювання в "Runs"). Поточне значення поля:

  ```
  0 6,8,10,13 * * 1-5
  ```

  Це відповідає 8:00/10:00/12:00/15:00 за Berlin **у літній час (CEST,
  UTC+2)**. Коли Німеччина перейде на зимовий час (кінець жовтня, UTC+1),
  цей вираз почне давати 9:00/11:00/13:00/16:00 замість потрібних годин —
  тоді значення треба вручну поміняти на `0 7,9,11,14 * * 1-5` (і навпаки
  наприкінці березня, коли повертається літній час).

## Відновлення рутини (якщо доведеться створювати заново)

- ID рутини: `trig_01R2F9hf5CE3GrMG33gvAcgQ`
- ID середовища: `env_01V6DDcKskE5E2o2kRoVpCcn`
- Текст промпту (Instructions) — див. нижче. Значення `<TELEGRAM_BOT_TOKEN>`,
  `<TELEGRAM_CHAT_ID>` і `<GITHUB_PAT>` — **секрети, ніколи не комітяться в
  цей репозиторій** (зберігаються лише в полі Instructions самої рутини на
  claude.ai). `GITHUB_PAT` — fine-grained personal access token, обмежений
  тільки цим репозиторієм, з правом лише "Contents: Read and write".

```
Repository: ikorytnyi/gag-koeln-watch (read-only clone, already available for check.py).

1. Run: python3 check.py
   This prints JSON: {object_id: {title, address, rent, area, rooms, facilities, url}} — the currently listed apartments.

2. Fetch the previous state via the GitHub REST API using Bash + curl:
     curl -s -H "Authorization: Bearer <GITHUB_PAT>" -H "Accept: application/vnd.github+json" \
       "https://api.github.com/repos/ikorytnyi/gag-koeln-watch/contents/seen.json"
   - If it returns 200: base64-decode the "content" field to get the previous state JSON,
     and remember the "sha" field (needed for the update in step 6).
   - If it returns 404: treat the previous state as an empty object {} and remember that
     there is no existing sha (this will be a file creation, not an update).

3. Compute new_ids = object_ids present in step 1 but absent from the previous state.

4. If new_ids is non-empty:
   - Group new_ids by "rooms", counting how many new listings per room count.
   - For any new listing where rooms == "5", collect full details.
   - Compose a plain-text Ukrainian report:
     "Нові оголошення на gag-koeln.de: <N>"
     ""
     "За кількістю кімнат:"
     "  <rooms> кімн.: <count>"   (one line per room count, sorted)
     (if any 5-room listings, blank line then:)
     "Деталі 5-кімнатних квартир:"
     (for each: title / address / "rent, area" / facilities joined by ", " / url, blank line between)
   - Send this report via Telegram using Bash + curl:
     curl -s "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/sendMessage" \
       --data-urlencode "chat_id=<TELEGRAM_CHAT_ID>" \
       --data-urlencode "text=<the report text>"
   - IMPORTANT: the message text must be written ONLY in Ukrainian. Use the
     report text above verbatim. Do NOT add any extra greeting, commentary,
     sign-off, or explanation in English or any other language.

5. If new_ids is empty: do not send any Telegram message.

6. Regardless of steps 4/5: update "seen.json" in the GitHub repo with the full
   current listings JSON from step 1, via a PUT request to the GitHub REST API:
     curl -s -X PUT -H "Authorization: Bearer <GITHUB_PAT>" -H "Accept: application/vnd.github+json" \
       -d '{"message": "update seen state", "content": "<base64 of the JSON from step 1>", "sha": "<sha from step 2, omit this field entirely if step 2 returned 404>"}' \
       "https://api.github.com/repos/ikorytnyi/gag-koeln-watch/contents/seen.json"
   Only do this if step 1 succeeded and step 2 completed without error — don't
   overwrite state if something failed, to avoid silently losing track of listings.

Do not use git clone/push for seen.json — use the GitHub REST API calls above only.
```

### Конектори рутини

- `Claude_Code_Remote` — стандартний, додається автоматично

Google Drive і Gmail не потрібні — стан і сповіщення йдуть напряму через
GitHub REST API та Telegram Bot API (curl), без MCP-конекторів.
