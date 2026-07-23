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

## Архітектура

Керується хмарною рутиною Claude (Routines, `/schedule`):

- **Repository**: цей репозиторій підключено до рутини в режимі read-only —
  клонується, `check.py` запускається. GitHub-конектор Claude наразі не
  підтримує запис (push/create ref повертає 403 "Resource not accessible by
  integration") — це поточне обмеження research-preview фічі, тому стан
  свідомо винесено за межі git.
- **Стан** ("вже побачені" оголошення): файл `gag-koeln-seen.json` у Google
  Drive акаунта, до якого підключено рутину. Рутина читає його на початку
  кожного запуску (через Drive-конектор), рахує різницю з поточним списком і
  перезаписує файл наприкінці. Формат — той самий JSON, що повертає
  `check.py`.
- **Сповіщення**: Telegram-бот, повідомлення надсилаються напряму через
  Telegram Bot API (`curl` всередині сесії рутини), а не через Gmail —
  Gmail-конектор Claude вміє лише створювати чернетки (`create_draft`), не
  надсилати листи автономно (свідоме обмеження безпеки). Надсилається тільки
  якщо є нові оголошення.
- **Мережевий доступ середовища**: Custom allowlist, домени
  `www.gag-koeln.de` і `api.telegram.org`.
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
  і `<TELEGRAM_CHAT_ID>` — **секрети, ніколи не комітяться в цей репозиторій**
  (зберігаються лише в полі Instructions самої рутини на claude.ai).

```
Repository: ikorytnyi/gag-koeln-watch (read-only clone, already available).

1. Run: python3 check.py
   This prints JSON: {object_id: {title, address, rent, area, rooms, facilities, url}} — the currently listed apartments.

2. Using the Google Drive connector, search "My Drive" for a file named exactly
   "gag-koeln-seen.json".
   - If found, read and parse its JSON contents as the previous state (same shape as above).
   - If not found, treat the previous state as an empty object {}.

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

6. Regardless of steps 4/5: overwrite "gag-koeln-seen.json" in Google Drive with the
   full current listings JSON from step 1 (create the file if it didn't already exist;
   only do this if step 1 succeeded and step 2 completed without error — don't
   overwrite state if something failed, to avoid silently losing track of listings).

Do not commit or push anything to the git repo — read-only access is sufficient.
```

### Конектори рутини

- `Google-Drive` — читання/запис файлу стану
- `Claude_Code_Remote` — стандартний, додається автоматично

Gmail-конектор не потрібен (замінено на Telegram).
