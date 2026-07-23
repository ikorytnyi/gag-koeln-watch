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
- `seen.json` — застарілий файл стану з часів, коли стан тримали в цьому
  репозиторії через GitHub REST API. Більше не оновлюється (див. нижче чому),
  залишений лише як історичний артефакт.

## Архітектура

Керується хмарною рутиною Claude (Routines, `/schedule`):

- **Repository**: цей репозиторій підключено до рутини в режимі read-only —
  клонується, `check.py` запускається.
- **Стан** ("вже побачені" оголошення): файли `gag-koeln-seen-<ISO-timestamp>.json`
  у папці **"GAG"** на Google Drive (`folderId: 1kQTxGvP5H8A9hjm-F-ZRkEallTa1roCF`).
  Кожен запуск шукає всі файли за префіксом `gag-koeln-seen-` **саме в цій
  папці** (не по всьому диску), бере **лексикографічно останній**
  (timestamp у форматі `YYYY-MM-DDTHH-MM`, без двокрапок — сортується як
  рядок так само, як і за часом) як попередній стан, і при потребі **створює
  новий** файл з поточним timestamp (Drive-конектор не підтримує
  update/overwrite/delete — тому апдейт неможливий, лишається "найновіший
  виграє"). Часові мітки в іменах дають змогу візуально відсортувати файли в
  Drive і час від часу вручну видаляти старі копії (автоматично це зробити
  не можна — інструменту delete в конекторі немає).

  **Чому не GitHub, і не пряме оновлення в Drive:** пробували два інші
  варіанти, обидва заблоковані на рівні платформи:
  1. GitHub-конектор Claude (через claude.ai/customize/connectors) має лише
     читання — `git push` і MCP `push_files` повертають 403 "Resource not
     accessible by integration".
  2. Прямий виклик GitHub REST API (`PUT .../contents/seen.json`) з окремим
     Personal Access Token (в обхід GitHub-конектора Claude) теж не
     спрацював — цього разу заблокував сам egress-проксі хмарного
     середовища рутини: "Write access to this GitHub API path is not
     permitted through this proxy". Це, схоже, навмисне обмеження безпеки
     на рівні платформи для будь-яких write-запитів до api.github.com з
     хмарних рутин, незалежно від токена.
  3. Google Drive-конектор має лише 8 інструментів (Download file content,
     Get file metadata, Get file permissions, List recent files, Read file
     content, Search files, Copy file, Create file) — без
     update/overwrite/delete. Це не платформне обмеження безпеки, а просто
     неповний набір інструментів конектора — тому єдиний робочий підхід:
     створювати новий файл щоразу (з timestamp у назві для керованості).
- **Сповіщення**: Telegram-бот, повідомлення надсилаються напряму через
  Telegram Bot API (`curl` всередині сесії рутини), а не через Gmail —
  Gmail-конектор Claude вміє лише створювати чернетки (`create_draft`), не
  надсилати листи автономно (свідоме обмеження безпеки). Надсилається тільки
  якщо є нові оголошення. Telegram API, на відміну від GitHub, не блокується
  проксі для запису.
- **Мережевий доступ середовища**: Custom allowlist, домени
  `www.gag-koeln.de` і `api.telegram.org` (`api.github.com` більше не
  потрібен для запису стану).
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
- Текст промпту (Instructions) — див. нижче. Значення `<TELEGRAM_BOT_TOKEN>`
  і `<TELEGRAM_CHAT_ID>` — **секрети, ніколи не комітяться в цей
  репозиторій** (зберігаються лише в полі Instructions самої рутини на
  claude.ai).

```
Repository: ikorytnyi/gag-koeln-watch (read-only clone, already available for check.py).

1. Run: python3 check.py
   This prints JSON: {object_id: {title, address, rent, area, rooms, facilities, url}} — the currently listed apartments.

2. Using the Google Drive connector, search for files inside the folder with
   ID "1kQTxGvP5H8A9hjm-F-ZRkEallTa1roCF" (the "GAG" folder) whose name starts
   with "gag-koeln-seen-" and ends with ".json".
   - If one or more found: sort by filename (lexicographic sort — the timestamp
     format makes this equivalent to chronological order) and read the content
     of the LAST one (most recent) as the previous state.
   - If none found: treat the previous state as an empty object {}.

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

6. Regardless of steps 4/5: using the Google Drive connector, create a NEW file
   inside the folder with ID "1kQTxGvP5H8A9hjm-F-ZRkEallTa1roCF" (the "GAG"
   folder), named "gag-koeln-seen-<UTC timestamp of this run, format
   YYYY-MM-DDTHH-MM, colons replaced with hyphens>.json", containing the full
   current listings JSON from step 1. Only do this if step 1 succeeded and step
   2 completed without error — don't create a new state file if something
   failed, to avoid silently losing track of listings. Do NOT attempt to update
   or delete the older gag-koeln-seen-*.json files — the Drive connector
   doesn't support that; just leave them (a human cleans them up periodically).
```

### Конектори рутини

- `Claude_Code_Remote` — стандартний, додається автоматично
- `Google-Drive` — читання/створення файлів стану

Gmail не потрібен — сповіщення йдуть через Telegram Bot API (curl).
